import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_admin, get_current_user
from app.models.blogger import Blogger
from app.models.user import User
from app.schemas.blogger import (
    BloggerDetail,
    BloggerListItem,
    BloggerOnboardRequest,
    BloggerOnboardResponse,
    BloggerProfile,
    BloggerRow,
)
from app.services.blogger_service import (
    get_blogger_detail,
    list_bloggers_with_stats,
    list_predictions_by_blogger,
    upsert_blogger,
)
from app.core.config import settings
from app.services.outbox_service import enqueue_outbox_event
from app.services.twitter_service import convert_profile_to_upsert, fetch_user_profile
from app.services.user_resource_service import ResourceLimitExceeded, follow_blogger

router = APIRouter(prefix="/api/bloggers", tags=["bloggers"])


@router.post("/onboard", response_model=BloggerOnboardResponse)
def onboard_blogger(
    body: BloggerOnboardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    handle = body.handle.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        raise HTTPException(status_code=422, detail="请输入有效的 Twitter Handle（1-15 位字母、数字或下划线）")

    raw_profile = fetch_user_profile(handle)
    if raw_profile is None:
        raise HTTPException(status_code=404, detail=f"未找到 @{handle}，请检查用户名或账号状态")

    profile = BloggerProfile(**convert_profile_to_upsert(raw_profile))
    blogger = upsert_blogger(db, profile)
    blogger.fetch_enabled = True
    try:
        follow_blogger(
            db,
            current_user.id,
            blogger.id,
            max_follows=settings.max_followed_bloggers_per_user,
        )
    except ResourceLimitExceeded as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="关注博主数量已达到上限") from exc

    enqueue_outbox_event(
        db,
        "blogger.fetch_requested",
        {"blogger_handle": blogger.handle},
    )
    db.commit()
    return BloggerOnboardResponse(
        id=str(blogger.id),
        handle=blogger.handle,
        name=blogger.name,
        avatar_url=blogger.avatar_url,
        followed=True,
        fetch_enabled=True,
        initial_fetch_queued=True,
    )


@router.get("", response_model=list[BloggerListItem])
def list_bloggers(
    sort: str = Query(
        "credibility",
        pattern="^(credibility|verified_count|followers|pending_count)$",
    ),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_bloggers_with_stats(db, sort=sort)


@router.post("/upsert", response_model=BloggerRow)
def upsert_blogger_endpoint(
    profile: BloggerProfile,
    _admin: User = Depends(get_current_admin),
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


class FetchToggleRequest(BaseModel):
    fetch_enabled: bool


@router.patch("/{handle:path}/fetch-toggle")
def toggle_fetch(
    handle: str,
    body: FetchToggleRequest,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """启用或禁用博主的定时推文抓取。"""
    blogger = db.execute(
        select(Blogger).where(Blogger.handle == handle)
    ).scalar_one_or_none()
    if not blogger:
        raise HTTPException(status_code=404, detail="Blogger not found")
    blogger.fetch_enabled = body.fetch_enabled
    db.commit()
    return {"handle": handle, "fetch_enabled": blogger.fetch_enabled}


# Order matters: /{handle:path}/predictions must be declared BEFORE /{handle:path}
# so the path converter doesn't swallow "predictions" into `handle`.
@router.get("/{handle:path}/predictions")
def get_blogger_predictions(
    handle: str,
    status: str = Query("all", pattern="^(pending|verified|all)$"),
    ticker: str | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detail = get_blogger_detail(db, handle)
    if detail is None:
        raise HTTPException(status_code=404, detail="Blogger not found")
    return list_predictions_by_blogger(
        db, handle, status=status, ticker=ticker, limit=limit, offset=offset
    )


@router.get("/{handle:path}", response_model=BloggerDetail)
def get_blogger(
    handle: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detail = get_blogger_detail(db, handle)
    if detail is None:
        raise HTTPException(status_code=404, detail="Blogger not found")
    return detail
