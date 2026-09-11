"""Deterministic dispatcher for type-specific prediction verifiers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.prediction import Prediction


ACTIVE_VERIFIERS = {
    "market_price_direction",
    "market_price_target",
    "fundamental_metric",
    "event_outcome",
}


def preview_prediction_verification(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    if prediction.verifier_type == "market_price_direction":
        from app.services.market_verification_service import (
            preview_prediction_verification as preview_market_direction,
        )

        return preview_market_direction(db, prediction, as_of=as_of)
    if prediction.verifier_type == "market_price_target":
        from app.services.price_target_verification_service import (
            preview_price_target_verification,
        )

        return preview_price_target_verification(db, prediction, as_of=as_of)
    if prediction.verifier_type == "fundamental_metric":
        from app.services.fundamental_verification_service import (
            preview_fundamental_verification,
        )

        return preview_fundamental_verification(db, prediction, as_of=as_of)
    if prediction.verifier_type == "event_outcome":
        from app.services.event_verification_service import preview_event_verification

        return preview_event_verification(db, prediction, as_of=as_of)
    return {
        "prediction_id": str(prediction.id),
        "prediction_type": prediction.prediction_type,
        "verifier_type": prediction.verifier_type,
        "status": "unsupported",
        "reason": "预测契约已保存，专用确定性验证器尚未启用",
        "write_back_allowed": False,
    }


def verify_due_prediction(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    if prediction.verifier_type == "market_price_direction":
        from app.services.market_verification_service import (
            verify_due_prediction as verify_market_direction,
        )

        return verify_market_direction(db, prediction, as_of=as_of)
    if prediction.verifier_type == "market_price_target":
        from app.services.price_target_verification_service import (
            verify_price_target_prediction,
        )

        return verify_price_target_prediction(db, prediction, as_of=as_of)
    if prediction.verifier_type == "fundamental_metric":
        from app.services.fundamental_verification_service import (
            verify_fundamental_prediction,
        )

        return verify_fundamental_prediction(db, prediction, as_of=as_of)
    if prediction.verifier_type == "event_outcome":
        from app.services.event_verification_service import verify_event_prediction

        return verify_event_prediction(db, prediction, as_of=as_of)
    return {
        "prediction_id": str(prediction.id),
        "prediction_type": prediction.prediction_type,
        "verifier_type": prediction.verifier_type,
        "status": "unsupported",
    }


def run_due_prediction_verifications(
    db: Session,
    *,
    batch_size: int | None = None,
    as_of: datetime | None = None,
) -> dict:
    """Run all active deterministic verifiers and return per-type evidence."""
    from app.services.market_verification_service import run_due_market_verifications
    from app.services.price_target_verification_service import (
        run_due_price_target_verifications,
    )
    from app.services.fundamental_verification_service import (
        run_due_fundamental_verifications,
    )
    from app.services.event_verification_service import run_due_event_verifications

    results = {
        "market_price_direction": run_due_market_verifications(
            db, batch_size=batch_size, as_of=as_of
        ),
        "market_price_target": run_due_price_target_verifications(
            db, batch_size=batch_size, as_of=as_of
        ),
        "fundamental_metric": run_due_fundamental_verifications(
            db, batch_size=batch_size, as_of=as_of
        ),
        "event_outcome": run_due_event_verifications(
            db, batch_size=batch_size, as_of=as_of
        ),
    }
    return {
        "status": "completed",
        "processed": sum(int(result.get("processed") or 0) for result in results.values()),
        "applied": sum(int(result.get("applied") or 0) for result in results.values()),
        "active_verifiers": sorted(ACTIVE_VERIFIERS),
        "verifiers": results,
    }
