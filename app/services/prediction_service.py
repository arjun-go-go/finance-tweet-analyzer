"""Verify a prediction and recompute the blogger's credibility."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.schemas.prediction import VERDICT_TO_SCORE, VerifyRequest
from app.services.blogger_service import _serialize_prediction
from app.services.credibility import recompute_blogger


def verify_prediction(
    db: Session, prediction_id: str, body: VerifyRequest
) -> dict:
    try:
        pid = uuid.UUID(prediction_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Prediction not found") from exc

    prediction = db.execute(
        select(Prediction).where(Prediction.id == pid)
    ).scalar_one_or_none()
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")

    now = datetime.now(timezone.utc)
    # TODO: restore time lock after testing
    # if prediction.verifiable_at and prediction.verifiable_at > now:
    #     raise HTTPException(
    #         status_code=400,
    #         detail={
    #             "error": "not_yet_verifiable",
    #             "verifiable_at": prediction.verifiable_at.isoformat(),
    #         },
    #     )

    prediction.verdict = body.verdict
    prediction.score = VERDICT_TO_SCORE[body.verdict]
    prediction.verified_at = now
    prediction.verified_by = "manual"
    prediction.note = body.note
    db.flush()

    recompute_blogger(db, prediction.blogger_handle)
    db.commit()

    tweet = db.execute(
        select(Tweet).where(Tweet.id == prediction.tweet_id)
    ).scalar_one()
    return _serialize_prediction(prediction, tweet)


def save_predictions_batch(db: Session, predictions: list[dict]) -> int:
    """批量保存预测记录（Celery 预测任务调用），内置去重逻辑。"""
    from datetime import timedelta

    from sqlalchemy import and_

    inserted = 0
    for cand in predictions:
        pub = cand.get("published_at")
        if pub is None:
            continue
        existing = db.execute(
            select(Prediction.id).where(
                and_(
                    Prediction.blogger_handle == cand["blogger_handle"],
                    Prediction.ticker == cand["ticker"],
                    Prediction.sentiment == cand["sentiment"],
                    Prediction.published_at >= pub - timedelta(hours=24),
                    Prediction.published_at <= pub + timedelta(hours=24),
                )
            ).limit(1)
        ).first()
        if existing:
            continue

        db.add(Prediction(
            analysis_id=uuid.UUID(cand["analysis_id"]) if cand.get("analysis_id") else None,
            tweet_id=uuid.UUID(cand["tweet_id"]),
            blogger_handle=cand["blogger_handle"],
            ticker=cand["ticker"],
            sentiment=cand["sentiment"],
            investment_horizon=cand.get("investment_horizon", "unknown"),
            published_at=cand["published_at"],
            verifiable_at=cand["verifiable_at"],
        ))
        inserted += 1

    return inserted
