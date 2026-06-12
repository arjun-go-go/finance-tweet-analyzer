"""
BM25 全文检索器（PostgreSQL tsvector 路径）
============================================================
职责：从 doc_chunks 表的 search_vector 列执行全文检索，
     返回关键词精确匹配的结果，与向量检索互补。

与向量检索的互补关系：
- 向量检索：找"语义相似"的内容（同义词、跨语言）
- BM25 检索：找"包含关键词"的内容（精确专有名词、ticker 代码）

实现方式：
- 使用 PG 内置 ts_rank 打分（基于词频 + 文档长度归一化）
- 使用 'simple' 配置（分词已由 jieba 在写入时完成）
- 查询时同样用 jieba 分词，保证索引/查询一致性

在管线中的位置：
  parse_intent → 4 路向量检索 + **BM25 全文检索** → RRF fuse → rerank
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, text, select
from sqlalchemy.orm import Session

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.core.deps import SessionLocal
from app.models.doc_chunk import DocChunk
from app.rag.tokenizer import tokenize_for_tsquery


def retrieve_bm25(intent: QueryIntent, user_id: UUID | None = None) -> list[dict]:
    """PG 全文检索路径：对 doc_chunks.search_vector 执行 ts_rank 查询。

    Args:
        intent: 解析后的查询意图（含 ticker, keywords）
        user_id: 可选，暂未使用（BM25 搜全量 doc_chunks，不做用户隔离）

    Returns:
        统一格式结果列表，按 ts_rank 降序
    """
    query_text = f"{intent.ticker} {' '.join(intent.keywords)}".strip()
    tokenized = tokenize_for_tsquery(query_text)

    if not tokenized:
        return []

    db: Session = SessionLocal()
    try:
        # Use OR logic: any token match counts, ts_rank scores multi-hit higher
        or_query = " | ".join(tokenized.split())
        tsquery = func.to_tsquery("simple", or_query)
        rank = func.ts_rank(DocChunk.search_vector, tsquery)

        stmt = (
            select(DocChunk, rank.label("rank"))
            .where(
                DocChunk.search_vector.isnot(None),
                DocChunk.search_vector.op("@@")(tsquery),
            )
            .order_by(rank.desc())
            .limit(settings.rag_bm25_top_k)
        )

        if intent.blogger_filter:
            stmt = stmt.where(
                DocChunk.metadata_["blogger_handle"].astext.in_(intent.blogger_filter)
            )

        rows = db.execute(stmt).all()

        return [
            {
                "unique_id": f"bm25:{chunk.id}",
                "content": chunk.content,
                "source_type": (chunk.metadata_ or {}).get("source_type", "document"),
                "metadata": chunk.metadata_ or {},
                "score": float(score),
            }
            for chunk, score in rows
        ]
    finally:
        db.close()
