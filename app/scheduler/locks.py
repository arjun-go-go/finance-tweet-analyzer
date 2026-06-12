"""Redis 分布式锁 —— 替代 threading.Lock，支持多 Worker / 多实例部署。

使用 Redis SET NX + TTL 实现，自动过期防死锁。
"""
import redis
from loguru import logger

from app.core.config import settings

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def try_acquire(handle: str, ttl: int = 600) -> bool:
    """尝试获取指定 blogger 的分析锁。

    Args:
        handle: blogger handle 作为锁标识
        ttl: 锁自动过期时间(秒)，防止 Worker 崩溃后死锁
    """
    key = f"lock:analysis:{handle}"
    acquired = _get_redis().set(key, "1", nx=True, ex=ttl)
    if not acquired:
        logger.debug("Redis lock exists for {}, skipping", handle)
    return bool(acquired)


def release(handle: str) -> None:
    """释放指定 blogger 的分析锁。"""
    key = f"lock:analysis:{handle}"
    _get_redis().delete(key)


def try_acquire_prediction_lock(ttl: int = 300) -> bool:
    """全局预测批处理锁，确保同一时刻只有一个 Worker 执行预测任务。"""
    key = "lock:prediction_batch"
    acquired = _get_redis().set(key, "1", nx=True, ex=ttl)
    return bool(acquired)


def release_prediction_lock() -> None:
    """释放预测批处理锁。"""
    _get_redis().delete("lock:prediction_batch")
