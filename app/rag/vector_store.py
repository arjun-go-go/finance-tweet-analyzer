"""
RAG 向量存储抽象层
============================================================
职责：
  1. 定义 VectorStoreClient Protocol（增删查接口），屏蔽底层存储差异
  2. 实现 Chroma 后端适配器（ChromaVectorStore）
  3. 管理两个 collection：
     - user_documents：用户上传的私有文档（按 user_id 隔离）
     - public_signals：系统采集的推文/分析结果（公共可查）

设计决策：
- 两个 collection 分离：隐私隔离 + 不同的 metadata schema
- add() 方法绕过 LangChain 的 add_texts()：因为我们已有预计算的
  embedding（通过 embed_with_dedupe 去重后得到），无需 LangChain 再调一次 API，
  所以直接走底层 chromadb collection.add()
- query() 使用 LangChain 的 similarity_search_by_vector_with_relevance_scores：
  传入预计算的 query embedding，获得带相关性分数的结果
- HNSW + cosine：适合动态写入场景，召回率高，无需重建索引
- Protocol 模式：未来切换 Milvus 只需新增一个实现类

在管线中的位置：
  写入：chunk → embed → **vector store add**
  检索：query embed → **vector store query** → rerank → 生成
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from langchain_chroma import Chroma

from app.core.config import settings
from app.rag.embeddings import get_embedder

_VS_INIT_LOCK = threading.Lock()


def _scrub_meta(meta: dict) -> dict:
    """Remove unsupported values from metadata — ChromaDB only accepts str/int/float/bool."""
    return {
        k: v for k, v in meta.items()
        if v is not None and isinstance(v, (str, int, float, bool))
    }


@dataclass
class VectorHit:
    """向量检索单条命中结果，包含 ID、相似度分数、原始文本和元数据。"""

    id: str
    score: float
    metadata: dict
    content: str = ""


class VectorStoreClient(Protocol):
    """向量存储统一接口 Protocol，解耦具体后端实现。

    任何实现此接口的类（Chroma / Milvus / FAISS）均可无缝替换。
    """

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

    def count(self, collection: str) -> int: ...


class ChromaVectorStore:
    """基于 langchain_chroma.Chroma 的向量存储实现。

    每个 collection 使用 HNSW 索引 + cosine 距离度量，
    适合动态写入（推文/分析持续入库）且高召回的场景。
    """

    # 两个 collection：user_documents（私有文档） / public_signals（公共信号）
    COLLECTIONS = ("user_documents", "public_signals")

    def __init__(self, persist_dir: str):
        embedding_fn = get_embedder()
        self._stores: dict[str, Chroma] = {}
        for name in self.COLLECTIONS:
            self._stores[name] = Chroma(
                collection_name=name,
                persist_directory=persist_dir,
                embedding_function=embedding_fn,
                collection_metadata={"hnsw:space": "cosine"},
            )

    def _col(self, collection: str) -> Chroma:
        return self._stores[collection]

    def add(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        """写入预计算的向量到指定 collection。

        注意：绕过 LangChain 的 add_texts()，直接操作底层 chromadb collection，
        因为我们已通过 embed_with_dedupe 得到了向量，无需 LangChain 再调 API。
        """
        cleaned = [_scrub_meta(m) for m in metadatas]
        self._col(collection)._collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=cleaned,
        )

    @staticmethod
    def _build_chroma_filter(filter: dict | None) -> dict | None:
        """将多条件 filter 转为 ChromaDB 要求的 {"$and": [...]} 格式。

        支持两种值形式：
          - 简单值: {"source_type": "tweet"} → {"source_type": "tweet"}
          - 运算符: {"ticker": {"$contains": "NVDA"}} → {"ticker": {"$contains": "NVDA"}}
        多条件时包裹为 $and。
        """
        if not filter:
            return None
        if len(filter) == 1:
            return filter
        return {"$and": [{k: v} for k, v in filter.items()]}

    def query(
        self,
        collection: str,
        query_embedding: list[float],
        k: int,
        filter: dict | None = None,
    ) -> list[VectorHit]:
        """向量相似度检索，支持 metadata 过滤（如 source_type、ticker）。"""
        chroma_filter = self._build_chroma_filter(filter)
        results = self._col(collection).similarity_search_by_vector_with_relevance_scores(
            embedding=query_embedding,
            k=k,
            filter=chroma_filter,
        )
        return [
            VectorHit(id=doc.id or "", score=score, metadata=doc.metadata, content=doc.page_content)
            for doc, score in results
        ]

    def delete(self, collection: str, ids: list[str]) -> None:
        """按 ID 批量删除向量（用于 GC 任务清理已删除文档的向量）。"""
        if ids:
            self._col(collection).delete(ids=ids)

    def count(self, collection: str) -> int:
        """返回 collection 中的向量总数（用于监控/健康检查）。"""
        col = self._col(collection)
        return col._collection.count()


_vector_store_singleton: VectorStoreClient | None = None


def get_vector_store() -> VectorStoreClient:
    """向量存储单例工厂，根据 settings.vector_backend 选择后端实现。

    使用 threading.Lock 保护初始化路径：LangGraph Send fan-out 会让多个
    检索节点在不同线程并发首次访问，chromadb 客户端在并发初始化时会
    抛 'Could not connect to tenant default_tenant'，所以必须串行化首次构造。
    """
    global _vector_store_singleton
    if _vector_store_singleton is not None:
        return _vector_store_singleton
    with _VS_INIT_LOCK:
        if _vector_store_singleton is not None:
            return _vector_store_singleton
        backend = settings.vector_backend
        if backend == "chroma":
            _vector_store_singleton = ChromaVectorStore(
                persist_dir=settings.chroma_persist_dir
            )
        elif backend == "milvus":
            raise NotImplementedError("Milvus adapter ships in a later plan")
        else:
            raise ValueError(f"Unknown vector backend: {backend}")
        return _vector_store_singleton
