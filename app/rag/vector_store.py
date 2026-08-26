"""Milvus vector storage for the public-signal RAG pipeline.

The protocol keeps indexing and retrieval independent from the client library.
Production has one supported backend so local and shared indexes cannot drift.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any
from typing import Protocol

from app.core.config import settings

_VS_INIT_LOCK = threading.Lock()


def _scrub_meta(meta: dict) -> dict:
    """Keep metadata values supported by the fixed Milvus JSON payload."""
    return {
        k: v for k, v in meta.items()
        if v is not None and isinstance(v, (str, int, float, bool))
    }


def _stringify_meta_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


@dataclass
class VectorHit:
    """向量检索单条命中结果，包含 ID、相似度分数、原始文本和元数据。"""

    id: str
    score: float
    metadata: dict
    content: str = ""


class VectorStoreClient(Protocol):
    """Storage interface used by RAG indexing and retrieval."""

    def add(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None: ...

    def query(
        self,
        collection: str,
        query_embedding: list[float],
        k: int,
        filter: dict | None = None,
    ) -> list[VectorHit]: ...

    def delete(self, collection: str, ids: list[str]) -> None: ...

    def delete_where(self, collection: str, filter: dict) -> None: ...

    def count(self, collection: str) -> int: ...


class MilvusVectorStore:
    """Milvus/Zilliz implementation of VectorStoreClient.

    Logical collections are mapped to physical Milvus collection names using
    settings.milvus_collection_prefix.
    """

    COLLECTIONS = ("public_signals",)
    VECTOR_FIELD = "vector"
    CONTENT_FIELD = "content"
    METADATA_FIELD = "metadata"

    def __init__(
        self,
        *,
        uri: str,
        token: str,
        db_name: str,
        collection_prefix: str,
        dimension: int,
        timeout_sec: float = 30.0,
    ):
        if not uri:
            raise ValueError("MILVUS_URI must be set when VECTOR_BACKEND=milvus")
        if not token:
            raise ValueError("MILVUS_TOKEN must be set when VECTOR_BACKEND=milvus")
        if not collection_prefix:
            raise ValueError("MILVUS_COLLECTION_PREFIX must not be empty")

        from pymilvus import MilvusClient

        self._client = MilvusClient(uri=uri, token=token, db_name=db_name, timeout=timeout_sec)
        self._collection_prefix = collection_prefix.strip("_")
        self._dimension = dimension
        self._timeout_sec = timeout_sec
        self._ensured: set[str] = set()
        self._collection_fields: dict[str, set[str]] = {}

        for collection in self.COLLECTIONS:
            self._ensure_collection(collection)

    def _physical_name(self, collection: str) -> str:
        if collection not in self.COLLECTIONS:
            raise KeyError(f"Unknown vector collection: {collection}")
        return f"{self._collection_prefix}_{collection}"

    def _ensure_collection(self, collection: str) -> None:
        physical_name = self._physical_name(collection)
        if physical_name in self._ensured:
            return
        if self._client.has_collection(physical_name):
            description = self._client.describe_collection(physical_name)
            self._collection_fields[physical_name] = {
                str(field.get("name")) for field in description.get("fields", [])
            }
            self._client.load_collection(physical_name)
            self._ensured.add(physical_name)
            return

        from pymilvus import DataType, MilvusClient

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=512)
        schema.add_field(field_name=self.VECTOR_FIELD, datatype=DataType.FLOAT_VECTOR, dim=self._dimension)
        schema.add_field(field_name=self.CONTENT_FIELD, datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name=self.METADATA_FIELD, datatype=DataType.JSON)
        schema.add_field(field_name="source_type", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="source_id", datatype=DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="index_stage", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="ticker", datatype=DataType.VARCHAR, max_length=512)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name=self.VECTOR_FIELD,
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._client.create_collection(
            collection_name=physical_name,
            schema=schema,
            index_params=index_params,
            timeout=self._timeout_sec,
        )
        self._client.load_collection(physical_name)
        self._collection_fields[physical_name] = {
            "id",
            self.VECTOR_FIELD,
            self.CONTENT_FIELD,
            self.METADATA_FIELD,
            "source_type",
            "source_id",
            "index_stage",
            "ticker",
        }
        self._ensured.add(physical_name)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @classmethod
    def _condition_to_expr(cls, field: str, value: Any) -> str:
        if isinstance(value, dict):
            if "$contains" in value:
                text = cls._escape(str(value["$contains"]))
                return f'{field} like "%{text}%"'
            if "$eq" in value:
                return cls._condition_to_expr(field, value["$eq"])
            raise ValueError(f"Unsupported Milvus filter operator for {field}: {value}")
        if isinstance(value, bool):
            return f"{field} == {str(value).lower()}"
        if isinstance(value, (int, float)):
            return f"{field} == {value}"
        return f'{field} == "{cls._escape(str(value))}"'

    @classmethod
    def _filter_to_expr(cls, filter: dict | None) -> str:
        if not filter:
            return ""
        if "$and" in filter:
            parts = [cls._filter_to_expr(part) for part in filter["$and"] if part]
            return " and ".join(f"({part})" for part in parts if part)
        return " and ".join(
            cls._condition_to_expr(field, value)
            for field, value in filter.items()
        )

    @staticmethod
    def _entity_to_hit(entity: dict, fallback_id: str, fallback_score: float) -> VectorHit:
        metadata = entity.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        return VectorHit(
            id=str(entity.get("id") or fallback_id),
            score=float(fallback_score),
            metadata=metadata,
            content=str(entity.get("content") or ""),
        )

    def add(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        physical_name = self._physical_name(collection)
        self._ensure_collection(collection)
        cleaned = [_scrub_meta(m) for m in metadatas]
        rows = []
        for i in range(len(ids)):
            row = {
                "id": ids[i],
                self.VECTOR_FIELD: embeddings[i],
                self.CONTENT_FIELD: texts[i],
                self.METADATA_FIELD: cleaned[i],
                "source_type": _stringify_meta_value(cleaned[i].get("source_type")),
                "ticker": _stringify_meta_value(cleaned[i].get("ticker") or cleaned[i].get("tickers")),
            }
            row["source_id"] = _stringify_meta_value(cleaned[i].get("source_id"))
            row["index_stage"] = _stringify_meta_value(cleaned[i].get("index_stage"))
            rows.append(row)
        self._client.upsert(collection_name=physical_name, data=rows, timeout=self._timeout_sec)

    def query(
        self,
        collection: str,
        query_embedding: list[float],
        k: int,
        filter: dict | None = None,
    ) -> list[VectorHit]:
        physical_name = self._physical_name(collection)
        self._ensure_collection(collection)
        results = self._client.search(
            collection_name=physical_name,
            data=[query_embedding],
            anns_field=self.VECTOR_FIELD,
            limit=k,
            filter=self._filter_to_expr(filter),
            output_fields=["id", self.CONTENT_FIELD, self.METADATA_FIELD],
            search_params={"metric_type": "COSINE"},
            timeout=self._timeout_sec,
        )
        hits: list[VectorHit] = []
        for item in results[0] if results else []:
            if isinstance(item, dict):
                entity = item.get("entity") or {}
                hits.append(self._entity_to_hit(
                    entity,
                    fallback_id=str(item.get("id") or ""),
                    fallback_score=float(item.get("distance") or item.get("score") or 0.0),
                ))
            else:
                entity = getattr(item, "entity", {}) or {}
                if not isinstance(entity, dict):
                    entity = dict(entity)
                hits.append(self._entity_to_hit(
                    entity,
                    fallback_id=str(getattr(item, "id", "") or ""),
                    fallback_score=float(getattr(item, "distance", 0.0) or getattr(item, "score", 0.0) or 0.0),
                ))
        return hits

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        self._client.delete(
            collection_name=self._physical_name(collection),
            ids=ids,
            timeout=self._timeout_sec,
        )

    def delete_where(self, collection: str, filter: dict) -> None:
        expression = self._filter_to_expr(filter)
        if not expression:
            raise ValueError("Vector delete filter is required")
        self._client.delete(
            collection_name=self._physical_name(collection),
            filter=expression,
            timeout=self._timeout_sec,
        )

    def count(self, collection: str) -> int:
        physical_name = self._physical_name(collection)
        self._ensure_collection(collection)
        stats = self._client.get_collection_stats(physical_name)
        value = stats.get("row_count", stats.get("num_entities", 0))
        return int(value)


_vector_store_singleton: VectorStoreClient | None = None


def get_vector_store() -> VectorStoreClient:
    """Return the process-wide Milvus client.

    The lock serializes first construction when LangGraph retrieval nodes fan
    out across threads.
    """
    global _vector_store_singleton
    if _vector_store_singleton is not None:
        return _vector_store_singleton
    with _VS_INIT_LOCK:
        if _vector_store_singleton is not None:
            return _vector_store_singleton
        if settings.vector_backend.lower() != "milvus":
            raise ValueError("VECTOR_BACKEND must be 'milvus'")
        _vector_store_singleton = MilvusVectorStore(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            db_name=settings.milvus_db_name,
            collection_prefix=settings.milvus_collection_prefix,
            dimension=settings.embedding_dim,
            timeout_sec=settings.milvus_timeout_sec,
        )
        return _vector_store_singleton
