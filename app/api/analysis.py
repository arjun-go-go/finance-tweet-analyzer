from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.scheduler.locks import try_acquire, release
from app.services.analysis_service import (
    analyze_by_blogger,
    analyze_by_bloggers,
    analyze_single_tweet,
    trigger_analysis,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisResponse(BaseModel):
    batch_id: str
    analyzed: int
    analyses: list[dict]
    ticker_summaries: list[dict]


class MultiBloggerRequest(BaseModel):
    blogger_handles: list[str]


@router.post("/trigger", response_model=AnalysisResponse)
def trigger_analysis_endpoint(db: Session = Depends(get_db)):
    """分析所有 pending 推文"""
    return trigger_analysis(db)


@router.post("/tweet/{tweet_id}", response_model=AnalysisResponse)
def analyze_single_tweet_endpoint(tweet_id: str, db: Session = Depends(get_db)):
    """分析单条推文（支持重新分析已分析过的推文）"""
    lock_key = f"tweet_analysis:{tweet_id}"
    if not try_acquire(lock_key):
        raise HTTPException(status_code=409, detail="该推文正在分析中，请稍后再试")
    try:
        return analyze_single_tweet(db, tweet_id)
    finally:
        release(lock_key)


@router.post("/blogger/{blogger_handle}", response_model=AnalysisResponse)
def analyze_single_blogger(blogger_handle: str, db: Session = Depends(get_db)):
    """分析单个博主的推文"""
    if not try_acquire(blogger_handle):
        raise HTTPException(status_code=409, detail=f"正在分析 {blogger_handle}，请稍后再试")
    try:
        return analyze_by_blogger(db, blogger_handle)
    finally:
        release(blogger_handle)


@router.post("/bloggers", response_model=AnalysisResponse)
def analyze_multiple_bloggers(
    request: MultiBloggerRequest,
    db: Session = Depends(get_db),
):
    """多博主综合分析，交叉对比观点"""
    return analyze_by_bloggers(db, request.blogger_handles)
