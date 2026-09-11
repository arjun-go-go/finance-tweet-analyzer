from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_user
from app.models.analysis import AnalysisResult
from app.models.instrument_claim import InstrumentClaim
from app.models.tweet import Tweet
from app.models.tweet_media_asset import TweetMediaAsset
from app.models.user import User
from app.schemas.tweet import TweetMediaItem
from app.services.instrument_claim_service import (
    analysis_payload_with_claims,
    claims_by_analysis_ids,
)
from app.services.instrument_claim_aggregation_service import aggregate_instrument_claims

router = APIRouter(prefix="/api", tags=["analysis-results"])


class TweetAnalysisItem(BaseModel):
    id: str
    tweet_id: str
    twitter_tweet_id: str
    author_handle: str
    content: str
    analysis: dict
    confidence: float
    created_at: str
    published_at: str
    media: list[TweetMediaItem] = []
    prediction_status: str
    prediction_decision: dict | None = None


class TweetAnalysesResponse(BaseModel):
    items: list[TweetAnalysisItem]
    total: int


class TickerSummaryItem(BaseModel):
    id: str
    result: dict
    created_at: str


class TickerSummariesResponse(BaseModel):
    items: list[TickerSummaryItem]
    total: int


@router.get("/analyses", response_model=TweetAnalysesResponse)
def list_tweet_analyses(
    blogger: str | None = Query(None),
    sentiment: str | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """逐条推文分析结果列表"""
    filters = [AnalysisResult.analysis_type == "tweet_analysis"]
    if blogger:
        filters.append(Tweet.author_handle == blogger)
    if sentiment:
        author_stance_ids = select(InstrumentClaim.analysis_result_id).where(
            InstrumentClaim.performance_eligible.is_(True),
        )
        if sentiment == "none":
            filters.append(AnalysisResult.id.not_in(author_stance_ids))
        else:
            filters.append(
                AnalysisResult.id.in_(
                    author_stance_ids.where(InstrumentClaim.direction == sentiment)
                )
            )

    query = (
        select(AnalysisResult, Tweet)
        .join(Tweet, AnalysisResult.tweet_id == Tweet.id)
        .where(*filters)
        .order_by(Tweet.published_at.desc())
    )

    count_query = (
        select(func.count(AnalysisResult.id))
        .join(Tweet, AnalysisResult.tweet_id == Tweet.id)
        .where(*filters)
    )
    total = db.execute(count_query).scalar() or 0

    rows = db.execute(query.limit(limit).offset(offset)).all()
    media_map: dict[str, list[TweetMediaItem]] = {}
    claim_map = claims_by_analysis_ids(db, [ar.id for ar, _tweet in rows])
    if rows:
        assets = db.execute(
            select(TweetMediaAsset)
            .where(
                TweetMediaAsset.tweet_id.in_([tweet.id for _, tweet in rows]),
                TweetMediaAsset.status == "downloaded",
                TweetMediaAsset.object_key.is_not(None),
            )
            .order_by(TweetMediaAsset.created_at.asc())
        ).scalars().all()
        for asset in assets:
            media_map.setdefault(str(asset.tweet_id), []).append(
                TweetMediaItem(
                    id=str(asset.id),
                    width=asset.width,
                    height=asset.height,
                    content_type=asset.content_type,
                )
            )

    items = [
        TweetAnalysisItem(
            id=str(ar.id),
            tweet_id=str(ar.tweet_id),
            twitter_tweet_id=tw.tweet_id,
            author_handle=tw.author_handle,
            content=tw.content,
            analysis=analysis_payload_with_claims(
                ar.result,
                claim_map.get(ar.id, []),
            ),
            confidence=ar.confidence,
            created_at=ar.created_at.isoformat() if ar.created_at else "",
            published_at=tw.published_at.isoformat() if tw.published_at else "",
            media=media_map.get(str(tw.id), []),
            prediction_status=ar.prediction_status,
            prediction_decision=ar.prediction_decision,
        )
        for ar, tw in rows
    ]

    return TweetAnalysesResponse(items=items, total=total)


@router.get("/ticker-summaries", response_model=TickerSummariesResponse)
def list_ticker_summaries(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按规范化逐标的观点实时聚合，不再读取 ticker_summary 缓存行。"""
    summaries = aggregate_instrument_claims(db)
    page = summaries[offset:offset + limit]
    items = [
        TickerSummaryItem(
            id=summary["ticker"],
            result=summary,
            created_at="",
        )
        for summary in page
    ]
    return TickerSummariesResponse(items=items, total=len(summaries))
