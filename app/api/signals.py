from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.analysis import AnalysisResult
from app.models.tweet import Tweet

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
    db: Session = Depends(get_db),
):
    """逐条推文分析结果列表"""
    query = (
        select(AnalysisResult, Tweet)
        .join(Tweet, AnalysisResult.tweet_id == Tweet.id)
        .where(AnalysisResult.analysis_type == "tweet_analysis")
        .order_by(AnalysisResult.created_at.desc())
    )

    if blogger:
        query = query.where(Tweet.author_handle == blogger)
    if sentiment:
        query = query.where(AnalysisResult.result["overall_sentiment"].astext == sentiment)

    count_query = select(func.count()).select_from(
        select(AnalysisResult)
        .where(AnalysisResult.analysis_type == "tweet_analysis")
        .subquery()
    )
    total = db.execute(count_query).scalar() or 0

    rows = db.execute(query.limit(limit).offset(offset)).all()

    items = [
        TweetAnalysisItem(
            id=str(ar.id),
            tweet_id=str(ar.tweet_id),
            twitter_tweet_id=tw.tweet_id,
            author_handle=tw.author_handle,
            content=tw.content,
            analysis=ar.result,
            confidence=ar.confidence,
            created_at=ar.created_at.isoformat() if ar.created_at else "",
            published_at=tw.published_at.isoformat() if tw.published_at else "",
        )
        for ar, tw in rows
    ]

    return TweetAnalysesResponse(items=items, total=total)


@router.get("/ticker-summaries", response_model=TickerSummariesResponse)
def list_ticker_summaries(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """标的聚合推荐结果列表"""
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.analysis_type == "ticker_summary")
        .order_by(AnalysisResult.created_at.desc())
    )

    count_query = select(func.count()).select_from(
        select(AnalysisResult)
        .where(AnalysisResult.analysis_type == "ticker_summary")
        .subquery()
    )
    total = db.execute(count_query).scalar() or 0

    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()

    items = [
        TickerSummaryItem(
            id=str(r.id),
            result=r.result,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]

    return TickerSummariesResponse(items=items, total=total)
