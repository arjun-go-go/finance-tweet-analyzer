"""
RAG 向量化模块
============================================================
职责：
  1. 提供统一的 Embedder 接口（Protocol 模式），方便测试时 mock
  2. 封装 DashScope text-embedding 模型调用（通过 langchain-community）
  3. 提供 content-hash 去重逻辑，避免重复内容重复调用 API 浪费 token

设计决策：
- 使用 Protocol 而非继承：DashScopeEmbeddings 本身不继承我们的类，
  但它 duck-typing 满足 embed_documents / embed_query 接口
- embed_with_dedupe 是核心优化：通过 SHA256 哈希比对已入库内容，
  跳过已有向量的文本，仅对新内容调用 embedding API
- 批内去重（in-batch dedupe）：同一批提交中如果有重复文本，
  只 embed 一次然后复制向量到所有相同位置

在管线中的位置：
  chunk → **embed** → vector store
  检索时：用户 query → embed_query → 向量相似度检索
"""

from __future__ import annotations

import functools
import hashlib
from typing import Protocol

from langchain_community.embeddings import DashScopeEmbeddings
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.doc_chunk import DocChunk


class Embedder(Protocol):
    """最小 Embedder 接口，DashScopeEmbeddings 隐式满足此协议。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def embed_with_dedupe(
    texts: list[str],
    *,
    embedder: Embedder,
    session: Session,
) -> tuple[list[list[float] | None], list[str | None], list[str]]:
    """带 content-hash 去重的批量向量化。

    去重逻辑：
      1. 对每段文本计算 SHA256 哈希
      2. 查 doc_chunks 表中是否已有相同 hash 且已分配 vector_id
      3. 命中 → 复用已有 vector_id，跳过 embedding API 调用
      4. 未命中 → 调用 embedder.embed_documents 生成新向量

    Returns:
        三元组 (embeddings, vector_ids, hashes)，长度与输入 texts 一致：
        - 命中时：embeddings[i] = None, vector_ids[i] = 已有 ID
        - 未命中：embeddings[i] = 新向量, vector_ids[i] = None（由调用方写入后回填）
    """
    if not texts:
        return [], [], []
    # 步骤 1：计算所有文本的内容哈希
    hashes = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    # 步骤 2：查库找已有向量（content-hash → vector_id 映射）
    rows = session.execute(
        select(DocChunk.content_hash, DocChunk.vector_id)
        .where(DocChunk.content_hash.in_(hashes))
        .where(DocChunk.vector_id.is_not(None))
    ).all()
    hash_to_vid: dict[str, str] = {h: vid for h, vid in rows}

    # 步骤 3：找出未命中的索引（需要调 API 的）
    miss_indexes = [i for i, h in enumerate(hashes) if h not in hash_to_vid]
    # 批内去重：同一批次内相同文本只 embed 一次，节省 API 调用
    unique_miss_hashes: list[str] = []
    unique_miss_texts: list[str] = []
    seen_miss: set[str] = set()
    for i in miss_indexes:
        h = hashes[i]
        if h in seen_miss:
            continue
        seen_miss.add(h)
        unique_miss_hashes.append(h)
        unique_miss_texts.append(texts[i])
    # 步骤 4：批量调用 embedding API（仅对去重后的未命中文本）
    miss_embeddings = (
        embedder.embed_documents(unique_miss_texts) if unique_miss_texts else []
    )
    hash_to_emb: dict[str, list[float]] = dict(
        zip(unique_miss_hashes, miss_embeddings)
    )

    # 步骤 5：组装输出——将向量散列回各自位置
    embeddings: list[list[float] | None] = [None] * len(texts)
    vector_ids: list[str | None] = [hash_to_vid.get(h) for h in hashes]
    for idx in miss_indexes:
        embeddings[idx] = hash_to_emb[hashes[idx]]
    return embeddings, vector_ids, hashes


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """单例工厂：返回 DashScope Embedding 客户端。

    使用 lru_cache 保证整个进程只创建一个实例，避免重复初始化连接。
    """
    return DashScopeEmbeddings(
        model=settings.embedding_model,
        dashscope_api_key=settings.dashscope_api_key,
        max_retries=settings.tool_max_retries,
    )
