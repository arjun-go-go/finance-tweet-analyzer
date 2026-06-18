from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.blogger import (
    BloggerDetail,
    BloggerListItem,
    BloggerProfile,
    BloggerRow,
)
from app.services.blogger_service import (
    get_blogger_detail,
    list_bloggers_with_stats,
    list_predictions_by_blogger,
    upsert_blogger,
)

router = APIRouter(prefix="/api/bloggers", tags=["bloggers"])


@router.get("", response_model=list[BloggerListItem])
def list_bloggers(
    sort: str = Query(
        "credibility",
        pattern="^(credibility|verified_count|followers|pending_count)$",
    ),
    db: Session = Depends(get_db),
):
    return list_bloggers_with_stats(db, sort=sort)


@router.post("/upsert", response_model=BloggerRow)
def upsert_blogger_endpoint(
    profile: BloggerProfile,
    db: Session = Depends(get_db),
):
    blogger = upsert_blogger(db, profile)
    db.commit()
    return BloggerRow(
        handle=blogger.handle,
        name=blogger.name,
        bio=blogger.bio,
        avatar_url=blogger.avatar_url,
        followers_count=blogger.followers_count,
        market_focus=blogger.market_focus,
        profile_updated_at=blogger.profile_updated_at,
        twitter_user_id=blogger.twitter_user_id,
        location=blogger.location,
        tweets_count=blogger.tweets_count,
        following_count=blogger.following_count,
        favorites_count=blogger.favorites_count,
        joined_at=blogger.joined_at,
        verified=blogger.verified,
        protected=blogger.protected,
        profile_url=blogger.profile_url,
    )


# Order matters: /{handle:path}/predictions must be declared BEFORE /{handle:path}
# so the path converter doesn't swallow "predictions" into `handle`.
@router.get("/{handle:path}/predictions")
def get_blogger_predictions(
    handle: str,
    status: str = Query("all", pattern="^(pending|verified|all)$"),
    ticker: str | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    detail = get_blogger_detail(db, handle)
    if detail is None:
        raise HTTPException(status_code=404, detail="Blogger not found")
    return list_predictions_by_blogger(
        db, handle, status=status, ticker=ticker, limit=limit, offset=offset
    )


@router.get("/{handle:path}", response_model=BloggerDetail)
def get_blogger(handle: str, db: Session = Depends(get_db)):
    detail = get_blogger_detail(db, handle)
    if detail is None:
        raise HTTPException(status_code=404, detail="Blogger not found")
    return detail
