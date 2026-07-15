from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_user
from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.models.user import User
from app.schemas.dashboard import DashboardOverview

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def get_overview(
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_tweets = db.execute(select(func.count(Tweet.id))).scalar() or 0
    pending_tweets = db.execute(
        select(func.count(Tweet.id)).where(Tweet.status == "pending")
    ).scalar() or 0
    analyzed_tweets = db.execute(
        select(func.count(Tweet.id)).where(Tweet.status == "analyzed")
    ).scalar() or 0
    total_analyses = db.execute(
        select(func.count(AnalysisResult.id)).where(
            AnalysisResult.analysis_type == "tweet_analysis"
        )
    ).scalar() or 0
    total_bloggers = db.execute(select(func.count(Blogger.id))).scalar() or 0
    pending_predictions = db.execute(
        select(func.count(Prediction.id)).where(Prediction.verdict.is_(None))
    ).scalar() or 0

    recent_tickers_query = (
        select(AnalysisResult)
        .where(AnalysisResult.analysis_type == "ticker_summary")
        .order_by(AnalysisResult.created_at.desc())
        .limit(10)
    )
    recent = db.execute(recent_tickers_query).scalars().all()
    top_tickers = [
        {"id": str(r.id), "result": r.result, "confidence": r.confidence}
        for r in recent
    ]

    return DashboardOverview(
        total_tweets=total_tweets,
        pending_tweets=pending_tweets,
        analyzed_tweets=analyzed_tweets,
        total_analyses=total_analyses,
        total_bloggers=total_bloggers,
        pending_predictions=pending_predictions,
        top_tickers=top_tickers,
    )
