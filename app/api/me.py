from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.models.blogger import Blogger
from app.models.user import User
from app.schemas.blogger import BloggerListItem
from app.schemas.me import FollowedBloggerListResponse, FollowResponse
from app.services.blogger_service import blogger_ingestion_summary, get_blogger_processing_counts
from app.services.credibility import score_profile
from app.services.user_resource_service import (
    ResourceLimitExceeded,
    ResourceNotFound,
    count_pending_predictions_by_blogger,
    follow_blogger,
    list_followed_bloggers,
    unfollow_blogger,
)


router = APIRouter(prefix="/api/me", tags=["me"])


def _followed_blogger_item(
    blogger: Blogger, *, pending_count: int, processing_counts: dict | None = None
) -> BloggerListItem:
    verified_count = int(blogger.total_predictions or 0)
    correct_sum = float(blogger.correct_predictions or 0.0)
    score = score_profile(correct_sum, verified_count)
    return BloggerListItem(
        id=str(blogger.id),
        handle=blogger.handle,
        name=blogger.name,
        bio=blogger.bio,
        avatar_url=blogger.avatar_url,
        followers_count=blogger.followers_count,
        market_focus=blogger.market_focus,
        **score,
        verified_count=verified_count,
        pending_count=pending_count,
        hit_rate=(correct_sum / verified_count if verified_count else None),
        verified=bool(blogger.verified),
        location=blogger.location,
        **blogger_ingestion_summary(blogger, processing_counts),
    )


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


@router.delete("/bloggers/{blogger_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
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
    processing_counts = get_blogger_processing_counts(
        db, [blogger.handle for blogger in bloggers]
    )
    return FollowedBloggerListResponse(
        items=[
            _followed_blogger_item(
                blogger,
                pending_count=pending_counts.get(blogger.handle, 0),
                processing_counts=processing_counts.get(blogger.handle.lower()),
            )
            for blogger in bloggers
        ],
        total=total,
    )
