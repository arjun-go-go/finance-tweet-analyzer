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
SCORED_VERDICTS = ("correct", "partial", "incorrect")


def compute_score(correct_sum: float, total: int) -> float:
    if total == 0:
        return NEUTRAL_PRIOR
    return (correct_sum + ALPHA) / (total + ALPHA + BETA) * 100


def score_profile(correct_sum: float, total: int) -> dict:
    """Return the score together with the sample maturity needed to interpret it."""
    score = compute_score(correct_sum, total)
    raw_accuracy = correct_sum / total if total else None
    if total == 0:
        status, label = "no_data", "暂无已验证预测"
    elif total < 5:
        status, label = "early", "样本很少，仅供参考"
    elif total < 15:
        status, label = "developing", "样本积累中"
    else:
        status, label = "established", "样本相对稳定"
    return {
        "credibility_score": round(score, 2),
        "score_status": status,
        "score_label": label,
        "sample_confidence": round(min(total / 20, 1.0), 2),
        "raw_accuracy": round(raw_accuracy, 4) if raw_accuracy is not None else None,
        "verified_samples": total,
    }


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
            Prediction.scoring_eligible.is_(True),
            Prediction.verdict.in_(SCORED_VERDICTS),
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
