"""
报告生成 LangGraph Agent
============================================================
职责：根据用户查询，自动生成一份结构化的金融跟踪报告。

整体管线（StateGraph 编排）：
  parse_intent → multi_retrieve（5路并行） → fuse(RRF) → rerank
                → generate_section（5 章节 Send 并行） → synthesize

设计决策：
1. LangGraph StateGraph：有状态的 DAG 执行引擎
   - 每个节点是独立函数，修改 state 的特定字段
   - Annotated[list, operator.add] 实现并行节点结果的自动合并

2. Send 并行检索：parse_intent 后通过 conditional_edges + Send
   将 4 个检索任务并行派发，互不阻塞，显著降低总延迟

3. 分段生成 → 综合：
   - 先按主题（KOL/研报/新闻/风险/历史）分别生成章节（用 Signal LLM，快且便宜）
   - 再由 Report LLM（Claude，更强推理能力）综合所有章节输出最终报告
   - 好处：并行生成 + 专业模型分工

4. 容错：每个检索/生成节点内部 try-except，单路失败不影响整体管线

状态流转：
  parsing → retrieving → reranking → generating → done / no_results
"""

from __future__ import annotations

import concurrent.futures
import operator
import time
import uuid
from typing import Annotated, Literal, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from pydantic import BaseModel, Field

from app.agents.llm import get_report_llm, get_signal_llm
from app.agents.self_query_agent import QueryIntent, parse_intent
from app.core.config import settings
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranker import rerank, apply_time_decay
from app.rag.retrievers.analysis_retriever import retrieve_analyses
from app.rag.retrievers.bm25_retriever import retrieve_bm25
from app.rag.retrievers.document_retriever import retrieve_documents
from app.rag.retrievers.structured_retriever import retrieve_structured
from app.rag.retrievers.tweet_retriever import retrieve_tweets


class ReportState(TypedDict):
    """报告生成全局状态。

    使用 Annotated[list, operator.add] 的字段（retrieve_results / sections）
    支持多个并行节点各自追加结果，LangGraph 自动合并。
    """

    user_id: str                                          # 当前用户 ID
    query: str                                            # 原始查询文本
    intent: dict | None                                   # 解析后的结构化意图
    query_embedding: list[float] | None                   # parse_intent 阶段预计算的查询向量（5 路向量检索复用）
    retrieve_results: Annotated[list[list[dict]], operator.add]  # 4路检索结果（并行追加）
    retrieval_errors: Annotated[dict[str, str], operator.or_]    # 各路检索的失败原因（path -> message）
    fused: list[dict]                                     # RRF 融合后的文档列表
    reranked: list[dict]                                  # Rerank 精排后的文档列表
    sections: Annotated[list[dict], operator.add]         # 各章节生成结果（可并行追加）
    synthesis: dict | None                                # 综合报告（summary + consensus）
    report_id: str | None                                 # 持久化后的报告 ID
    status: str                                           # 当前管线状态
    error: str | None                                     # 错误信息（如果有）


class RetrieveSubState(TypedDict):
    """检索子节点的输入状态（由 Send 派发）。"""

    path: str       # 检索路径标识：documents/tweets/analyses/structured
    user_id: str
    intent: dict
    query_embedding: list[float] | None  # 由 parse_intent 阶段预计算的查询向量


class SectionSubState(TypedDict):
    """章节生成子节点的输入状态（由 Send 派发）。"""

    section_def: dict           # 单个 SECTION_DEFINITIONS 条目
    reranked: list[dict]        # 整体 rerank 后的文档列表，由各章节自行筛选


# ============================================================
# 报告章节定义
# ------------------------------------------------------------
# 每个章节对应一组 source_type，rerank 后按类型分配相关文档给各章节
# ============================================================
SECTION_DEFINITIONS = [
    {"name": "kol_views", "title": "KOL 观点", "source_types": ["tweet"]},
    {"name": "research_views", "title": "研报观点", "source_types": ["document"]},
    {"name": "news_updates", "title": "新闻动态", "source_types": ["document", "tweet"]},
    {"name": "risk_alerts", "title": "风险提示", "source_types": ["analysis", "structured"]},
    {"name": "historical_review", "title": "历史预测回顾", "source_types": ["structured"]},
]

