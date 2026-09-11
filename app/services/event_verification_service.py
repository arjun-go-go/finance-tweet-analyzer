"""Evidence-first verification for dated listing and IPO event forecasts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.services.credibility import recompute_blogger
from app.services.instrument_resolver import validate_instrument_candidate
from app.services.market_verification_service import _as_utc, preview_prediction_identity


RULE_VERSION = "event_outcome_v1"
SUPPORTED_EVENT_METRICS = {"ipo_status", "listing_status", "trading_status"}
_EVENT_ALIASES = {
    "ipo": "ipo_status",
    "listing": "listing_status",
    "listed": "listing_status",
    "starts_trading": "trading_status",
    "start_trading": "trading_status",
}


def canonical_event_metric(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return _EVENT_ALIASES.get(normalized, normalized)


def _parse_event_date(instrument: dict) -> datetime | None:
    for field in ("listing_date", "listed_at", "trading_started_at", "event_date"):
        raw = instrument.get(field)
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def preview_event_verification(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    now = _as_utc(as_of or datetime.now(timezone.utc))
    base = {
        "prediction_id": str(prediction.id),
        "prediction_type": prediction.prediction_type,
        "verifier_type": prediction.verifier_type,
        "ticker": prediction.ticker,
        "as_of": now.isoformat(),
        "verifiable_at": prediction.verifiable_at.isoformat() if prediction.verifiable_at else None,
        "write_back_allowed": False,
    }
    if prediction.verifier_type != "event_outcome" or not prediction.scoring_eligible:
        return {**base, "status": "unsupported", "reason": "不是已启用的事件预测契约"}
    if prediction.verdict is not None:
        return {**base, "status": "already_verified", "reason": "已有正式验证结果"}
    identity_result = preview_prediction_identity(
        db,
        prediction,
        require_direction=False,
    )
    if identity_result:
        return {**base, **identity_result, "as_of": now.isoformat()}
    if prediction.verifiable_at is None:
        return {**base, "status": "manual_review", "review_type": "event_time", "reason": "事件预测缺少截止日期"}
    if _as_utc(prediction.verifiable_at) > now:
        return {**base, "status": "tracking", "reason": "等待事件截止日期"}

    target = dict(prediction.target_spec or {})
    metric = canonical_event_metric(str(target.get("target_metric") or target.get("target_condition") or ""))
    if metric not in SUPPORTED_EVENT_METRICS:
        return {
            **base,
            "status": "manual_review",
            "review_type": "unsupported_event",
            "reason": "当前只自动核验 IPO、上市和开始交易事件；产品发布、审批等需人工证据",
            "target_spec": target,
        }
    instrument = dict(prediction.instrument_snapshot or {})
    result = validate_instrument_candidate(
        symbol=str(instrument.get("symbol") or prediction.ticker),
        name=str(instrument.get("original_name") or instrument.get("resolved_name") or prediction.ticker),
        asset_type=str(instrument.get("asset_type") or "equity"),
        market=str(instrument.get("market") or "US"),
    )
    observed = dict(result.get("instrument") or instrument)
    observation = {
        "accepted": bool(result.get("accepted")),
        "reason": result.get("reason"),
        "validation_status": observed.get("validation_status"),
        "listing_status": observed.get("listing_status"),
        "validation_sources": observed.get("validation_sources") or [],
    }
    event_date = _parse_event_date(observed)
    if event_date is None:
        return {
            **base,
            "status": "manual_review",
            "review_type": "event_date_evidence",
            "reason": "公开目录只能确认当前身份，缺少可证明事件发生在预测窗口内的日期，禁止自动计分",
            "target_spec": target,
            "observation": observation,
        }

    window_start = _as_utc(prediction.published_at)
    window_end = _as_utc(prediction.verifiable_at)
    occurred = window_start < event_date <= window_end
    operator = str(target.get("target_operator") or "occurs")
    expected = operator != "not_occurs"
    correct = occurred == expected
    verdict = "correct" if correct else "incorrect"
    score = 1.0 if correct else 0.0
    return {
        **base,
        "status": "ready",
        "provider": ", ".join(observation["validation_sources"]) or "public instrument catalog",
        "provider_symbol": str(observed.get("symbol") or prediction.ticker),
        "market": observed.get("market"),
        "target_spec": target,
        "observation": {**observation, "event_date": event_date.isoformat(), "occurred_in_window": occurred},
        "preview_verdict": verdict,
        "preview_score": score,
        "reason": "事件日期已由公开目录证明并落在预测窗口内" if occurred else "事件日期不在预测窗口内",
    }


def _audit(prediction: Prediction, result: dict) -> PredictionMarketVerification:
    observation = result.get("observation") or {}
    return PredictionMarketVerification(
        prediction_id=prediction.id,
        verification_type="event_outcome",
        status=str(result.get("status") or "manual_review"),
        provider=result.get("provider"),
        provider_symbol=result.get("provider_symbol") or prediction.ticker,
        market=result.get("market"),
        end_observed_at=observation.get("event_date"),
        proposed_verdict=result.get("preview_verdict"),
        proposed_score=result.get("preview_score"),
        rule_version=RULE_VERSION,
        evidence=result,
        observation=observation,
        error_message=(str(result.get("reason")) if result.get("status") == "manual_review" else None),
    )


def verify_event_prediction(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    now = as_of or datetime.now(timezone.utc)
    result = preview_event_verification(db, prediction, as_of=now)
    audit = _audit(prediction, result)
    db.add(audit)
    if result.get("status") != "ready":
        db.flush()
        return result
    prediction.verdict = str(result["preview_verdict"])
    prediction.score = float(result["preview_score"])
    prediction.verified_at = now
    prediction.verified_by = RULE_VERSION
    prediction.note = str(result.get("reason") or "事件验证完成")
    audit.applied = True
    audit.applied_at = now
    recompute_blogger(db, prediction.blogger_handle)
    db.flush()
    return {**result, "write_back_allowed": True, "applied": True}


def run_due_event_verifications(
    db: Session,
    *,
    batch_size: int | None = None,
    as_of: datetime | None = None,
) -> dict:
    if not settings.auto_verification_enabled:
        return {"status": "disabled", "processed": 0, "applied": 0}
    now = as_of or datetime.now(timezone.utc)
    retry_cutoff = now - timedelta(hours=settings.auto_verification_retry_hours)
    rows = db.execute(
        select(Prediction)
        .where(
            Prediction.verdict.is_(None),
            Prediction.scoring_eligible.is_(True),
            Prediction.verifier_type == "event_outcome",
            Prediction.verifiable_at.is_not(None),
            Prediction.verifiable_at <= now,
            or_(
                Prediction.instrument_snapshot.has_key("manual_correction_reason"),
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                    PredictionMarketVerification.status == "manual_review",
                    PredictionMarketVerification.created_at >= retry_cutoff,
                ),
            ),
        )
        .order_by(Prediction.verifiable_at.asc())
        .limit(batch_size or settings.auto_verification_batch_size)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    stats = {"status": "completed", "processed": 0, "applied": 0, "tracking": 0, "manual_review": 0}
    for prediction in rows:
        result = verify_event_prediction(db, prediction, as_of=now)
        stats["processed"] += 1
        if result.get("applied"):
            stats["applied"] += 1
        elif result.get("status") in stats:
            stats[str(result["status"])] += 1
    db.commit()
    return stats
