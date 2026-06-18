import operator
from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from loguru import logger

from app.agents.analysis_agent import analysis_agent_node
from app.agents.llm import get_report_llm
from app.prompts import get_chat_prompt
from app.agents.risk_agent import risk_agent_node
from app.schemas.routing import BatchClassificationResult
from app.services.trace_service import traced_node


# ============================================================
# Supervisor 全局状态定义
# ------------------------------------------------------------
# 该状态在整个 StateGraph 中流转，承载从分类 → 分析 / 风险 →
# 合并 → 收尾各阶段的中间产物与最终结果。
# prediction_agent 已移至 Celery 后台定时任务异步执行，
# 不再阻塞实时分析链路。
# 带 Annotated[..., operator.add] 的字段会在 fan-in 时自动累加，
# 用于汇总并行子 Agent 的输出。
# ============================================================
class SupervisorState(TypedDict):
    tweets: list[dict]                # 入口推文列表（原始数据）
    analyses: list[dict]              # 合并后的分析结果（merge 节点写入）
    ticker_summaries: list[dict]      # 标的维度的聚合摘要
    phase: str                        # 当前阶段标记: classify / done
    classification: dict              # supervisor_classify 节点的分类结果
    # 并行 fan-out 节点的部分结果，使用 operator.add 在 fan-in 时合并
    partial_analyses: Annotated[list[dict], operator.add]
    risk_assessments: Annotated[list[dict], operator.add]
    _trace_conv_id: str               # LangSmith / 自研 trace 的会话 ID


# ============================================================
# 分类阶段 Prompt
# ------------------------------------------------------------
# Supervisor 的核心职责：先对一批推文做轻量分类，决定后续走哪条
# 处理路径，避免对 non_financial 推文浪费昂贵的分析 / 风险模型调用。
# 输出结构由 BatchClassificationResult 强约束（json_schema）。
# Prompt 模板已迁移至 prompts/supervisor.yaml，通过 get_chat_prompt 加载。
# ============================================================


def _to_lc_messages(msg_dicts: list[dict]) -> list:
    """将 get_chat_prompt 返回的 dict 列表转换为 LangChain Message 对象。"""
    _ROLE_MAP = {"system": SystemMessage, "human": HumanMessage}
    return [_ROLE_MAP[m["role"]](content=m["content"]) for m in msg_dicts]


# ============================================================
# Token 预算保护常量
# ------------------------------------------------------------
# 分类阶段属于"轻量级判别"，不需要全文。对单条推文做硬截断，
# 并对整批拼接后的总长度再做一次防御性截断，避免极端长文导致
# 上下文窗口爆掉或成本失控。
# ============================================================
CLASSIFY_MAX_CHARS_PER_TWEET = 500   # 单条推文进入分类 Prompt 的最大字符数
CLASSIFY_MAX_TOTAL_CHARS = 6000      # 整批推文拼接后的最大字符数


# ============================================================
# 节点 1：supervisor_classify —— 批量分类
# ------------------------------------------------------------
# 1) 拼装受控长度的推文文本；
# 2) 调用 LLM 产出结构化分类结果；
# 3) LLM 失败时降级为 market_commentary（保守选择，不触发风险路径）。
# ============================================================
@traced_node("supervisor_classify")
def supervisor_classify_node(state: SupervisorState) -> dict:
    tweets = state["tweets"]

    # 单条截断 + 标准化前缀，方便 LLM 对应到 tweet_id
    tweet_lines = []
    for t in tweets:
        content = t["content"][:CLASSIFY_MAX_CHARS_PER_TWEET]
        tweet_lines.append(f"[ID: {t['id']}] 博主: {t['author_handle']}\n内容: {content}")

    # 整批再做一次总长度兜底
    tweets_text = "\n\n".join(tweet_lines)
    if len(tweets_text) > CLASSIFY_MAX_TOTAL_CHARS:
        tweets_text = tweets_text[:CLASSIFY_MAX_TOTAL_CHARS] + "\n\n[...已截断]"

    try:
        # json_mode + 手动解析，兼容不严格遵循 schema 的模型
        llm = get_report_llm()
        structured_llm = llm.with_structured_output(BatchClassificationResult)
        messages = _to_lc_messages(get_chat_prompt("supervisor/classify", tweets_text=tweets_text))
        result = structured_llm.invoke(messages)
        if result is None:
            raise ValueError("LLM returned None for classification")
        classification = result.model_dump()
    except Exception as e:
        # 尝试降级：用普通 JSON 模式解析
        try:
            from app.agents.llm import get_report_llm as _get_llm
            import json
            _llm = _get_llm().bind(response_format={"type": "json_object"})
            _messages = _to_lc_messages(get_chat_prompt("supervisor/classify", tweets_text=tweets_text))
            raw_result = _llm.invoke(_messages)
            raw_json = json.loads(raw_result.content)
            # 兼容模型将列表放在 tweets / classifications / items 等不同键名
            cls_list = (
                raw_json.get("classifications")
                or raw_json.get("tweets")
                or raw_json.get("items")
                or []
            )
            classification = BatchClassificationResult(
                classifications=cls_list,
                has_investment_content=raw_json.get("has_investment_content", True),
            ).model_dump()
        except Exception as fallback_err:
            # 最终降级：默认 market_commentary + 不触发风险分析，置信度低
            logger.warning(
                "Supervisor classify failed (primary: {}, fallback: {}), using defaults",
                e, fallback_err,
            )
            classification = {
                "classifications": [
                    {
                        "tweet_id": t["id"],
                        "category": "market_commentary",
                        "needs_risk_analysis": False,
                        "confidence": 0.3,
                    }
                    for t in tweets
                ],
                "has_investment_content": True,
            }

    return {"classification": classification, "phase": "classify"}


