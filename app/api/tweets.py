from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_admin
from app.models.user import User
from app.models.analysis import AnalysisResult
from app.models.tweet import Tweet
from app.schemas.tweet import TweetImportRequest, TweetImportResponse
from app.services.tweet_service import import_tweets

router = APIRouter(prefix="/api/tweets", tags=["tweets"])


class TweetListItem(BaseModel):
    id: str
    tweet_id: str
    author_handle: str
    author_name: str
    content: str
    published_at: str
    status: str
    metrics: dict | None = None
    analysis: dict | None = None


class TweetListResponse(BaseModel):
    items: list[TweetListItem]
    total: int


@router.get("", response_model=TweetListResponse)
def list_tweets(
    status: str | None = Query(None, description="pending / analyzed"),
    blogger: str | None = Query(None),
    include_analysis: bool = Query(False, description="Include latest tweet_analysis result"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    query = select(Tweet).order_by(Tweet.published_at.desc())
    count_query = select(func.count()).select_from(Tweet)

    if status:
        query = query.where(Tweet.status == status)
        count_query = count_query.where(Tweet.status == status)
    if blogger:
        query = query.where(Tweet.author_handle == blogger)
        count_query = count_query.where(Tweet.author_handle == blogger)

    total = db.execute(count_query).scalar() or 0
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()

    # If include_analysis, batch-fetch related analysis_results
    analysis_map: dict[str, dict] = {}
    if include_analysis and rows:
        tweet_ids = [t.id for t in rows]
        analysis_rows = db.execute(
            select(AnalysisResult).where(
                AnalysisResult.tweet_id.in_(tweet_ids),
                AnalysisResult.analysis_type == "tweet_analysis",
            )
        ).scalars().all()
        # Keep the latest analysis per tweet (by created_at desc)
        for ar in analysis_rows:
            tid = str(ar.tweet_id)
            if tid not in analysis_map or (ar.created_at and analysis_map[tid].get("_created_at", "") < ar.created_at.isoformat()):
                analysis_map[tid] = {
                    **ar.result,
                    "confidence": ar.confidence,
                    "_created_at": ar.created_at.isoformat() if ar.created_at else "",
                }

    items = [
        TweetListItem(
            id=str(t.id),
            tweet_id=t.tweet_id,
            author_handle=t.author_handle,
            author_name=t.author_name or "",
            content=t.content,
            published_at=t.published_at.isoformat() if t.published_at else "",
            status=t.status or "pending",
            metrics=t.metrics,
            analysis=analysis_map.get(str(t.id)),
        )
        for t in rows
    ]
    return TweetListResponse(items=items, total=total)


@router.post("/import", response_model=TweetImportResponse)
def import_tweets_endpoint(
    request: TweetImportRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    imported, skipped = import_tweets(db, request.tweets, request.blogger)
    return TweetImportResponse(imported=imported, skipped=skipped)
