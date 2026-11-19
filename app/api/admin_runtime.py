import json
from datetime import datetime, timedelta, timezone
from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.core.deps import engine, get_db
from app.models.agent_trace import AgentTrace
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
from app.services.analysis_control_service import (
    analysis_backlog,
    analysis_ingest_cutoff,
    get_analysis_control,
    pause_analysis_manually,
    requeue_waiting_media_analysis,
    resume_analysis_manually,
)


router = APIRouter(prefix="/api/admin/runtime", tags=["admin-runtime"])


class AnalysisPauseRequest(BaseModel):
    reason: str = Field(default="管理员手动暂停", max_length=500)


class AnalysisResumeRequest(BaseModel):
    include_backlog: bool = True


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
    analysis_control = get_analysis_control(db)
    analysis_control["backlog"] = analysis_backlog(db, analysis_control)
    text_usage = db.execute(select(
        func.coalesce(func.sum(cast(AgentTrace.input["tweet_count"].astext, BigInteger)), 0),
        func.coalesce(func.sum(cast(AgentTrace.output["calls"].astext, BigInteger)), 0),
        func.coalesce(func.sum(cast(AgentTrace.output["total_tokens"].astext, BigInteger)), 0),
    ).where(
        AgentTrace.node_name == "analysis_model_usage",
        AgentTrace.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
    )).one()
    queue_names = ["analysis", "prediction", "ingest", "vision", "embed", "default"]
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
        "analysis_control": analysis_control,
        "text_model_usage_24h": dict(zip(("tweet_attempts", "calls", "total_tokens"), text_usage)),
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


@router.get("/analysis-control")
def analysis_control_status(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    control = get_analysis_control(db)
    control["backlog"] = analysis_backlog(db, control)
    return control


@router.post("/analysis-control/pause")
def pause_analysis_control(
    request: AnalysisPauseRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    control = pause_analysis_manually(
        db,
        reason=request.reason,
        updated_by=str(admin.id),
    )
    control["backlog"] = analysis_backlog(db, control)
    return control


@router.post("/analysis-control/resume")
def resume_analysis_control(
    request: AnalysisResumeRequest | None = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    control = resume_analysis_manually(
        db, updated_by=str(admin.id), include_backlog=request.include_backlog if request else True
    )
    media_requeued = requeue_waiting_media_analysis(db, ingested_after=analysis_ingest_cutoff(control))

    # Kick the text backlog immediately; the periodic scan remains the fallback.
    from app.scheduler.tasks import auto_analysis_task

    task = auto_analysis_task.apply_async(queue="analysis")
    control["backlog"] = analysis_backlog(db, control)
    control["resume_dispatch"] = {
        "media_requeued": media_requeued,
        "text_task_id": task.id,
    }
    return control