# ============================================================
# 路由 1：route_after_classification —— 分类后扇出
# ------------------------------------------------------------
# 基于分类结果，决定将哪些推文分别路由到：
#   - analysis_agent：所有非 non_financial 推文
#   - risk_agent：明确需要风险分析且置信度 >= 0.5 的推文
# 没有任何金融内容时，直接跳到 supervisor_finalize 收尾。
# 使用 Send 列表实现 LangGraph 的并行 fan-out。
# ============================================================
def route_after_classification(state: SupervisorState) -> list[Send]:
    classification = state.get("classification", {})
    classifications = classification.get("classifications", [])
    has_investment = classification.get("has_investment_content", False)
    trace_id = state.get("_trace_conv_id", "")

    # 整批都是非金融 → 直接结束，节省所有下游成本
    if not has_investment:
        return [Send("supervisor_finalize", state)]

    # 通过 id 快速回查原始推文
    tweet_map = {t["id"]: t for t in state["tweets"]}

    # 分析路径：剔除非金融
    analysis_ids = {
        c["tweet_id"] for c in classifications
        if c.get("category") != "non_financial"
    }
    # 风险路径：仅在分类器明确指定且置信度足够时进入，避免误报
    risk_ids = {
        c["tweet_id"] for c in classifications
        if c.get("needs_risk_analysis") and c.get("confidence", 0) >= 0.5
    }

    sends = []

    # 构造 analysis_agent 的输入子状态
    analysis_tweets = [tweet_map[tid] for tid in analysis_ids if tid in tweet_map]
    analysis_classifications = [c for c in classifications if c["tweet_id"] in analysis_ids]
    if analysis_tweets:
        sends.append(Send("analysis_agent", {
            "tweets": analysis_tweets,
            "classifications": analysis_classifications,
            "_trace_conv_id": trace_id,
        }))

    # 构造 risk_agent 的输入子状态（与 analysis 并行执行）
    risk_tweets = [tweet_map[tid] for tid in risk_ids if tid in tweet_map]
    risk_classifications = [c for c in classifications if c["tweet_id"] in risk_ids]
    if risk_tweets:
        sends.append(Send("risk_agent", {
            "tweets": risk_tweets,
            "classifications": risk_classifications,
            "_trace_conv_id": trace_id,
        }))

    # 兜底：分类说有金融内容，但置信度全部不达标 → 直接收尾
    if not sends:
        return [Send("supervisor_finalize", state)]

    return sends


# ============================================================
# 节点 2：supervisor_merge —— 合并并行子 Agent 结果
# ------------------------------------------------------------
# analysis_agent 与 risk_agent 是并行 fan-out，二者输出通过
# Annotated[..., operator.add] 自动累积到 partial_analyses /
# risk_assessments。本节点：
#   1) 把风险因子按 tweet_id 回填到对应分析对象；
#   2) 合并后直接结束（预测由 Celery 后台异步完成）。
# ============================================================
@traced_node("supervisor_merge")
def supervisor_merge_node(state: SupervisorState) -> dict:
    partial_analyses = state.get("partial_analyses", [])
    risk_assessments = state.get("risk_assessments", [])

    # tweet_id -> 风险评估结果索引，O(n) 合并
    risk_map = {r["tweet_id"]: r for r in risk_assessments}

    merged = []
    for analysis in partial_analyses:
        tweet_id = analysis.get("tweet_id")
        if tweet_id in risk_map:
            assessment = risk_map[tweet_id]
            raw_factors = assessment.get("risk_factors", [])
            # 结构化风险因子 → 提取 description 作为 list[str] 保持向后兼容
            if raw_factors and isinstance(raw_factors[0], dict):
                analysis["risk_factors"] = [f.get("description", "") for f in raw_factors if f.get("description")]
                analysis["risk_details"] = raw_factors
            else:
                analysis["risk_factors"] = raw_factors
                analysis["risk_details"] = []
            analysis["risk_level"] = assessment.get("risk_level", "low")
            analysis["risk_summary"] = assessment.get("risk_summary", "")

            # per-ticker 风险分配：将 risk_details 按 related_tickers 匹配到各标的
            _enrich_tickers_with_risks(analysis)
        elif "risk_factors" not in analysis:
            analysis["risk_factors"] = []
        merged.append(analysis)

    return {
        "analyses": merged,
        "phase": "done",
    }


