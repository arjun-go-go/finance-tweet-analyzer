"""
分析结果信号检索器
============================================================
职责：从 public_signals collection 中检索与 ticker 相关的 LLM 分析结果。

特点：
- 公共数据：分析结果由系统自动生成，所有用户可见
- metadata 过滤：source_type='analysis' + ticker（可选）
- 与 tweet_retriever 结构相似，但 source_type 不同

数据来源：系统对推文执行 LLM 分析后，通过 embed_signal_task 向量化入库
metadata 包含：sentiment（情感）、horizon（投资周期）、credibility_score（可信度）
"""

from __future__ import annotations

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.rag.embeddings import get_embedder
from app.rag.vector_store import get_vector_store


def retrieve_analyses(
    intent: QueryIntent,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    """检索 public_signals 中的分析结果信号，返回统一格式结果。"""
    vs = get_vector_store()

    query_text = f"{intent.ticker} {' '.join(intent.keywords)}".strip()
    if query_embedding is None:
        query_embedding = get_embedder().embed_query(query_text)

    # metadata 过滤：限定 source_type='analysis'
    # ticker 不做过滤——向量语义已包含 ticker 信息
    flt: dict = {"source_type": "analysis"}
    if intent.blogger_filter:
        flt["blogger_handle"] = {"$in": intent.blogger_filter}
    if intent.time_range_start or intent.time_range_end:
        ts_filter: dict = {}
        if intent.time_range_start:
            ts_filter["$gte"] = intent.time_range_start.isoformat()
        if intent.time_range_end:
            ts_filter["$lte"] = intent.time_range_end.isoformat()
        flt["published_at"] = ts_filter

    hits = vs.query(
        "public_signals",
        query_embedding=query_embedding,
        k=settings.rag_top_k_per_path,
        filter=flt,
    )

    return [
        {
            "unique_id": f"analysis:{hit.id}",
            "content": hit.content,
            "source_type": "analysis",
            "metadata": hit.metadata,
            "score": hit.score,
        }
        for hit in hits
    ]
