"""
mem0 长期记忆客户端单例（自托管 OSS 模式）
============================================================
职责：
  - 使用 mem0 OSS `Memory` 类，全部基础设施自托管
  - LLM：OpenRouter（OpenAI 兼容接口）
  - Embedder：DashScope text-embedding（OpenAI 兼容接口）
  - 向量存储：独立 ChromaDB 目录（与 RAG 的 chroma_db 隔离）
  - 历史记录：本地 SQLite（mem0_history.db）
  - 单例保证整个进程只初始化一次
  - mem0_enabled=False 时返回 None，调用方需判断

使用方式：
    from app.memory.mem0_client import get_mem0_client
    memory = get_mem0_client()   # None if disabled
    if memory:
        results = memory.search(query, user_id=user_id, limit=5)
        memory.add(messages, user_id=user_id)
"""
from __future__ import annotations

import threading

from loguru import logger

from app.core.config import settings

try:
    from mem0 import Memory
except ImportError:  # pragma: no cover
    Memory = None  # type: ignore[assignment,misc]

_mem0_client_singleton = None
_mem0_init_lock = threading.Lock()


def _build_config() -> dict:
    """构建 mem0 自托管配置字典。"""
    llm_cfg: dict = {
        "model": settings.signal_model,
        "api_key": settings.openrouter_api_key,
        "openai_base_url": settings.openrouter_base_url,
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    embedder_cfg: dict = {
        "model": settings.embedding_model,
        "api_key": settings.dashscope_api_key,
        "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "embedding_dims": settings.embedding_dim,
    }

    return {
        "llm": {"provider": "openai", "config": llm_cfg},
        "embedder": {"provider": "openai", "config": embedder_cfg},
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "mem0_memories",
                "path": settings.mem0_chroma_path,
            },
        },
        "history_db_path": settings.mem0_history_db_path,
        "version": "v1.1",
    }


def get_mem0_client():
    """返回 mem0 Memory 单例；未启用时返回 None。"""
    global _mem0_client_singleton

    if _mem0_client_singleton is not None:
        return _mem0_client_singleton

    with _mem0_init_lock:
        if _mem0_client_singleton is not None:
            return _mem0_client_singleton

        if not settings.mem0_enabled:
            logger.debug("[mem0] disabled by config")
            return None

        if Memory is None:
            logger.warning("[mem0] mem0ai package not installed")
            return None

        try:
            cfg = _build_config()
            _mem0_client_singleton = Memory.from_config(cfg)
            logger.info(
                "[mem0] Memory initialized (chroma={}, llm={}, embedder={})",
                settings.mem0_chroma_path,
                settings.signal_model,
                settings.embedding_model,
            )
        except Exception as e:
            logger.warning("[mem0] initialization failed: {}", e)
            return None

    return _mem0_client_singleton