# 风险等级优先级（用于取 max）
_RISK_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _enrich_tickers_with_risks(analysis: dict) -> None:
    """将 risk_details 按 related_tickers 分配到各 ticker 对象，计算 per-ticker risk level。"""
    tickers = analysis.get("tickers", [])
    risk_details = analysis.get("risk_details", [])

    if not tickers or not risk_details:
        return

    ticker_symbols = {t.get("symbol", "").upper() for t in tickers}

    for ticker in tickers:
        symbol = ticker.get("symbol", "").upper()
        matched_risks = []
        for risk in risk_details:
            related = [r.upper() for r in risk.get("related_tickers", [])]
            # 匹配条件：明确关联该标的，或未指定关联标的（视为全局风险）
            if symbol in related or (not related and len(ticker_symbols) == 1):
                matched_risks.append({
                    "category": risk.get("category", "market"),
                    "description": risk.get("description", ""),
                    "severity": risk.get("severity", "medium"),
                    "urgency": risk.get("urgency", "near_term"),
                })

        ticker["risks"] = matched_risks
        # per-ticker risk level = 最高 severity
        if matched_risks:
            max_sev = max(_RISK_SEVERITY_ORDER.get(r["severity"], 1) for r in matched_risks)
            level_map = {4: "critical", 3: "high", 2: "medium", 1: "low"}
            ticker["ticker_risk_level"] = level_map.get(max_sev, "low")
        else:
            ticker["ticker_risk_level"] = "low"


# ============================================================
# 节点 3：supervisor_finalize —— 收尾
# ------------------------------------------------------------
# 统一输出口径：无论从哪条路径进来，都保证核心字段存在，
# 并将 phase 标记为 done。便于上层 analysis_service 直接消费。
# 预测由 Celery 后台任务异步生成，不在此处产出。
# ============================================================
@traced_node("supervisor_finalize")
def supervisor_finalize_node(state: SupervisorState) -> dict:
    return {
        "analyses": state.get("analyses", []),
        "ticker_summaries": state.get("ticker_summaries", []),
        "phase": "done",
    }


# ============================================================
# 图拓扑构建
# ------------------------------------------------------------
# 流程概览（prediction_agent 已移至 Celery 异步）：
#   START
#     → supervisor_classify
#     → (条件 fan-out) analysis_agent ‖ risk_agent ‖ supervisor_finalize
#     → supervisor_merge
#     → supervisor_finalize → END
#
# 子 Agent 节点统一包裹 traced_node，保证全链路可观测。
# ============================================================
def build_supervisor_graph():
    graph = StateGraph(SupervisorState)

    # 子 Agent 同样接入 trace 装饰器，便于在 LangSmith / 审计表中查看
    traced_analysis = traced_node("analysis_agent")(analysis_agent_node)
    traced_risk = traced_node("risk_agent")(risk_agent_node)

    # 注册所有节点
    graph.add_node("supervisor_classify", supervisor_classify_node)
    graph.add_node("analysis_agent", traced_analysis)
    graph.add_node("risk_agent", traced_risk)
    graph.add_node("supervisor_merge", supervisor_merge_node)
    graph.add_node("supervisor_finalize", supervisor_finalize_node)

    # 入口 → 分类
    graph.add_edge(START, "supervisor_classify")

    # 分类后条件路由（fan-out 到 analysis/risk，或直接收尾）
    graph.add_conditional_edges(
        "supervisor_classify",
        route_after_classification,
        ["analysis_agent", "risk_agent", "supervisor_finalize"],
    )

    # fan-in：并行 Agent 的结果汇聚到 supervisor_merge
    graph.add_edge("analysis_agent", "supervisor_merge")
    graph.add_edge("risk_agent", "supervisor_merge")

    # merge 直接进入收尾（预测异步）
    graph.add_edge("supervisor_merge", "supervisor_finalize")
    graph.add_edge("supervisor_finalize", END)

    return graph.compile()


# 模块级单例：在应用启动时一次性编译，避免每次调用重新构图
supervisor = build_supervisor_graph()
