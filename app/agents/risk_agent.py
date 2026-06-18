"""风险 Agent —— 推文风险因子识别与等级评估。

核心职责：
    对一批推文并行调用 LLM，提取结构化风险因子并评估整体风险等级。

与 analysis_agent 的分工：
    - analysis_agent：提取投资标的、情绪、观点（进攻端）
    - risk_agent：识别风险因子、评估风险等级（防御端）

二者在 Supervisor 中并行执行（Send fan-out），结果在 merge 节点合并：
risk_factors 覆盖到对应的分析记录上，形成完整的投资信号。

设计特点：
    - 6大类风险分类体系（市场/流动性/监管/技术面/事件驱动/信用违约）
    - 4档风险等级量化标准（critical/high/medium/low）
    - RiskFactor 结构化模型：category + severity + urgency + related_tickers
    - 风险黑话/暗语识别 + 反讽过滤
    - CoT reasoning 支持风控审计追溯
    - field_validator 容错 LLM 输出异常
    - asyncio.gather 批量并发，失败容忍
"""
import asyncio
import time
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.agents.llm import get_signal_llm
from app.prompts import get_chat_prompt
from app.services.blogger_context import fetch_blogger_contexts, build_blogger_context_block


# ============================================================
# 风险评估 Prompt —— 已迁移至 prompts/risk.yaml
# ------------------------------------------------------------
# Prompt 模板通过 get_chat_prompt("risk/system_prompt") 加载，
# 运行时变量 blogger_context / classification_hint / author_handle / content
# 由 Jinja2 渲染。
# ============================================================


def _to_lc_messages(msg_dicts: list[dict]) -> list:
    """将 get_chat_prompt 返回的 dict 列表转换为 LangChain Message 对象。"""
    _ROLE_MAP = {"system": SystemMessage, "human": HumanMessage}
    return [_ROLE_MAP[m["role"]](content=m["content"]) for m in msg_dicts]


