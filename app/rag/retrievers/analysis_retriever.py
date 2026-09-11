"""
逐标的观点检索器
============================================================
职责：从 public_signals collection 中检索逐标的观点 claim。

特点：
- 公共数据：分析结果由系统自动生成，所有用户可见
- metadata 过滤：source_type='claim' + 精确 ticker（可选）
- 与 tweet_retriever 结构相似，但 source_type 不同

数据来源：系统对推文执行 LLM 分析后，通过 embed_signal_task 向量化入库
metadata 包含：direction（方向）、horizon（投资周期）、claim_type（观点类型）
"""

from __future__ import annotations

from datetime import datetime

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.rag.embeddings import get_embedder
from app.rag.vector_store import get_vector_store


def retrieve_analyses(
    intent: QueryIntent,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    """检索 public_signals 中的逐标的观点，返回统一格式结果。"""
    vs = get_vector_store()

    query_text = f"{intent.ticker} {' '.join(intent.keywords)}".strip()
    if query_embedding is None:
        query_embedding = get_embedder().embed_query(query_text)

    # Milvus has first-class fields for source_type/ticker; the remaining claim
    # attributes live in JSON metadata and are filtered after vector recall.
    flt: dict = {"source_type": "claim"}
    if intent.ticker and intent.ticker != "UNKNOWN":
        flt["ticker"] = intent.ticker.upper()
    hits = vs.query(
        "public_signals",
        query_embedding=query_embedding,
        k=settings.rag_top_k_per_path * 4,
        filter=flt,
    )

    allowed_bloggers = {handle.lower() for handle in intent.blogger_filter}

    def allowed(hit) -> bool:
        metadata = hit.metadata or {}
        if intent.sentiment_filter and metadata.get("direction") not in intent.sentiment_filter:
            return False
        if intent.horizon_filter and metadata.get("horizon") not in intent.horizon_filter:
            return False
        if allowed_bloggers and str(metadata.get("blogger_handle") or "").lower() not in allowed_bloggers:
            return False
        published_raw = str(metadata.get("published_at") or "")
        if published_raw and (intent.time_range_start or intent.time_range_end):
            try:
                published_at = datetime.fromisoformat(published_raw)
            except ValueError:
                return False
            if intent.time_range_start and published_at < intent.time_range_start:
                return False
            if intent.time_range_end and published_at > intent.time_range_end:
                return False
        return True

    hits = [hit for hit in hits if allowed(hit)][:settings.rag_top_k_per_path]

    return [
        {
            "unique_id": f"claim:{hit.metadata.get('source_id') or hit.id}",
            "content": hit.content,
            "source_type": "claim",
            "metadata": hit.metadata,
            "score": hit.score,
        }
        for hit in hits
    ]