# 章节生成 Prompt：要求基于参考材料撰写，强制引用标注
_SECTION_PROMPT = """你是一个金融分析报告的章节撰写专家。

## 任务
根据以下检索到的参考材料，撰写报告的「{title}」章节。

## 参考材料格式说明
每条参考材料以 `[N]` 开头，**N 是全局唯一的引用编号**（可能不连续，如 [3]、[7]、[1]）。
紧随其后的 `(...)` 中包含 metadata，字段可能包括：
  - 来源类型（tweet / document / analysis / structured）
  - @博主账号
  - 发布日期 (YYYY-MM-DD)
  - sentiment（bullish / bearish / neutral 等）
  - horizon（投资周期）
  - cred（博主可信度，0-1）
  - 涉及标的 ticker

## 要求
1. 仅基于提供的参考材料撰写，不要编造信息
2. **必须使用材料中给出的原始编号** [N]，不要重新编号或合并编号
3. 引用观点时**必须落实到具体博主、日期或来源类型**，例如：
   "@qinbafrank 在 6 月 8 日表示...[3]"、"近期某研报指出...[7]"
4. 当多条来源观点冲突时，**优先采纳 cred 较高、日期较近的观点**，并指出分歧
5. 语言简洁专业，300-500 字
6. 如果参考材料不足，说明"相关数据有限"

## 参考材料
{sources}

## 输出
直接输出章节内容，无需标题。"""

# 综合 Prompt：将各章节草稿 + 原始证据合并为最终报告（含 consensus 评级）
_SYNTHESIS_PROMPT = """你是一个资深金融分析师。请根据以下「章节草稿」与「原始证据」生成一份完整的跟踪报告。

## 标的: {ticker}
## 时间范围: {time_range}

## 各章节草稿
{sections_text}

## 原始证据（已按相关性排序，metadata 含来源类型/博主/日期/sentiment/horizon/cred/ticker）
{evidence_text}

## 评级原则
- 综合参考章节草稿中的归纳和原始证据中的具体数据
- consensus 应反映原始证据中的情感分布，**优先按 cred 与日期加权**
- 当章节草稿与原始证据矛盾时，以原始证据为准
- 如果证据不足或观点严重分歧，consensus 取 neutral

## 输出
请严格按 JSON schema 输出（summary ≤300字，recommendation ≤150字）。recommendation 中如引用观点请简述来源类别（如"多位 KOL"、"近期研报"），不必出现编号。
根据各方观点的一致性程度、情感倾向与可信度判断 consensus 评级。"""


# ============================================================
# Graph 节点函数
# ============================================================

def parse_intent_node(state: ReportState) -> dict:
    """节点 1：解析用户查询为结构化 QueryIntent，并预计算查询向量供后续检索复用。"""
    from app.rag.embeddings import get_embedder
    from app.rag.vector_store import get_vector_store

    intent = parse_intent(state["query"])
    # 在并行 Send 派发前预热向量库单例，避免多线程并发初始化 chromadb 客户端时
    # 触发 'Could not connect to tenant default_tenant' 竞态。
    get_vector_store()
    # 三路向量检索共用同一个 query_embedding，避免重复 embed
    query_text = f"{intent.ticker} {' '.join(intent.keywords)}".strip() or state["query"]
    try:
        query_embedding = get_embedder().embed_query(query_text)
    except Exception:
        # embed 失败时下游 retriever 自行回退到本地 embed（保持向后兼容）
        query_embedding = None
    return {
        "intent": intent.model_dump(),
        "query_embedding": query_embedding,
        "status": "retrieving",
    }


def route_retrieval(state: ReportState) -> list[Send]:
    """条件边：将 5 条检索路径通过 Send 并行派发。

    每条路径接收相同的 intent + user_id + 预计算的 query_embedding，
    独立执行后结果自动合并到 retrieve_results。
    """
    paths = ["documents", "tweets", "analyses", "structured", "bm25"]
    return [
        Send(
            f"retrieve_{path}",
            {
                "path": path,
                "user_id": state["user_id"],
                "intent": state["intent"],
                "query_embedding": state.get("query_embedding"),
            },
        )
        for path in paths
    ]


def retrieve_documents_node(state: RetrieveSubState) -> dict:
    """检索路径 1：用户私有文档。"""
    intent = QueryIntent(**state["intent"])
    try:
        results = retrieve_documents(
            intent,
            uuid.UUID(state["user_id"]),
            query_embedding=state.get("query_embedding"),
        )
        return {"retrieve_results": [results]}
    except Exception as e:
        return {"retrieve_results": [[]], "retrieval_errors": {"documents": f"{type(e).__name__}: {e}"}}


def retrieve_tweets_node(state: RetrieveSubState) -> dict:
    """检索路径 2：公共推文信号。"""
    intent = QueryIntent(**state["intent"])
    try:
        results = retrieve_tweets(intent, query_embedding=state.get("query_embedding"))
        return {"retrieve_results": [results]}
    except Exception as e:
        return {"retrieve_results": [[]], "retrieval_errors": {"tweets": f"{type(e).__name__}: {e}"}}


