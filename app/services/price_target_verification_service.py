"""Deterministic terminal-price verification for explicit price targets."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.services.credibility import recompute_blogger
from app.services.market_verification_service import (
    _as_utc,
    load_prediction_price_window,
    preview_prediction_identity,
)
from app.services.prediction_contract_math import (
    parse_numeric_target,
    scale_observed_value,
    score_numeric_target,
)


RULE_VERSION = "market_price_target_v1"


def _target_currency(unit: str) -> str | None:
    normalized = str(unit or "").upper()
    if "USDT" in normalized:
        return "USDT"
    if "美元" in unit or "USD" in normalized or "$" in normalized:
        return "USD"
    if "港元" in unit or "港币" in unit or "HKD" in normalized:
        return "HKD"
    if "人民币" in unit or "CNY" in normalized or "RMB" in normalized:
        return "CNY"
    return None


def _quote_currency(market: str, ticker: str) -> str:
    if market == "CN":
        return "CNY"
    if market == "HK":
        return "HKD"
    if market == "US":
        return "USD"
    if market == "CRYPTO":
        return "USDT"
    if market == "COMMODITY":
        return "USDT" if ticker.upper() == "XAU" else "USD"
    return "price"


def _base(prediction: Prediction, as_of: datetime) -> dict:
    return {
        "prediction_id": str(prediction.id),
        "prediction_type": prediction.prediction_type,
        "verifier_type": prediction.verifier_type,
        "ticker": prediction.ticker,
        "published_at": prediction.published_at.isoformat(),
        "verifiable_at": prediction.verifiable_at.isoformat() if prediction.verifiable_at else None,
        "as_of": as_of.isoformat(),
        "is_due": bool(
            prediction.verifiable_at
            and _as_utc(prediction.verifiable_at) <= as_of
        ),
        "write_back_allowed": False,
    }


def preview_price_target_verification(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    now = _as_utc(as_of or datetime.now(timezone.utc))
    base = _base(prediction, now)
    if prediction.verifier_type != "market_price_target" or not prediction.scoring_eligible:
        return {**base, "status": "unsupported", "reason": "不是已启用的目标价预测契约"}
    if prediction.verifiable_at is None:
        return {**base, "status": "target_date_unresolved", "reason": "目标价预测缺少截止日期"}
    if prediction.verdict is not None:
        return {**base, "status": "already_verified", "reason": "已有正式验证结果"}

    identity_result = preview_prediction_identity(
        db,
        prediction,
        require_direction=False,
    )
    if identity_result:
        return {**base, **identity_result, "as_of": now.isoformat()}

    target_spec = dict(prediction.target_spec or {})
    try:
        target = parse_numeric_target(
            str(target_spec.get("target_value") or ""),
            str(target_spec.get("target_unit") or ""),
        )
    except ValueError as exc:
        return {
            **base,
            "status": "manual_review",
            "review_type": "target_contract",
            "reason": str(exc),
            "target_spec": target_spec,
        }

    end_at = min(now, _as_utc(prediction.verifiable_at))
    try:
        market_result = load_prediction_price_window(db, prediction, end_at)
    except Exception as exc:
        logger.warning("Price-target verification failed for {}: {}", prediction.id, exc)
        return {
            **base,
            "status": "market_data_unavailable",
            "review_type": "market_data",
            "reason": str(exc),
            "target_spec": target_spec,
        }

    window = market_result["window"]
    raw_return = window.end.price / window.start.price - 1
    if target.is_percent:
        actual = raw_return * 100
        observed_unit = "%"
    else:
        market = str(market_result.get("market") or "").upper()
        quote_currency = _quote_currency(market, prediction.ticker)
        expected_currency = _target_currency(str(target_spec.get("target_unit") or ""))
        compatible_currencies = {quote_currency}
        if quote_currency == "USDT":
            compatible_currencies.add("USD")
        if expected_currency and expected_currency not in compatible_currencies:
            return {
                **base,
                "status": "manual_review",
                "review_type": "unit_mismatch",
                "reason": (
                    f"目标价格单位 {expected_currency} 与行情报价单位 "
                    f"{quote_currency} 不一致，禁止自动换算计分"
                ),
                "target_spec": target_spec,
                "market": market,
            }
        actual = scale_observed_value(window.end.price, target)
        observed_unit = quote_currency

    operator = str(target_spec.get("target_operator") or "unknown")
    if operator == "unknown":
        if target.low != target.high:
            operator = "range"
        elif prediction.sentiment == "bullish":
            operator = "gte"
        elif prediction.sentiment == "bearish":
            operator = "lte"
    try:
        verdict, score, comparison = score_numeric_target(actual, target, operator)
    except ValueError as exc:
        return {
            **base,
            "status": "manual_review",
            "review_type": "target_contract",
            "reason": str(exc),
            "target_spec": target_spec,
        }

    result = {
        **base,
        "status": "ready" if base["is_due"] else "tracking",
        "market": market_result["market"],
        "price_window": asdict(window),
        "price_proxy": market_result.get("price_proxy"),
        "raw_return": round(raw_return, 6),
        "target_spec": target_spec,
        "parsed_target": target.evidence(),
        "observed_value": round(actual, 8),
        "observed_unit": observed_unit,
        "comparison": comparison,
        "preview_verdict": verdict,
        "preview_score": score,
        "reason": "按截止日最后可用收盘价验证目标" if base["is_due"] else "等待目标截止日",
    }
    return result


def _audit(prediction: Prediction, result: dict) -> PredictionMarketVerification:
    window = result.get("price_window") or {}
    start = window.get("start") or {}
    end = window.get("end") or {}
    return PredictionMarketVerification(
        prediction_id=prediction.id,
        verification_type="market_price_target",
        status=str(result.get("status") or "market_data_unavailable"),
        provider=window.get("source"),
        provider_symbol=window.get("symbol") or prediction.ticker,
        market=result.get("market"),
        start_observed_at=start.get("observed_at"),
        start_price=start.get("price"),
        end_observed_at=end.get("observed_at"),
        end_price=end.get("price"),
        raw_return=result.get("raw_return"),
        threshold=(result.get("parsed_target") or {}).get("low"),
        proposed_verdict=result.get("preview_verdict"),
        proposed_score=result.get("preview_score"),
        rule_version=RULE_VERSION,
        evidence=result,
        observation={
            "price_window": window,
            "observed_value": result.get("observed_value"),
            "observed_unit": result.get("observed_unit"),
            "comparison": result.get("comparison"),
        },
        error_message=(
            str(result.get("reason"))
            if result.get("status") in {"manual_review", "market_data_unavailable"}
            else None
        ),
    )


def verify_price_target_prediction(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    now = _as_utc(as_of or datetime.now(timezone.utc))
    if prediction.verdict is not None:
        return {"prediction_id": str(prediction.id), "status": "already_verified"}
    if prediction.verifiable_at is None or _as_utc(prediction.verifiable_at) > now:
        return {"prediction_id": str(prediction.id), "status": "not_due"}
    result = preview_price_target_verification(db, prediction, as_of=now)
    audit = _audit(prediction, result)
    db.add(audit)
    if result.get("status") != "ready":
        db.flush()
        return result

    prediction.verdict = str(result["preview_verdict"])
    prediction.score = float(result["preview_score"])
    prediction.verified_at = now
    prediction.verified_by = RULE_VERSION
    prediction.note = (
        f"terminal={result.get('observed_value')} {result.get('observed_unit')}; "
        f"target={result.get('parsed_target')}"
    )
    audit.applied = True
    audit.applied_at = now
    recompute_blogger(db, prediction.blogger_handle)
    db.flush()
    return {**result, "write_back_allowed": True, "applied": True}


def run_due_price_target_verifications(
    db: Session,
    *,
    batch_size: int | None = None,
    as_of: datetime | None = None,
) -> dict:
    if not settings.auto_verification_enabled:
        return {"status": "disabled", "processed": 0, "applied": 0}
    now = _as_utc(as_of or datetime.now(timezone.utc))
    retry_cutoff = now - timedelta(hours=settings.auto_verification_retry_hours)
    rows = db.execute(
        select(Prediction)
        .where(
            Prediction.verdict.is_(None),
            Prediction.scoring_eligible.is_(True),
            Prediction.verifier_type == "market_price_target",
            Prediction.verifiable_at.is_not(None),
            Prediction.verifiable_at <= now,
            or_(
                Prediction.instrument_snapshot.has_key("manual_correction_reason"),
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                    PredictionMarketVerification.status == "manual_review",
                ),
            ),
            or_(
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                    PredictionMarketVerification.status == "market_data_unavailable",
                ),
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                    PredictionMarketVerification.status == "market_data_unavailable",
                    PredictionMarketVerification.created_at >= retry_cutoff,
                ),
            ),
        )
        .order_by(Prediction.verifiable_at.asc())
        .limit(batch_size or settings.auto_verification_batch_size)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    stats = {"status": "completed", "processed": 0, "applied": 0, "manual_review": 0, "market_data_unavailable": 0}
    for prediction in rows:
        result = verify_price_target_prediction(db, prediction, as_of=now)
        stats["processed"] += 1
        if result.get("applied"):
            stats["applied"] += 1
        elif result.get("status") in stats:
            stats[str(result["status"])] += 1
    db.commit()
    return stats
