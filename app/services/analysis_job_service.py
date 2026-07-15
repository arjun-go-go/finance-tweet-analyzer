"""Durable user analysis job requests."""

from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisJob, AnalysisResult, Blogger, Tweet, UserBloggerFollow


class AnalysisJobNotFound(Exception):
    """Raised when a user-scoped analysis job does not exist."""


class AnalysisJobTargetNotFound(Exception):
    """Raised when the requested analysis target does not exist."""


class AnalysisJobForbidden(Exception):
    """Raised when the user is not allowed to analyze the target."""


class AnalysisJobInvalidState(Exception):
    """Raised when a job cannot be processed in its current state."""


def analysis_cache_key(
    *, kind: str, target_id: UUID, pipeline_version: str
) -> str:
    return sha256(f"{pipeline_version}:{kind}:{target_id}".encode()).hexdigest()


def create_analysis_job(
    db: Session,
    user_id: UUID,
    *,
    kind: str,
    target_id: UUID,
    pipeline_version: str,
    status: str = "queued",
    batch_id: UUID | None = None,
) -> AnalysisJob:
    if status not in {"queued", "awaiting_confirmation"}:
        raise ValueError(f"Unsupported initial analysis job status: {status}")

    if kind == "tweet_analysis":
        if db.execute(select(Tweet.id).where(Tweet.id == target_id)).scalar_one_or_none() is None:
            raise AnalysisJobTargetNotFound("tweet")
    elif kind == "blogger_analysis":
        if db.execute(select(Blogger.id).where(Blogger.id == target_id)).scalar_one_or_none() is None:
            raise AnalysisJobTargetNotFound("blogger")
        followed = db.execute(
            select(UserBloggerFollow.id).where(
                UserBloggerFollow.user_id == user_id,
                UserBloggerFollow.blogger_id == target_id,
            )
        ).scalar_one_or_none()
        if followed is None:
            raise AnalysisJobForbidden("blogger")
    else:
        raise ValueError(f"Unsupported analysis job kind: {kind}")

    job = AnalysisJob(
        requested_by_user_id=user_id,
        kind=kind,
        request_payload={
            "target_id": str(target_id),
            "pipeline_version": pipeline_version,
        },
        status=status,
        batch_id=batch_id,
    )
    db.add(job)
    db.flush()
    return job


def get_analysis_job(db: Session, user_id: UUID, job_id: UUID) -> AnalysisJob:
    job = db.execute(
        select(AnalysisJob).where(
            AnalysisJob.id == job_id,
            AnalysisJob.requested_by_user_id == user_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise AnalysisJobNotFound("analysis_job")
    return job


def list_analysis_jobs(
    db: Session,
    user_id: UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[AnalysisJob], int]:
    total = db.execute(
        select(func.count())
        .select_from(AnalysisJob)
        .where(AnalysisJob.requested_by_user_id == user_id)
    ).scalar_one()
    jobs = db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.requested_by_user_id == user_id)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(jobs), int(total)


def mark_analysis_job_dispatched(
    db: Session, job: AnalysisJob, *, celery_task_id: str
) -> AnalysisJob:
    job.celery_task_id = celery_task_id
    job.status = "queued"
    db.flush()
    return job


def mark_analysis_job_started(db: Session, job: AnalysisJob) -> AnalysisJob:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.flush()
    return job


def mark_analysis_job_completed(
    db: Session,
    job: AnalysisJob,
    *,
    reused_result: bool,
    batch_id: UUID | None = None,
) -> AnalysisJob:
    job.status = "completed"
    job.reused_result = reused_result
    job.batch_id = batch_id
    job.completed_at = datetime.now(timezone.utc)
    job.error_code = None
    job.error_summary = None
    db.flush()
    return job


def mark_analysis_job_dispatch_failed(
    db: Session,
    job: AnalysisJob,
    *,
    error_code: str = "dispatch_failed",
) -> AnalysisJob:
    job.status = "failed"
    job.error_code = error_code
    job.error_summary = "Analysis job could not be queued. Please retry later."
    db.flush()
    return job


def mark_analysis_job_failed(
    db: Session,
    job: AnalysisJob,
    *,
    error_code: str = "analysis_failed",
) -> AnalysisJob:
    job.status = "failed"
    job.error_code = error_code
    job.error_summary = "Analysis job failed. Please retry later."
    job.completed_at = datetime.now(timezone.utc)
    db.flush()
    return job


def find_cached_tweet_analysis(
    db: Session,
    *,
    tweet_id: UUID,
    pipeline_version: str,
) -> AnalysisResult | None:
    return db.execute(
        select(AnalysisResult)
        .where(
            AnalysisResult.tweet_id == tweet_id,
            AnalysisResult.analysis_type == "tweet_analysis",
            AnalysisResult.pipeline_version == pipeline_version,
        )
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _cache_tweet_analysis(
    analysis: AnalysisResult,
    *,
    pipeline_version: str,
) -> None:
    analysis.pipeline_version = pipeline_version
    analysis.cache_key = analysis_cache_key(
        kind="tweet_analysis",
        target_id=analysis.tweet_id,
        pipeline_version=pipeline_version,
    )


def _cache_blogger_analyses(
    db: Session,
    *,
    blogger_handle: str,
    pipeline_version: str,
) -> int:
    analyses = db.execute(
        select(AnalysisResult)
        .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
        .where(
            Tweet.author_handle == blogger_handle,
            AnalysisResult.analysis_type == "tweet_analysis",
            AnalysisResult.pipeline_version == pipeline_version,
        )
    ).scalars().all()
    for analysis in analyses:
        _cache_tweet_analysis(analysis, pipeline_version=pipeline_version)
    return len(analyses)


def _blogger_cache_count(
    db: Session,
    *,
    blogger_handle: str,
    pipeline_version: str,
) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(AnalysisResult)
            .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
            .where(
                Tweet.author_handle == blogger_handle,
                AnalysisResult.analysis_type == "tweet_analysis",
                AnalysisResult.pipeline_version == pipeline_version,
            )
        ).scalar_one()
    )


