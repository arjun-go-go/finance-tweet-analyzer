import json
from datetime import datetime, timedelta, timezone
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.core.deps import engine, get_db
from app.models.index_job import IndexJob
from app.models.outbox_event import OutboxEvent
from app.models.tweet import Tweet
from app.models.tweet_media_analysis import TweetMediaAnalysis
from app.models.tweet_media_asset import TweetMediaAsset
from app.models.user import User
from app.scheduler.locks import _get_redis
from app.core.config import settings
from app.services.market_verification_service import (
    PREDICTION_RUNTIME_SOURCE_PREFIX,
    PREDICTION_RUNTIME_TASK_KEY,
)


router = APIRouter(prefix="/api/admin/runtime", tags=["admin-runtime"])


def _redis_hash(redis_client, key: str) -> dict:
    return {str(name): value for name, value in redis_client.hgetall(key).items()}


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _prediction_verification_runtime(redis_client) -> dict:
    task = _redis_hash(redis_client, PREDICTION_RUNTIME_TASK_KEY)
    result = {}
    if task.get("last_result"):
        try:
            result = json.loads(task["last_result"])
        except (TypeError, ValueError):
            result = {}

    interval = settings.auto_verification_interval_minutes
    next_scheduled_at = None
    last_finished_at = task.get("last_finished_at")
    if last_finished_at:
        try:
            next_at = datetime.fromisoformat(last_finished_at) + timedelta(minutes=interval)
            next_scheduled_at = next_at.isoformat()
        except ValueError:
            pass

    sources = {}
    alerts = []
    source_labels = {
        "cn": "A股",
        "hk": "港股",
        "us": "美股",
        "eia": "WTI 原油",
        "binance": "黄金 / 加密货币",
    }
    for source, label in source_labels.items():
        raw = _redis_hash(redis_client, f"{PREDICTION_RUNTIME_SOURCE_PREFIX}{source}")
        consecutive_failures = _as_int(raw.get("consecutive_failures"))
        sources[source] = {
            "label": label,
            "status": raw.get("status", "unknown"),
            "provider": raw.get("provider"),
            "last_checked_at": raw.get("last_checked_at"),
            "last_success_at": raw.get("last_success_at"),
            "last_error_at": raw.get("last_error_at"),
            "last_error": raw.get("last_error"),
            "consecutive_failures": consecutive_failures,
            "total_calls": _as_int(raw.get("total_calls")),
            "total_successes": _as_int(raw.get("total_successes")),
            "total_failures": _as_int(raw.get("total_failures")),
            "fallback_count": _as_int(raw.get("fallback_count")),
        }
        if consecutive_failures >= 3:
            alerts.append({
                "level": "critical",
                "source": source,
                "message": f"{label}行情源已连续失败 {consecutive_failures} 次",
            })

    task_failures = _as_int(task.get("consecutive_failures"))
    if task_failures >= 3:
        alerts.append({
            "level": "critical",
            "source": "task",
            "message": f"自动验证任务已连续失败 {task_failures} 次",
        })
    return {
        "enabled": settings.auto_verification_enabled,
        "interval_minutes": interval,
        "batch_size": settings.auto_verification_batch_size,
        "task": {
            "status": task.get("status", "never_run"),
            "task_id": task.get("task_id"),
            "last_started_at": task.get("last_started_at"),
            "last_finished_at": last_finished_at,
            "last_success_at": task.get("last_success_at"),
            "last_error_at": task.get("last_error_at"),
            "last_error": task.get("last_error"),
            "consecutive_failures": task_failures,
            "last_result": result,
            "next_scheduled_at": next_scheduled_at,
        },
        "sources": sources,
        "alerts": alerts,
    }


@router.get("/stats")
def runtime_stats(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    redis_client = _get_redis()
    queue_names = ["analysis", "prediction", "ingest", "vision", "embed", "report", "default"]
    outbox_rows = db.execute(
        select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
    ).all()
    index_rows = db.execute(
        select(IndexJob.target, IndexJob.status, func.count()).group_by(
            IndexJob.target, IndexJob.status
        )
    ).all()
    oldest_pending = db.execute(
        select(func.min(OutboxEvent.created_at)).where(OutboxEvent.status == "pending")
    ).scalar_one_or_none()
    analysis_status_rows = db.execute(
        select(Tweet.status, func.count()).group_by(Tweet.status)
    ).all()
    vision_rows = list(db.execute(select(TweetMediaAnalysis)).scalars().all())
    media_asset_rows = db.execute(
        select(TweetMediaAsset.status, func.count()).group_by(TweetMediaAsset.status)
    ).all()

    index_jobs: dict[str, dict[str, int]] = {}
    for target, status, count in index_rows:
        index_jobs.setdefault(target, {})[status] = int(count or 0)

    pending_age_seconds = 0
    if oldest_pending:
        pending_age_seconds = max(
            0,
            int((datetime.now(timezone.utc) - oldest_pending).total_seconds()),
        )

    completed_vision = [row for row in vision_rows if row.status == "completed"]
    vision_usage = {
        "input_tokens": sum(int((row.usage or {}).get("input_tokens") or 0) for row in vision_rows),
        "output_tokens": sum(int((row.usage or {}).get("output_tokens") or 0) for row in vision_rows),
        "total_tokens": sum(int((row.usage or {}).get("total_tokens") or 0) for row in vision_rows),
        "provider_cost_usd": round(
            sum(float((row.usage or {}).get("cost_usd") or 0.0) for row in vision_rows),
            6,
        ),
    }
    average_confidence = 0.0
    if completed_vision:
        average_confidence = sum(
            float((row.result or {}).get("confidence") or 0.0)
            for row in completed_vision
        ) / len(completed_vision)

    return {
        "celery_pipeline_heartbeat": redis_client.get("health:celery_pipeline"),
        "queues": {name: int(redis_client.llen(name)) for name in queue_names},
        "outbox": {
            "statuses": {status: int(count or 0) for status, count in outbox_rows},
            "oldest_pending_age_seconds": pending_age_seconds,
        },
        "index_jobs": index_jobs,
        "tweet_analysis": {
            status: int(count or 0)
            for status, count in analysis_status_rows
        },
        "vision": {
            "statuses": dict(Counter(row.status for row in vision_rows)),
            "attempts": sum(row.attempts or 0 for row in vision_rows),
            "average_confidence": round(average_confidence, 3),
            "assets": {status: int(count or 0) for status, count in media_asset_rows},
            "usage": vision_usage,
        },
        "prediction_verification": _prediction_verification_runtime(redis_client),
        "database_pool": engine.pool.status(),
    }
