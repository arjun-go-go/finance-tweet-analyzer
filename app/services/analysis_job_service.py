"""Durable user analysis job requests."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisJob, Blogger, Tweet, UserBloggerFollow


class AnalysisJobNotFound(Exception):
    """Raised when a user-scoped analysis job does not exist."""


class AnalysisJobTargetNotFound(Exception):
    """Raised when the requested analysis target does not exist."""


class AnalysisJobForbidden(Exception):
    """Raised when the user is not allowed to analyze the target."""


def create_analysis_job(
    db: Session,
    user_id: UUID,
    *,
    kind: str,
    target_id: UUID,
    pipeline_version: str,
) -> AnalysisJob:
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
        status="queued",
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
