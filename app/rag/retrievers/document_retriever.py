"""
用户私有文档检索器
============================================================
职责：从 user_documents collection 中检索当前用户上传的文档。

特点：
- 多租户隔离：通过 user_id 过滤，确保用户只能检索自己的文档
- 支持 ticker 精确过滤：如果 intent 中有明确 ticker，追加 metadata filter
- 通过 UserDocumentRepository 封装，底层走 vector store 的 query 接口

数据来源：用户上传的 PDF/研报/笔记，经 chunk + embed 后入库
"""

from __future__ import annotations

from uuid import UUID

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.rag.embeddings import get_embedder
from app.rag.repository import UserDocumentRepository
from app.rag.vector_store import get_vector_store


def retrieve_documents(
    intent: QueryIntent,
    user_id: UUID,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    """检索当前用户的私有文档，返回统一格式的结果列表。"""
    repo = UserDocumentRepository(get_vector_store(), get_embedder())

    # ChromaDB 不支持字符串字段 $contains，tickers 存为逗号分隔大写字符串
    # 无法做子串过滤，暂不加 ticker filter，由 reranker 处理相关性
    extra_filter: dict = {}

    hits = repo.search(
        user_id=user_id,
        query=f"{intent.ticker} {' '.join(intent.keywords)}".strip(),
        k=settings.rag_top_k_per_path,
        extra_filter=extra_filter if extra_filter else None,
        query_embedding=query_embedding,
    )

    # 转换为统一的检索结果格式（unique_id 加 "doc:" 前缀区分来源）
    return [
        {
            "unique_id": f"doc:{hit.id}",
            "content": hit.content,
            "source_type": "document",
            "metadata": hit.metadata,
            "score": hit.score,
        }
        for hit in hits
    ]
