from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.models.blogger import Blogger
from app.models.user import User
from app.schemas.blogger import BloggerListItem
from app.schemas.me import (
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
