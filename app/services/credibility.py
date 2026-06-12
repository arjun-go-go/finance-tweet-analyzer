"""Bayesian-smoothed credibility scoring for bloggers.

Score formula: (correct_sum + ALPHA) / (total + ALPHA + BETA) * 100
- ALPHA = BETA = 5 (neutral 50.0 prior)
- correct_sum is FLOAT; partial verdicts contribute 0.5
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.blogger import Blogger
from app.models.prediction import Prediction

ALPHA = 5
BETA = 5
NEUTRAL_PRIOR = 50.0


def compute_score(correct_sum: float, total: int) -> float:
    if total == 0:
        return NEUTRAL_PRIOR
    return (correct_sum + ALPHA) / (total + ALPHA + BETA) * 100


def recompute_blogger(db: Session, handle: str) -> None:
    """Recompute total_predictions / correct_predictions on the Blogger row.

    total_predictions = COUNT(*) WHERE verdict IS NOT NULL
    correct_predictions = COALESCE(SUM(score), 0) WHERE verdict IS NOT NULL
    """
    row = db.execute(
        select(
            func.count(Prediction.id).label("total"),
            func.coalesce(func.sum(Prediction.score), 0.0).label("correct_sum"),
        ).where(
            Prediction.blogger_handle == handle,
            Prediction.verdict.is_not(None),
        )
    ).one()

    blogger = db.execute(
        select(Blogger).where(Blogger.handle == handle)
    ).scalar_one_or_none()
    if blogger is None:
        return

    blogger.total_predictions = int(row.total)
    blogger.correct_predictions = float(row.correct_sum)
    blogger.credibility_score = compute_score(
        float(row.correct_sum), int(row.total)
    )