# ============================================================
# 结构化输出 Schema —— 风险因子细粒度模型
# ============================================================
class RiskFactor(BaseModel):
    """单个风险因子的结构化描述。"""
    category: Literal["market", "liquidity", "regulatory", "technical", "event", "credit"] = Field(
        description="风险分类: market/liquidity/regulatory/technical/event/credit"
    )
    description: str = Field(description="风险描述（中文简述）")
    severity: Literal["critical", "high", "medium", "low"] = Field(
        default="medium", description="该因子严重程度"
    )
    urgency: Literal["imminent", "near_term", "long_term"] = Field(
        default="near_term",
        description="时间紧迫性: imminent(已发生/即将), near_term(数天~数周), long_term(潜在长期)"
    )
    related_tickers: list[str] = Field(
        default_factory=list, description="该风险影响的标的代码列表"
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v):
        if not isinstance(v, str):
            return "market"
        mapping = {
            "市场": "market", "流动性": "liquidity", "监管": "regulatory",
            "技术": "technical", "事件": "event", "信用": "credit",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "market"

    @field_validator("related_tickers", mode="before")
    @classmethod
    def _ensure_ticker_list(cls, v):
        if not isinstance(v, list):
            return []
        return [str(x).strip().upper() for x in v if x]


class TweetRiskAssessment(BaseModel):
    """单条推文的风险评估结果。

    生产级 Schema：
        - RiskFactor 结构化风险因子（分类 + 严重度 + 紧迫性 + 关联标的）
        - 4档风险等级 (critical/high/medium/low)
        - CoT reasoning 支持审计追溯
        - field_validator 容错 LLM 异常输出
        - @property 保持向后兼容
    """
    reasoning: str = Field(
        default="",
        description="分析逻辑链：1.风险信号识别 2.分类 3.紧迫性 4.反讽判断 5.等级判定"
    )
    risk_factors: list[RiskFactor] = Field(
        default_factory=list, description="结构化风险因子列表"
    )
    risk_level: Literal["critical", "high", "medium", "low"] = Field(
        default="low", description="综合风险等级（取所有因子中最高 severity）"
    )
    risk_summary: str = Field(
        default="", description="一句话风险概述"
    )

    # ----------------------------------------------------------
    # LLM 输出容错 validators
    # ----------------------------------------------------------
    @field_validator("risk_factors", mode="before")
    @classmethod
    def _ensure_risk_list(cls, v):
        """兼容 LLM 偶尔返回 null 或非数组。"""
        return v if isinstance(v, list) else []

    @field_validator("risk_level", mode="before")
    @classmethod
    def _normalize_risk_level(cls, v):
        """容错：LLM 可能返回中文或非标准值。"""
        if not isinstance(v, str):
            return "low"
        mapping = {
            "紧急": "critical", "严重": "critical", "极高": "critical",
            "高": "high", "高风险": "high",
            "中": "medium", "中等": "medium", "中风险": "medium",
            "低": "low", "低风险": "low", "无": "low",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, normalized) if normalized else "low"

    @field_validator("risk_summary", mode="before")
    @classmethod
    def _ensure_str(cls, v):
        """确保 risk_summary 为字符串。"""
        if v is None:
            return ""
        return str(v)

    # ----------------------------------------------------------
    # 向后兼容属性 —— 供 merge 节点消费旧格式
    # ----------------------------------------------------------
    @property
    def risk_factor_texts(self) -> list[str]:
        """返回纯文本风险因素列表，兼容旧版 risk_assessments[*]['risk_factors'] 为 list[str] 的消费方。"""
        return [f.description for f in self.risk_factors]


# ============================================================
# 单条推文风险评估 —— 异步 LLM 调用
# ============================================================
async def _assess_one(structured_llm, tweet: dict, blogger_context: str, classification_hint: str) -> dict | None:
    """对单条推文执行风险评估，返回结构化结果或 None（失败时）。"""
    start = time.perf_counter()
    try:
        messages = _to_lc_messages(get_chat_prompt(
            "risk/system_prompt",
            blogger_context=blogger_context,
            classification_hint=classification_hint,
            author_handle=tweet["author_handle"],
            content=tweet["content"],
        ))
        result = await structured_llm.ainvoke(messages)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = result.model_dump()
        data["tweet_id"] = tweet["id"]
        data["_latency_ms"] = latency_ms
        logger.debug(
            "[Risk] tweet={} latency={}ms risk_level={}",
            tweet["id"][:8], latency_ms, data.get("risk_level", "low"),
        )
        return data
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.warning("Risk agent failed for tweet {} ({}ms): {}", tweet["id"], latency_ms, e)
        return None


# ============================================================
# 批量风险评估编排
# ------------------------------------------------------------
# 对所有输入推文并行调用 LLM（不做过滤，因为 Supervisor 路由
# 时已确保只有 needs_risk_analysis=true 的推文才发送到这里）。
# ============================================================
async def _run_risk(state: dict) -> dict:
    """批量执行风险评估，注入博主画像和分类提示，asyncio.gather 并发。"""
    tweets = state["tweets"]
    classifications = state.get("classifications", [])

    # #14: 批量获取博主历史画像（共享 service，与 analysis_agent 解耦）
    handles = list({t["author_handle"] for t in tweets})
    blogger_contexts = fetch_blogger_contexts(handles)
    context_block = build_blogger_context_block(blogger_contexts)

    # #15: 构建 tweet_id -> 分类提示映射
    category_map = {c["tweet_id"]: c.get("category", "") for c in classifications}
    category_hints = {
        "risk_warning": "该推文被分类为「风险预警」，重点识别具体风险因子和紧迫性。",
        "investment": "该推文被分类为「投资建议」，关注其中隐含的风险因素。",
        "market_commentary": "该推文被分类为「市场评论」，评估是否包含潜在风险信号。",
    }

    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(TweetRiskAssessment)

    tasks = []
    for tweet in tweets:
        cat = category_map.get(tweet["id"], "")
        hint = category_hints.get(cat, "无特殊分类提示。")
        tasks.append(_assess_one(structured_llm, tweet, context_block, hint))

    results = await asyncio.gather(*tasks)
    risk_assessments = [r for r in results if r is not None]

    if risk_assessments:
        latencies = [r.get("_latency_ms", 0) for r in risk_assessments]
        logger.info(
            "[Risk] batch done: total={} assessed={} avg_latency={}ms max_latency={}ms",
            len(tweets), len(risk_assessments),
            sum(latencies) // len(latencies), max(latencies),
        )

    return {"risk_assessments": risk_assessments}


# ============================================================
# LangGraph 节点入口 —— 事件循环兼容
# ------------------------------------------------------------
# 与 analysis_agent_node 相同的线程池桥接策略。
# ============================================================
def risk_agent_node(state: dict) -> dict:
    """风险 Agent 的 LangGraph 节点入口。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run_risk(state)).result()
    return asyncio.run(_run_risk(state))