def _blogger_pending_count(db: Session, *, blogger_handle: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Tweet)
            .where(
                Tweet.author_handle == blogger_handle,
                Tweet.status == "pending",
            )
        ).scalar_one()
    )


def run_user_analysis_job(
    db: Session,
    job_id: UUID,
    *,
    pipeline_version: str,
    analyze_single_tweet: Callable[[Session, str], dict],
    analyze_by_blogger: Callable[[Session, str], dict],
) -> dict:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        return {"status": "skipped", "reason": "not_found"}
    if job.status not in {"queued", "failed"}:
        return {"status": "skipped", "reason": "invalid_state"}

    mark_analysis_job_started(db, job)
    db.commit()

    try:
        target_id = UUID(str(job.request_payload["target_id"]))
        if job.kind == "tweet_analysis":
            cached = find_cached_tweet_analysis(
                db, tweet_id=target_id, pipeline_version=pipeline_version
            )
            if cached is not None:
                _cache_tweet_analysis(cached, pipeline_version=pipeline_version)
                mark_analysis_job_completed(db, job, reused_result=True)
                db.commit()
                return {
                    "status": "completed",
                    "reused_result": True,
                    "analysis_result_id": str(cached.id),
                }

            result = analyze_single_tweet(db, str(target_id))
            cached = find_cached_tweet_analysis(
                db, tweet_id=target_id, pipeline_version=pipeline_version
            )
            if cached is not None:
                _cache_tweet_analysis(cached, pipeline_version=pipeline_version)
            batch_id = UUID(result["batch_id"]) if result.get("batch_id") else None
            mark_analysis_job_completed(
                db, job, reused_result=False, batch_id=batch_id
            )
            db.commit()
            return {"status": "completed", "reused_result": False, **result}

        if job.kind == "blogger_analysis":
            blogger = db.get(Blogger, target_id)
            if blogger is None:
                raise AnalysisJobTargetNotFound("blogger")

            pending_count = _blogger_pending_count(
                db, blogger_handle=blogger.handle
            )
            cached_count = _blogger_cache_count(
                db,
                blogger_handle=blogger.handle,
                pipeline_version=pipeline_version,
            )
            if pending_count == 0 and cached_count > 0:
                mark_analysis_job_completed(db, job, reused_result=True)
                db.commit()
                return {
                    "status": "completed",
                    "reused_result": True,
                    "cached_count": cached_count,
                }

            result = analyze_by_blogger(db, blogger.handle)
            cached_count = _cache_blogger_analyses(
                db,
                blogger_handle=blogger.handle,
                pipeline_version=pipeline_version,
            )
            batch_id = UUID(result["batch_id"]) if result.get("batch_id") else None
            mark_analysis_job_completed(
                db, job, reused_result=False, batch_id=batch_id
            )
            db.commit()
            return {
                "status": "completed",
                "reused_result": False,
                "cached_count": cached_count,
                **result,
            }

        raise ValueError(f"Unsupported analysis job kind: {job.kind}")
    except Exception:
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        if job is not None:
            mark_analysis_job_failed(db, job)
            db.commit()
        raise
