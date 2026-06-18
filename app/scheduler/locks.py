"""Redis 分布式锁 —— 替代 threading.Lock，支持多 Worker / 多实例部署。

使用 Redis SET NX + TTL 实现，自动过期防死锁。
释放时使用 Lua 脚本校验锁所有权，防止误删其他 Worker 的锁。
"""
import uuid

import redis
from loguru import logger

from app.core.config import settings

_redis: redis.Redis | None = None

# Lua script: only delete if value matches token (safe release)
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def try_acquire(handle: str, ttl: int = 600) -> tuple[bool, str]:
    """尝试获取指定 blogger 的分析锁。

    Args:
        handle: blogger handle 作为锁标识
        ttl: 锁自动过期时间(秒)，防止 Worker 崩溃后死锁

    Returns:
        (acquired, token): acquired=True 表示成功获取，token 用于释放时校验所有权
    """
    key = f"lock:analysis:{handle}"
    token = uuid.uuid4().hex
    acquired = _get_redis().set(key, token, nx=True, ex=ttl)
    if not acquired:
        logger.debug("Redis lock exists for {}, skipping", handle)
        return False, ""
    return True, token


def release(handle: str, token: str) -> None:
    """释放指定 blogger 的分析锁（仅当 token 匹配时才删除）。"""
    key = f"lock:analysis:{handle}"
    result = _get_redis().eval(_RELEASE_SCRIPT, 1, key, token)
    if result == 0:
        logger.warning("Lock release skipped for {} (token mismatch or lock expired)", handle)


def try_acquire_prediction_lock(ttl: int = 300) -> tuple[bool, str]:
    """全局预测批处理锁，确保同一时刻只有一个 Worker 执行预测任务。

    Returns:
        (acquired, token): acquired=True 表示成功获取，token 用于释放时校验所有权
    """
    key = "lock:prediction_batch"
    token = uuid.uuid4().hex
    acquired = _get_redis().set(key, token, nx=True, ex=ttl)
    if not acquired:
        return False, ""
    return True, token


def release_prediction_lock(token: str) -> None:
    """释放预测批处理锁（仅当 token 匹配时才删除）。"""
    key = "lock:prediction_batch"
    result = _get_redis().eval(_RELEASE_SCRIPT, 1, key, token)
    if result == 0:
        logger.warning("Prediction lock release skipped (token mismatch or lock expired)")
