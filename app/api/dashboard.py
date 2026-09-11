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
from app.services.instrument_claim_aggregation_service import aggregate_instrument_claims

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def get_overview(
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_tweets = db.execute(select(func.count(Tweet.id))).scalar() or 0
    pending_tweets = db.execute(
        select(func.count(Tweet.id)).where(
            Tweet.status.in_([
                "media_pending",
                "media_archiving",
                "media_analysis_ready",
                "media_analyzing",
                "pending",
                "analyzing",
                "retrying",
            ])
        )
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
        select(func.count(Prediction.id)).where(
            Prediction.verdict.is_(None),
            Prediction.scoring_eligible.is_(True),
        )
    ).scalar() or 0

    recent = [
        row
        for row in aggregate_instrument_claims(db)
        if row["has_effective_views"] and row["recommendation_score"] is not None
    ][:10]
    top_tickers = [
        {
            "id": row["ticker"],
            "result": row,
            "confidence": row["recommendation_score"] / 100,
        }
        for row in recent
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