def retrieve_analyses_node(state: RetrieveSubState) -> dict:
    """检索路径 3：LLM 分析结果信号。"""
    intent = QueryIntent(**state["intent"])
    try:
        results = retrieve_analyses(intent, query_embedding=state.get("query_embedding"))
        return {"retrieve_results": [results]}
    except Exception as e:
        return {"retrieve_results": [[]], "retrieval_errors": {"analyses": f"{type(e).__name__}: {e}"}}


def retrieve_structured_node(state: RetrieveSubState) -> dict:
    """检索路径 4：PostgreSQL 结构化预测数据。"""
    intent = QueryIntent(**state["intent"])
    try:
        results = retrieve_structured(intent)
        return {"retrieve_results": [results]}
    except Exception as e:
        return {"retrieve_results": [[]], "retrieval_errors": {"structured": f"{type(e).__name__}: {e}"}}


def retrieve_bm25_node(state: RetrieveSubState) -> dict:
    """检索路径 5：PostgreSQL 全文检索（BM25）。"""
    intent = QueryIntent(**state["intent"])
    try:
        results = retrieve_bm25(intent)
        return {"retrieve_results": [results]}
    except Exception as e:
        return {"retrieve_results": [[]], "retrieval_errors": {"bm25": f"{type(e).__name__}: {e}"}}


def fuse_node(state: ReportState) -> dict:
    """节点 2：RRF 融合——将 4 路检索结果合并为统一排序。"""
    all_results = state.get("retrieve_results", [])
    if not any(all_results):
        return {"fused": [], "status": "no_results", "error": "所有检索路径返回空结果"}
    fused = reciprocal_rank_fusion(all_results, k=settings.rag_rrf_k, top_n=30)
    return {"fused": fused, "status": "reranking"}


def _apply_source_quota(
    ranked_pairs: list[tuple[int, float]],
    fused: list[dict],
    quota_map: dict[str, int],
    total_top_n: int,
) -> list[dict]:
    """按 source_type 配额挑选 rerank 结果，剩余名额按全局打分补齐。

    保证小类型（如 structured）即使全局得分低也能进入最终 top_n，
    避免章节因 source 缺失而无法生成。
    """
    counts: dict[str, int] = {k: 0 for k in quota_map}
    picked: list[dict] = []
    leftover: list[dict] = []
    for idx, _score in ranked_pairs:
        if idx >= len(fused):
            continue
        item = fused[idx]
        st = item.get("source_type", "unknown")
        if counts.get(st, 0) < quota_map.get(st, 0):
            picked.append(item)
            counts[st] = counts.get(st, 0) + 1
        else:
            leftover.append(item)
        if len(picked) >= total_top_n:
            break
    for item in leftover:
        if len(picked) >= total_top_n:
            break
        picked.append(item)
    return picked


def rerank_node(state: ReportState) -> dict:
    """节点 3：Rerank 精排——用交叉编码器对融合结果进一步排序，并按 source_type 配额裁剪。"""
    fused = state.get("fused", [])
    if not fused:
        return {"reranked": [], "status": "generating"}

    # 用 intent 中的 ticker + keywords 构造 rerank query
    intent = QueryIntent(**state["intent"]) if state.get("intent") else None
    query = state["query"]
    if intent:
        query = f"{intent.ticker} {' '.join(intent.keywords)}".strip() or query

    documents = [item["content"] for item in fused]
    # 取全量打分以便配额算法可见所有候选
    ranked_pairs = rerank(query, documents, top_n=len(documents))
    reranked = _apply_source_quota(
        ranked_pairs,
        fused,
        settings.report_rerank_quota,
        settings.reranker_top_n,
    )
    reranked = apply_time_decay(reranked)
    # 写入全局引用号：章节 prompt 与 synthesis prompt 共用同一套 [N]，与 DB citations.index 对齐
    for i, item in enumerate(reranked):
        item["global_index"] = i + 1
    return {"reranked": reranked, "status": "generating"}


def route_sections(state: ReportState) -> list[Send]:
    """条件边：将 5 个章节通过 Send 并行派发，独立调用 Signal LLM。"""
    reranked = state.get("reranked", [])
    if not reranked:
        return [Send("generate_section", {"section_def": {"name": "empty", "title": "无数据", "source_types": []}, "reranked": []})]
    return [
        Send("generate_section", {"section_def": section_def, "reranked": reranked})
        for section_def in SECTION_DEFINITIONS
    ]


