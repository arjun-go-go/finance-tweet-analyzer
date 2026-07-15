from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.core.rate_limit import enforce_user_limit
from app.models.analysis_job import AnalysisJob
from app.models.blogger import Blogger
from app.models.user import User
from app.schemas.blogger import BloggerListItem
from app.schemas.me import (
    AnalysisJobCreateRequest,
    AnalysisJobListResponse,
    AnalysisJobResponse,
    BookmarkResponse,
    BookmarkedTweetItem,
    BookmarkedTweetListResponse,
    FollowedBloggerListResponse,
    FollowResponse,
)
from app.services.user_resource_service import (
    ResourceLimitExceeded,
    ResourceNotFound,
    bookmark_tweet,
    count_pending_predictions_by_blogger,
    follow_blogger,
    list_bookmarked_tweets,
    list_followed_bloggers,
    remove_tweet_bookmark,
    unfollow_blogger,
)
from app.services.analysis_job_service import (
    AnalysisJobForbidden,
    AnalysisJobNotFound,
    AnalysisJobTargetNotFound,
    create_analysis_job,
    get_analysis_job,
    list_analysis_jobs,
    mark_analysis_job_dispatch_failed,
    mark_analysis_job_dispatched,
)


router = APIRouter(prefix="/api/me", tags=["me"])


def _followed_blogger_item(
    blogger: Blogger, *, pending_count: int
) -> BloggerListItem:
    verified_count = int(blogger.total_predictions or 0)
    correct_sum = float(blogger.correct_predictions or 0.0)
    return BloggerListItem(
        id=str(blogger.id),
        handle=blogger.handle,
        name=blogger.name,
        bio=blogger.bio,
        avatar_url=blogger.avatar_url,
        followers_count=blogger.followers_count,
        market_focus=blogger.market_focus,
        credibility_score=float(blogger.credibility_score),
        verified_count=verified_count,
        pending_count=pending_count,
        hit_rate=(correct_sum / verified_count if verified_count else None),
        verified=bool(blogger.verified),
        location=blogger.location,
    )


def _analysis_job_response(job: AnalysisJob) -> AnalysisJobResponse:
    return AnalysisJobResponse(
        id=str(job.id),
        kind=job.kind,
        target_id=str(job.request_payload.get("target_id", "")),
        status=job.status,
        error_code=job.error_code,
        error_summary=job.error_summary,
        reused_result=job.reused_result,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _dispatch_analysis_job(job: AnalysisJob) -> str:
    task_id = str(job.id)
    celery.send_task(
        "app.scheduler.tasks.user_analysis_job_task",
        args=[task_id],
        task_id=task_id,
        queue="analysis",
    )
    return task_id


@router.post(
    "/bloggers/{blogger_id}/follow",
    response_model=FollowResponse,
    status_code=status.HTTP_201_CREATED,
)
def follow_blogger_endpoint(
    blogger_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FollowResponse:
    try:
        relationship = follow_blogger(
            db,
            current_user.id,
            blogger_id,
            max_follows=settings.max_followed_bloggers_per_user,
        )
        db.commit()
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="Resource not found")
    except ResourceLimitExceeded:
        raise HTTPException(status_code=429, detail="Follow limit exceeded")
    return FollowResponse(
        id=str(relationship.id),
        blogger_id=str(relationship.blogger_id),
        created_at=relationship.created_at,
    )


@router.delete(
    "/bloggers/{blogger_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unfollow_blogger_endpoint(
    blogger_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not unfollow_blogger(db, current_user.id, blogger_id):
        raise HTTPException(status_code=404, detail="Resource not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/bloggers", response_model=FollowedBloggerListResponse)
def get_followed_bloggers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FollowedBloggerListResponse:
    bloggers, total = list_followed_bloggers(
        db, current_user.id, limit=limit, offset=offset
    )
    pending_counts = count_pending_predictions_by_blogger(
        db, [blogger.handle for blogger in bloggers]
    )
    return FollowedBloggerListResponse(
        items=[
            _followed_blogger_item(
                blogger,
                pending_count=pending_counts.get(blogger.handle, 0),
            )
            for blogger in bloggers
        ],
        total=total,
    )


@router.post(
    "/tweets/{tweet_id}/bookmark",
    response_model=BookmarkResponse,
    status_code=status.HTTP_201_CREATED,
)
def bookmark_tweet_endpoint(
    tweet_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BookmarkResponse:
    try:
        relationship = bookmark_tweet(db, current_user.id, tweet_id)
        db.commit()
    except ResourceNotFound:
        raise HTTPException(status_code=404, detail="Resource not found")
    return BookmarkResponse(
        id=str(relationship.id),
        tweet_id=str(relationship.tweet_id),
        created_at=relationship.created_at,
    )


@router.delete(
    "/tweets/{tweet_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_tweet_bookmark_endpoint(
    tweet_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not remove_tweet_bookmark(db, current_user.id, tweet_id):
        raise HTTPException(status_code=404, detail="Resource not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tweets", response_model=BookmarkedTweetListResponse)
def get_bookmarked_tweets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BookmarkedTweetListResponse:
    tweets, total = list_bookmarked_tweets(
        db, current_user.id, limit=limit, offset=offset
    )
    return BookmarkedTweetListResponse(
        items=[
            BookmarkedTweetItem(
                id=str(tweet.id),
                tweet_id=tweet.tweet_id,
                author_handle=tweet.author_handle,
                author_name=tweet.author_name or "",
                content=tweet.content,
                published_at=tweet.published_at,
                status=tweet.status or "pending",
                metrics=tweet.metrics,
            )
            for tweet in tweets
        ],
        total=total,
    )


@router.post(
    "/analysis-jobs",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis_job_endpoint(
    body: AnalysisJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    if not settings.user_analysis_requests_enabled:
        raise HTTPException(status_code=404, detail="Resource not found")

    enforce_user_limit(
        f"user-analysis:{current_user.id}",
        limit=settings.user_analysis_daily_limit,
        window=24 * 60 * 60,
    )

    try:
        job = create_analysis_job(
            db,
            current_user.id,
            kind=body.kind,
            target_id=body.target_id,
            pipeline_version=settings.user_analysis_pipeline_version,
        )
        db.commit()
        db.refresh(job)
    except AnalysisJobTargetNotFound:
        raise HTTPException(status_code=404, detail="Resource not found")
    except AnalysisJobForbidden:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        task_id = _dispatch_analysis_job(job)
    except Exception:
        mark_analysis_job_dispatch_failed(db, job)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analysis queue unavailable",
        )

    mark_analysis_job_dispatched(db, job, celery_task_id=task_id)
    db.commit()
    db.refresh(job)
    return _analysis_job_response(job)


@router.get("/analysis-jobs", response_model=AnalysisJobListResponse)
def get_analysis_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJobListResponse:
    jobs, total = list_analysis_jobs(
        db, current_user.id, limit=limit, offset=offset
    )
    return AnalysisJobListResponse(
        items=[_analysis_job_response(job) for job in jobs],
        total=total,
    )


@router.get("/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_analysis_job_endpoint(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    try:
        job = get_analysis_job(db, current_user.id, job_id)
    except AnalysisJobNotFound:
        raise HTTPException(status_code=404, detail="Resource not found")
    return _analysis_job_response(job)
