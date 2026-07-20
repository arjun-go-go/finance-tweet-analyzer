from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.celery_app import celery
from app.core.config import settings
from app.core.rate_limit import enforce_user_limit
from app.models.blogger import Blogger
from app.models.tweet import Tweet
from app.services.analysis_job_service import (
    AnalysisJobForbidden,
    AnalysisJobTargetNotFound,
    confirm_analysis_jobs,
    create_analysis_job,
    list_confirmable_analysis_jobs_by_batch,
)

ALL_HANDLES = ("all", "全部", "所有")


def preview_tweet_analysis_impl(
    db,
    *,
    user_id: UUID,
    blogger_handle: str = "",
    reanalyze: bool = False,
    since: str = "",
    pipeline_version: str,
) -> str:
    """Create durable awaiting-confirmation analysis jobs and return a preview message."""
    if reanalyze or since:
        return "持久化分析确认暂不支持 reanalyze/since，请先使用默认 pending 推文分析。"

    handle = blogger_handle.strip().lstrip("@").lower() if blogger_handle else ""
    query = (
        select(Tweet.author_handle, func.count(Tweet.id))
        .where(Tweet.status == "pending")
        .group_by(Tweet.author_handle)
    )
    if handle and handle not in ALL_HANDLES:
        query = query.where(Tweet.author_handle == handle)

    rows = db.execute(query).all()
    if not rows:
        scope = f"博主 @{handle}" if handle and handle not in ALL_HANDLES else "所有博主"
        return f"{scope} 当前没有待分析的推文。"

    handles_list = [h for h, _ in rows]
    bloggers = db.execute(
        select(Blogger).where(Blogger.handle.in_(handles_list))
    ).scalars().all()
    blogger_by_handle = {blogger.handle: blogger for blogger in bloggers}

    confirmation_id = uuid4()
    created_jobs = []
    skipped = 0
    for h in handles_list:
        blogger = blogger_by_handle.get(h)
        if blogger is None:
            skipped += 1
            continue
        try:
            created_jobs.append(
                create_analysis_job(
                    db,
                    user_id,
                    kind="blogger_analysis",
                    target_id=blogger.id,
                    pipeline_version=pipeline_version,
                    status="awaiting_confirmation",
                    batch_id=confirmation_id,
                )
            )
        except (AnalysisJobForbidden, AnalysisJobTargetNotFound):
            skipped += 1
    db.commit()

    if not created_jobs:
        return "没有可提交的分析任务。请先关注对应博主，或等待系统抓取可分析推文。"

    total = sum(count for _, count in rows)
    lines = [f"待分析推文统计：共 {total} 条"]
    for h, count in sorted(rows, key=lambda x: -x[1])[:10]:
        lines.append(f"  - @{h}: {count} 条")
    if len(rows) > 10:
        lines.append(f"  ...及其他 {len(rows) - 10} 位博主")
    if skipped:
        lines.append(f"\n已跳过 {skipped} 位未关注或不存在的博主。")
    lines.append(f"\n确认ID: {confirmation_id}")
    lines.append("请用户确认是否执行分析，确认后调用 confirm_tweet_analysis。")
    return "\n".join(lines)


def confirm_tweet_analysis_impl(
    db,
    *,
    user_id: UUID,
    confirmation_id: UUID,
    daily_limit: int,
) -> str:
    """Confirm and dispatch durable analysis jobs."""
    jobs = list_confirmable_analysis_jobs_by_batch(db, user_id, confirmation_id)
    if not jobs:
        return f"确认ID '{confirmation_id}' 无效、已提交或已过期。请重新预览。"

    def dispatch(job) -> str:
        enforce_user_limit(
            f"user-analysis:{user_id}",
            limit=daily_limit,
            window=24 * 60 * 60,
        )
        celery.send_task(
            "app.scheduler.tasks.user_analysis_job_task",
            args=[str(job.id)],
            task_id=str(job.id),
            queue="analysis",
        )
        return str(job.id)

    confirmed, _ = confirm_analysis_jobs(
        db,
        user_id,
        [job.id for job in jobs],
        dispatch=dispatch,
    )
    db.commit()

    return (
        f"已提交分析任务（{len(confirmed)} 个持久化 job）。"
        f"确认ID: {confirmation_id}。"
        "后台执行中，可在个人分析任务列表查看状态。"
    )