def _format_evidence_line(idx: int, item: dict, content_limit: int) -> str:
    """把一条检索结果格式化为带 metadata 头的引用行。

    格式: [n] (src · @blogger · 2026-06-08 · sentiment=bullish · horizon=mid · cred=0.85 · TSLA) content...
    缺失字段自动跳过，避免冗余分隔符。
    """
    md = item.get("metadata") or {}
    src = item.get("source_type", "unknown")
    parts: list[str] = [src]
    if md.get("blogger_handle"):
        parts.append(f"@{md['blogger_handle']}")
    pub = md.get("published_at") or md.get("publish_date") or ""
    if pub:
        parts.append(str(pub)[:10])
    if md.get("sentiment"):
        parts.append(f"sentiment={md['sentiment']}")
    if md.get("horizon") and md["horizon"] != "unknown":
        parts.append(f"horizon={md['horizon']}")
    cred = md.get("credibility_score")
    if isinstance(cred, (int, float)) and cred > 0:
        parts.append(f"cred={cred:.2f}")
    if md.get("ticker"):
        parts.append(str(md["ticker"]))
    header = " · ".join(parts)
    content = (item.get("content") or "")[:content_limit]
    return f"[{idx}] ({header}) {content}"


def generate_section_node(state: SectionSubState) -> dict:
    """节点 4（并行）：单章节生成——按 source_type 筛选 reranked 文档后调用 LLM。

    容错策略：
    - LLM 调用包 try/except，并通过 ThreadPoolExecutor.future.result(timeout)
      强制 settings.report_section_timeout_sec 上限
    - 失败章节 content 留空，error 字段记录原因；synthesis 仍可继续
    """
    section_def = state["section_def"]
    reranked = state["reranked"]

    if section_def["name"] == "empty":
        return {"sections": [{
            "name": "empty",
            "title": "无数据",
            "content": "",
            "error": "检索未返回相关信息",
        }]}

    relevant = [
        item for item in reranked
        if item.get("source_type") in section_def["source_types"]
    ]
    if not relevant:
        return {"sections": [{
            "name": section_def["name"],
            "title": section_def["title"],
            "content": "",
            "error": "相关数据有限，暂无可用素材",
        }]}

    sources_lines: list[str] = []
    truncate_map = settings.report_section_truncate_by_type
    truncate_default = settings.report_section_truncate_default
    for item in relevant[: settings.report_section_max_sources]:
        limit = truncate_map.get(item.get("source_type", ""), truncate_default)
        idx = item.get("global_index", 0) or 0
        sources_lines.append(_format_evidence_line(idx, item, limit))
    sources_text = "\n".join(sources_lines)
    prompt = _SECTION_PROMPT.format(
        title=section_def["title"],
        sources=sources_text,
    )

    content = ""
    error_msg: str | None = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                lambda: get_signal_llm().invoke([{"role": "user", "content": prompt}])
            )
            response = future.result(timeout=settings.report_section_timeout_sec)
        content = response.content or ""
    except concurrent.futures.TimeoutError:
        error_msg = f"生成超时（>{settings.report_section_timeout_sec}s）"
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"

    return {"sections": [{
        "name": section_def["name"],
        "title": section_def["title"],
        "content": content,
        "error": error_msg,
    }]}


class ReportSynthesis(BaseModel):
    """综合节点结构化输出 schema。"""

    summary: str = Field(description="执行摘要，200字以内")
    consensus: Literal["strong_buy", "buy", "neutral", "sell", "strong_sell"] = Field(
        description="共识评级"
    )
    recommendation: str = Field(description="综合投资建议，100字以内")


def synthesize_node(state: ReportState) -> dict:
    """节点 5：综合——用 Report LLM 将各章节 + 原始证据合并为最终报告。

    输出包含：
    - summary: 执行摘要（≤200 字）
    - consensus: 共识评级（strong_buy ~ strong_sell）
    - recommendation: 综合投资建议
    """
    sections = state.get("sections", [])
    reranked = state.get("reranked", [])
    intent = QueryIntent(**state["intent"]) if state.get("intent") else None
    ticker = intent.ticker if intent else "UNKNOWN"

    time_range = ""
    if intent and intent.time_range_start and intent.time_range_end:
        time_range = f"{intent.time_range_start.strftime('%Y-%m-%d')} ~ {intent.time_range_end.strftime('%Y-%m-%d')}"

    sections_text = "\n\n".join(
        f"### {s['title']}\n{s['content']}"
        for s in sections
        if s.get("content") and not s.get("error")
    ) or "(所有章节均生成失败，请仅依据原始证据综合判断。)"

    # 拼装原始证据：从 reranked 取 top N 条，每条带 metadata 头（用全局引用号）
    evidence_lines: list[str] = []
    evidence_limit = settings.report_synth_truncate_default
    for item in reranked[: settings.report_synth_max_evidence]:
        idx = item.get("global_index", 0) or 0
        evidence_lines.append(_format_evidence_line(idx, item, evidence_limit))
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "(无原始证据)"

    prompt = _SYNTHESIS_PROMPT.format(
        ticker=ticker,
        time_range=time_range or "最近7天",
        sections_text=sections_text,
        evidence_text=evidence_text,
    )

    try:
        llm = get_report_llm().with_structured_output(ReportSynthesis, method="json_mode")
        synthesis = llm.invoke([{"role": "user", "content": prompt}]).model_dump()
    except Exception:
        # 综合失败时的降级：直接截取章节文本作为摘要
        synthesis = {
            "summary": sections_text[:200],
            "consensus": "neutral",
            "recommendation": "数据不足，建议观望。",
        }

    return {"synthesis": synthesis, "status": "done"}


