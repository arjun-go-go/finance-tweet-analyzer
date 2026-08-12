from datetime import datetime, timezone
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


router = APIRouter(prefix="/api/admin/runtime", tags=["admin-runtime"])


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
        "database_pool": engine.pool.status(),
    }
