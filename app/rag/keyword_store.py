"""Elasticsearch keyword/BM25 read model for RAG chunks.

PostgreSQL remains the source of truth. This module stores and queries a
searchable copy of ``doc_chunks`` for keyword retrieval.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from loguru import logger

from app.core.config import settings


def build_rag_index_body() -> dict[str, Any]:
    """Return the approved Elasticsearch index settings and mapping."""
    return {
        "settings": {
            "analysis": {
                "analyzer": {
                    "ik_smart_analyzer": {
                        "type": "custom",
                        "tokenizer": "ik_smart",
                    },
                    "ik_max_word_analyzer": {
                        "type": "custom",
                        "tokenizer": "ik_max_word",
                    },
                }
            }
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "source_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "visibility": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "content": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                },
                "title": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                    "fields": {
                        "keyword": {"type": "keyword"},
                    },
                },
                "url": {"type": "keyword"},
                "ticker": {"type": "keyword"},
                "tickers": {"type": "keyword"},
                "blogger_handle": {"type": "keyword"},
                "index_stage": {"type": "keyword"},
                "published_at": {"type": "date"},
                "created_at": {"type": "date"},
                "metadata": {
                    "type": "object",
                    "enabled": True,
                },
            }
        },
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _split_tickers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).split(",")
    tickers: list[str] = []
    for item in items:
        if isinstance(item, dict):
            symbol = item.get("symbol")
        else:
            symbol = item
        normalized = str(symbol or "").strip().upper()
        if normalized:
            tickers.append(normalized)
    return tickers


def chunk_to_es_document(chunk: Any, user_id: UUID | str | None = None) -> dict[str, Any]:
    """Convert a DocChunk-like object to an Elasticsearch document."""
    metadata = dict(getattr(chunk, "metadata_", None) or {})
    source_type = metadata.get("source_type", "document")
    tickers = _split_tickers(metadata.get("tickers") or metadata.get("ticker"))
    chunk_id = str(getattr(chunk, "id"))
    document_id = getattr(chunk, "document_id", None)
    source_id = (
        metadata.get("source_id")
        or metadata.get("tweet_id")
        or metadata.get("analysis_id")
        or metadata.get("document_id")
        or document_id
    )
    effective_user_id = user_id or metadata.get("user_id")
    visibility = metadata.get("visibility") or ("private" if effective_user_id else "public")

    return {
        "chunk_id": chunk_id,
        "document_id": str(document_id) if document_id else None,
        "source_id": str(source_id) if source_id else None,
        "user_id": str(effective_user_id) if effective_user_id else None,
        "visibility": visibility,
        "source_type": source_type,
        "chunk_index": getattr(chunk, "chunk_index", 0),
        "content": getattr(chunk, "content", "") or "",
        "title": metadata.get("title") or "",
        "url": metadata.get("source_uri") or metadata.get("url") or "",
        "ticker": tickers[0] if tickers else (metadata.get("ticker") or ""),
        "tickers": tickers,
        "blogger_handle": metadata.get("blogger_handle") or "",
        "published_at": metadata.get("published_at") or metadata.get("publish_date"),
        "created_at": _iso(getattr(chunk, "created_at", None)),
        "metadata": metadata,
    }


class ElasticsearchKeywordStore:
    """Thin wrapper around Elasticsearch for RAG keyword retrieval."""

    def __init__(
        self,
        *,
        client: Elasticsearch | None = None,
        index_name: str | None = None,
    ) -> None:
        self._client = client or build_elasticsearch_client()
        self.index_name = index_name or settings.es_rag_index

    def versioned_index_name(self, version: int = 1) -> str:
        return f"{self.index_name}_v{version}"

    def health_check(self) -> bool:
        return bool(self._client.ping())

    def index_exists(self) -> bool:
        return bool(self._client.indices.exists_alias(name=self.index_name))

    def current_write_index(self) -> str | None:
        try:
            aliases = self._client.indices.get_alias(name=self.index_name)
        except Exception:
            return None
        for index, data in (aliases or {}).items():
            if self.index_name in (data.get("aliases") or {}):
                return index
        return None

    def create_index_if_missing(self) -> bool:
        if self.index_exists():
            return False
        physical_index = self.versioned_index_name(1)
        body = build_rag_index_body()
        self._client.indices.create(
            index=physical_index,
            settings=body["settings"],
            mappings=body["mappings"],
        )
        if self._client.indices.exists(index=self.index_name):
            self._client.reindex(
                source={"index": self.index_name},
                dest={"index": physical_index},
                refresh=True,
                wait_for_completion=True,
            )
            self._client.indices.delete(index=self.index_name)
        self._client.indices.update_aliases(
            body={
                "actions": [
                    {"add": {"index": physical_index, "alias": self.index_name}},
                ]
            }
        )
        return True

    def switch_alias(self, new_index: str) -> dict[str, Any]:
        current_index = self.current_write_index()
        actions: list[dict[str, Any]] = []
        if current_index:
            actions.append({"remove": {"index": current_index, "alias": self.index_name}})
        actions.append({"add": {"index": new_index, "alias": self.index_name}})
        return self._client.indices.update_aliases(body={"actions": actions})

    def _build_query(
        self,
        *,
        query_text: str,
        user_id: UUID | str | None = None,
        blogger_filter: list[str] | None = None,
        time_range_start: datetime | date | None = None,
        time_range_end: datetime | date | None = None,
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if user_id:
            filters.append(
                {
                    "bool": {
                        "should": [
                            {"term": {"visibility": "public"}},
                            {
                                "bool": {
                                    "must": [
                                        {"term": {"visibility": "private"}},
                                        {"term": {"user_id": str(user_id)}},
                                    ]
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        else:
            filters.append({"term": {"visibility": "public"}})

        if blogger_filter:
            filters.append({"terms": {"blogger_handle": blogger_filter}})
        if time_range_start:
            filters.append({"range": {"published_at": {"gte": _iso(time_range_start)}}})
        if time_range_end:
            filters.append({"range": {"published_at": {"lte": _iso(time_range_end)}}})

        return {
            "function_score": {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query_text,
                                    "fields": [
                                        "ticker^8",
                                        "tickers^8",
                                        "title^4",
                                        "blogger_handle^3",
                                        "content^2",
                                    ],
                                    "type": "best_fields",
                                    "operator": "or",
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
                "functions": [
                    {"filter": {"term": {"index_stage": "analysis"}}, "weight": 1.25},
                    {"filter": {"term": {"index_stage": "raw"}}, "weight": 1.05},
                    {
                        "gauss": {
                            "published_at": {
                                "origin": "now",
                                "scale": "14d",
                                "decay": 0.5,
                            }
                        },
                        "weight": 1.15,
                    },
                ],
                "score_mode": "sum",
                "boost_mode": "multiply",
            }
        }

    def _highlight(self) -> dict[str, Any]:
        return {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {
                "content": {"fragment_size": 160, "number_of_fragments": 3},
                "title": {"fragment_size": 120, "number_of_fragments": 1},
            },
        }

    def _results_from_response(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            chunk_id = str(source.get("chunk_id") or hit.get("_id") or "")
            metadata = dict(source.get("metadata") or {})
            metadata["chunk_id"] = chunk_id
            if hit.get("highlight"):
                metadata["highlight"] = hit["highlight"]
            results.append(
                {
                    "unique_id": f"es:{chunk_id}",
                    "content": source.get("content") or "",
                    "source_type": source.get("source_type") or metadata.get("source_type", "document"),
                    "metadata": metadata,
                    "score": float(hit.get("_score") or 0.0),
                }
            )
        return results

    def search(
        self,
        *,
        query_text: str,
        user_id: UUID | str | None = None,
        blogger_filter: list[str] | None = None,
        time_range_start: datetime | date | None = None,
        time_range_end: datetime | date | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        query = self._build_query(
            query_text=query_text,
            user_id=user_id,
            blogger_filter=blogger_filter,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
        )
        response = self._client.search(
            index=self.index_name,
            query=query,
            size=top_k or settings.rag_bm25_top_k,
            highlight=self._highlight(),
        )
        return self._results_from_response(response)

    def debug_search(
        self,
        *,
        query_text: str,
        user_id: UUID | str | None = None,
        blogger_filter: list[str] | None = None,
        time_range_start: datetime | date | None = None,
        time_range_end: datetime | date | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        query = self._build_query(
            query_text=query_text,
            user_id=user_id,
            blogger_filter=blogger_filter,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
        )
        response = self._client.search(
            index=self.index_name,
            query=query,
            size=top_k or settings.rag_bm25_top_k,
            highlight=self._highlight(),
        )
        return {
            "index": self.index_name,
            "query": query,
            "raw_hits": response.get("hits", {}).get("hits", []),
            "results": self._results_from_response(response),
        }

    def bulk_upsert_documents(self, documents: Iterable[dict[str, Any]]) -> tuple[int, list[Any]]:
        actions = [
            {
                "_op_type": "index",
                "_index": self.index_name,
                "_id": doc["chunk_id"],
                "_source": doc,
            }
            for doc in documents
        ]
        if not actions:
            return 0, []
        return bulk(
            self._client,
            actions,
            chunk_size=settings.es_bulk_chunk_size,
            raise_on_error=False,
        )

    def delete_by_document_id(self, document_id: UUID | str) -> dict[str, Any]:
        return self._client.delete_by_query(
            index=self.index_name,
            query={"term": {"document_id": str(document_id)}},
            conflicts="proceed",
        )

    def delete_by_source(self, source_type: str, source_id: UUID | str) -> dict[str, Any]:
        return self._client.delete_by_query(
            index=self.index_name,
            query={
                "bool": {
                    "filter": [
                        {"term": {"source_type": source_type}},
                        {"term": {"source_id": str(source_id)}},
                    ]
                }
            },
            conflicts="proceed",
            refresh=True,
        )


def build_elasticsearch_client() -> Elasticsearch:
    if not settings.elasticsearch_url:
        raise RuntimeError("ELASTICSEARCH_URL is required for Elasticsearch keyword retrieval")

    kwargs: dict[str, Any] = {
        "request_timeout": settings.es_request_timeout_sec,
    }
    if settings.elasticsearch_username or settings.elasticsearch_password:
        kwargs["basic_auth"] = (
            settings.elasticsearch_username,
            settings.elasticsearch_password,
        )
    return Elasticsearch(settings.elasticsearch_url, **kwargs)


@lru_cache(maxsize=1)
def get_keyword_store() -> ElasticsearchKeywordStore:
    logger.debug("[KeywordStore] initialize Elasticsearch keyword store index={}", settings.es_rag_index)
    return ElasticsearchKeywordStore()