def should_continue_after_fuse(state: ReportState) -> str:
    """条件边：融合后如果有错误（全空）则直接结束，否则继续 rerank。"""
    if state.get("error"):
        return END
    return "rerank"


# ============================================================
# 构建 StateGraph
# ============================================================

def build_report_graph() -> StateGraph:
    """构建并编译报告生成图。

    图结构：
      START → parse_intent → [Send: retrieve_documents, retrieve_tweets,
                              retrieve_analyses, retrieve_structured]
            → fuse → (条件) → rerank → generate_sections → synthesize → END
    """
    graph = StateGraph(ReportState)

    # 注册所有节点
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("retrieve_documents", retrieve_documents_node)
    graph.add_node("retrieve_tweets", retrieve_tweets_node)
    graph.add_node("retrieve_analyses", retrieve_analyses_node)
    graph.add_node("retrieve_structured", retrieve_structured_node)
    graph.add_node("retrieve_bm25", retrieve_bm25_node)
    graph.add_node("fuse", fuse_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("generate_section", generate_section_node)
    graph.add_node("synthesize", synthesize_node)

    # 定义边：顺序 + 并行 + 条件
    graph.add_edge(START, "parse_intent")
    graph.add_conditional_edges("parse_intent", route_retrieval)  # Send 并行派发
    graph.add_edge("retrieve_documents", "fuse")    # 5 路检索完成后汇聚到 fuse
    graph.add_edge("retrieve_tweets", "fuse")
    graph.add_edge("retrieve_analyses", "fuse")
    graph.add_edge("retrieve_structured", "fuse")
    graph.add_edge("retrieve_bm25", "fuse")
    graph.add_conditional_edges("fuse", should_continue_after_fuse, {"rerank": "rerank", END: END})
    graph.add_conditional_edges("rerank", route_sections)  # Send 并行派发章节
    graph.add_edge("generate_section", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


# 全局编译好的图实例（避免每次调用重新编译）
report_graph = build_report_graph()


def generate_report(user_id: str, query: str) -> dict:
    """执行完整的报告生成管线（对外主入口）。

    Args:
        user_id: 当前用户 ID
        query: 用户的自然语言查询（如"帮我分析 TSLA 本周的情况"）

    Returns:
        最终 state dict，包含 synthesis（报告结论）+ latency_ms（总耗时）
    """
    start_time = time.perf_counter()
    result = report_graph.invoke({
        "user_id": user_id,
        "query": query,
        "intent": None,
        "query_embedding": None,
        "retrieve_results": [],
        "retrieval_errors": {},
        "fused": [],
        "reranked": [],
        "sections": [],
        "synthesis": None,
        "report_id": None,
        "status": "parsing",
        "error": None,
    })
    result["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
    return result


def generate_report_streaming(user_id: str, query: str):
    """生成报告（流式）—— 每个图节点完成后 yield (node_name, node_output)。

    供 Celery 任务消费：每收到一个节点输出可以同时做两件事
      1. 发布 SSE 事件给前端
      2. 增量写入 DB（章节、citations 等）

    Returns: 生成器，迭代 (node_name: str, node_output: dict)
    """
    initial_state = {
        "user_id": user_id,
        "query": query,
        "intent": None,
        "query_embedding": None,
        "retrieve_results": [],
        "retrieval_errors": {},
        "fused": [],
        "reranked": [],
        "sections": [],
        "synthesis": None,
        "report_id": None,
        "status": "parsing",
        "error": None,
    }
    for chunk in report_graph.stream(initial_state, stream_mode="updates"):
        # chunk shape: {node_name: node_output_dict}；并行节点一次只来一个 key
        for node_name, node_output in chunk.items():
            yield node_name, node_output
