"""
mem0 长期记忆客户端单例（自托管 OSS 模式）
============================================================
职责：
  - 使用 mem0 OSS `Memory` 类，全部基础设施自托管
  - LLM：OpenRouter（OpenAI 兼容接口）
  - Embedder：DashScope text-embedding（OpenAI 兼容接口）
  - 向量存储：独立 Milvus collection
  - 历史记录与最近消息：共享 PostgreSQL
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

import os
import threading

from loguru import logger

from app.core.config import settings
from app.memory.postgres_history import PostgresMemoryHistory

# mem0 在模块导入时读取此变量；必须先设置，避免创建遥测专用 collection。
os.environ.setdefault("MEM0_TELEMETRY", "false")

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

    if settings.mem0_vector_backend.lower() != "milvus":
        raise ValueError("MEM0_VECTOR_BACKEND must be 'milvus'")
    vector_store_cfg = {
        "provider": "milvus",
        "config": {
            "url": settings.milvus_uri,
            "token": settings.milvus_token,
            "collection_name": settings.mem0_milvus_collection,
            "embedding_model_dims": settings.embedding_dim,
            "metric_type": settings.mem0_milvus_metric_type,
            "db_name": settings.milvus_db_name,
        },
    }

    return {
        "llm": {"provider": "openai", "config": llm_cfg},
        "embedder": {"provider": "openai", "config": embedder_cfg},
        "vector_store": vector_store_cfg,
        # mem0 2.0.6 constructs SQLite internally. Use in-memory storage only
        # during initialization, then replace it with the shared PG adapter.
        "history_db_path": ":memory:",
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
            memory = Memory.from_config(cfg)
            memory.db.close()
            memory.db = PostgresMemoryHistory()
            _mem0_client_singleton = memory
            logger.info(
                "[mem0] Memory initialized (vector_backend={}, history=postgresql, llm={}, embedder={})",
                settings.mem0_vector_backend,
                settings.signal_model,
                settings.embedding_model,
            )
        except Exception as e:
            logger.warning("[mem0] initialization failed: {}", e)
            return None

    return _mem0_client_singleton
