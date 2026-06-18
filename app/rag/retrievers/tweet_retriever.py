"""
推文信号检索器
============================================================
职责：从 public_signals collection 中检索与 ticker 相关的推文。

特点：
- 公共数据：不做 user_id 隔离，所有用户可见所有推文信号
- metadata 过滤：source_type='tweet' + ticker（可选）
- 向量检索：将 intent 中的 ticker + keywords 组合为 query text，embed 后做相似度检索
- 上下文扩展：向量命中 chunk 后，通过 source_id 反查原始推文全文，
  确保 LLM 获得完整上下文而非切块片段

数据来源：系统通过 embed_signal_task 将采集的推文向量化入库
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.core.deps import SessionLocal
from app.models.tweet import Tweet
from app.rag.embeddings import get_embedder
from app.rag.vector_store import get_vector_store


def retrieve_tweets(
    intent: QueryIntent,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    """检索 public_signals 中的推文信号，返回统一格式结果（含原文扩展）。"""
    vs = get_vector_store()

    # 构造查询文本：ticker + 用户关键词
    query_text = f"{intent.ticker} {' '.join(intent.keywords)}".strip()
    if query_embedding is None:
        query_embedding = get_embedder().embed_query(query_text)

    # metadata 过滤：限定 source_type='tweet'
    flt: dict = {"source_type": "tweet"}
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

    if not hits:
        return []

    # 上下文扩展：通过 source_id 反查原始推文全文
    # 按 source_id 去重（同一推文的多个 chunk 命中时只保留分数最高的）
    seen_source_ids: dict[str, int] = {}
    deduped_hits = []
    for i, hit in enumerate(hits):
        sid = hit.metadata.get("source_id", "")
        if sid and sid not in seen_source_ids:
            seen_source_ids[sid] = i
            deduped_hits.append(hit)

    # 批量查询原始推文
    source_ids = [h.metadata["source_id"] for h in deduped_hits if h.metadata.get("source_id")]
    full_texts: dict[str, str] = {}
    if source_ids:
        db = SessionLocal()
        try:
            rows = db.execute(
                select(Tweet.id, Tweet.content).where(
                    Tweet.id.in_([UUID(sid) for sid in source_ids])
                )
            ).all()
            full_texts = {str(r.id): r.content for r in rows if r.content}
        finally:
            db.close()

    return [
        {
            "unique_id": f"tweet:{hit.metadata.get('source_id', hit.id)}",
            "content": full_texts.get(hit.metadata.get("source_id", ""), hit.content),
            "source_type": "tweet",
            "metadata": hit.metadata,
            "score": hit.score,
        }
        for hit in deduped_hits
    ]
