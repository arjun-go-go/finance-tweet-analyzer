"""Repository layer enforcing user_id isolation on vector store access."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.embeddings import Embedder
    from app.rag.vector_store import VectorHit, VectorStoreClient


@dataclass
class Chunk:
    """Lightweight DTO passed into the repository for indexing."""

    content: str
    chunk_index: int
    metadata: dict


class UserDocumentRepository:
    """Vector store repository that always enforces user_id filtering.

    Every read/write operation scopes data to a specific user, preventing
    cross-tenant data leakage at the repository layer.
    """

    COLLECTION = "user_documents"

    def __init__(self, vs: VectorStoreClient, embedder: Embedder):
        self._vs = vs
        self._embedder = embedder

    def add_chunks(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, chunks: list[Chunk]
    ) -> list[str]:
        """Embed and store chunks. Returns list of vector ids."""
        if not chunks:
            return []
        embeddings = self._embedder.embed_documents([c.content for c in chunks])
        ids = [f"{document_id}:{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "user_id": str(user_id),
                "document_id": str(document_id),
                "chunk_index": c.chunk_index,
                **c.metadata,
            }
            for c in chunks
        ]
        self._vs.add(
            self.COLLECTION, ids, [c.content for c in chunks], embeddings, metadatas
        )
        return ids

    def search(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        k: int = 15,
        extra_filter: dict | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[VectorHit]:
        """Search user's documents — user_id is ALWAYS enforced."""
        if not user_id:
            raise ValueError("user_id is required for user_documents search")
        flt: dict = {"user_id": str(user_id)}
        if extra_filter:
            if "user_id" in extra_filter and extra_filter["user_id"] != str(user_id):
                raise PermissionError("user_id filter override is forbidden")
            flt.update(extra_filter)
        emb = query_embedding if query_embedding is not None else self._embedder.embed_query(query)
        return self._vs.query(self.COLLECTION, emb, k=k, filter=flt)

    def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Delete all chunks for a document. Queries by metadata to enforce ownership."""
        # Use the vector store's query to get all chunk ids belonging to this doc
        # then delete them. Since Chroma's where filter supports "$and",
        # we filter by both user_id and document_id for safety.
        flt = {
            "$and": [
                {"user_id": str(user_id)},
                {"document_id": str(document_id)},
            ]
        }
        # Query with a high k to get all chunks (docs rarely have > 1000 chunks)
        hits = self._vs.query(
            self.COLLECTION,
            query_embedding=[0.0] * 1024,  # dummy embedding, we filter by metadata
            k=10000,
            filter=flt,
        )
        if hits:
            self._vs.delete(self.COLLECTION, [h.id for h in hits])
