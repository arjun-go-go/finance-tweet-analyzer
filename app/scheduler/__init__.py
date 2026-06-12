"""Scheduler 模块入口 —— Celery 模式下仅提供健康检查接口。

Celery Worker + Beat 独立进程运行，FastAPI 不再管理调度生命周期。
此模块保留兼容接口供 main.py 调用（空操作），并提供运行状态查询。
"""
from loguru import logger
from redis import Redis

from app.core.config import settings

_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def start_scheduler() -> None:
    """兼容接口：Celery 模式下 FastAPI 不启动调度器，仅验证 Redis 连通性。"""
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via config")
        return

    try:
        _get_redis().ping()
        logger.info(
            "Celery scheduler mode: Redis connected. "
            "Ensure Worker+Beat processes are running separately."
        )
    except Exception as e:
        logger.warning("Redis ping failed (Celery tasks may not work): {}", e)


def stop_scheduler() -> None:
    """兼容接口：Celery 模式下无需停止（Worker 独立管理）。"""
    logger.info("Celery scheduler: no in-process scheduler to stop")


def get_scheduler_health() -> dict:
    """运行状态查询，供 /api/health 使用。"""
    try:
        _get_redis().ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "scheduler_type": "celery",
        "redis_connected": redis_ok,
        "analysis_interval_minutes": settings.scheduler_interval_minutes,
        "prediction_interval_minutes": settings.celery_prediction_interval_minutes,
    }
