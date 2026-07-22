"""Elasticsearch BM25 keyword retriever."""

from __future__ import annotations

from uuid import UUID

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.rag.keyword_store import get_keyword_store


def _query_text(intent: QueryIntent) -> str:
    return f"{intent.ticker} {' '.join(intent.keywords)}".strip()


def retrieve_es_bm25(intent: QueryIntent, user_id: UUID | None = None) -> list[dict]:
    """Elasticsearch keyword/BM25 retrieval path."""
    query_text = _query_text(intent)
    if not query_text:
        return []
    return get_keyword_store().search_with_source_quotas(
        query_text=query_text,
        source_quotas=settings.es_source_type_quota,
        user_id=user_id,
        blogger_filter=intent.blogger_filter,
        time_range_start=intent.time_range_start,
        time_range_end=intent.time_range_end,
    )


def retrieve_bm25(intent: QueryIntent, user_id: UUID | None = None) -> list[dict]:
    """Keyword retrieval entrypoint backed by Elasticsearch only."""
    try:
        return retrieve_es_bm25(intent, user_id=user_id)
    except Exception:
        return []
