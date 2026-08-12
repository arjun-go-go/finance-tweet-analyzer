"""Verify a prediction and recompute the blogger's credibility."""
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult
from app.models.instrument_correction_rule import InstrumentCorrectionRule
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.models.tweet import Tweet
from app.schemas.prediction import (
    CorrectInstrumentRequest,
    ExcludePredictionRequest,
    VERDICT_TO_SCORE,
    VerifyRequest,
)
from app.services.blogger_service import _serialize_prediction
from app.services.credibility import recompute_blogger
from app.services.instrument_resolver import (
    is_downstream_verified_ticker,
    validate_instrument_candidate,
)
from app.services.outbox_service import enqueue_outbox_event


def validate_prediction_instrument(body) -> dict:
    return validate_instrument_candidate(
        symbol=body.symbol,
        name=body.name,
        asset_type=body.asset_type,
        market=body.market,
    )


def _default_context_terms(old_symbol: str, old_item: dict | None) -> list[str]:
    original_name = str((old_item or {}).get("original_name") or "").lower()
    if old_symbol.upper() == "CL" and any(
        term in original_name for term in ("原油", "油价", "crude oil", "wti")
    ):
        return ["原油", "油价", "crude oil", "wti"]
    if old_symbol.upper() == "COIN" and any(
        term in original_name for term in ("circle", "usdc")
    ):
        return ["circle", "usdc"]
    return []


def _replace_analysis_instrument(
    analysis: AnalysisResult | None,
    old_symbol: str,
    snapshot: dict,
) -> bool:
    if not analysis or not analysis.result:
        return False
    result = deepcopy(analysis.result)
    replaced = False
    for item in result.get("tickers") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol") or "").upper() != old_symbol.upper():
            continue
        original_name = item.get("original_name")
        item.clear()
        item.update(snapshot)
        item["original_name"] = original_name or snapshot.get("original_name", "")
        item["original_extracted_symbol"] = old_symbol.upper()
        replaced = True
    if replaced:
        analysis.result = result
    return replaced


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
    if prediction.sentiment not in {"bullish", "bearish"}:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "non_directional_prediction",
                "message": "中性观点不构成可计分预测，请使用排除操作",
            },
        )
    if prediction.verdict == "excluded":
        raise HTTPException(status_code=409, detail="Excluded prediction cannot be scored")

    now = datetime.now(timezone.utc)
    if prediction.verifiable_at and prediction.verifiable_at > now:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "not_yet_verifiable",
                "verifiable_at": prediction.verifiable_at.isoformat(),
            },
        )

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
    latest_verification = db.execute(
        select(PredictionMarketVerification)
        .where(PredictionMarketVerification.prediction_id == prediction.id)
        .order_by(PredictionMarketVerification.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return _serialize_prediction(prediction, tweet, latest_verification)


def exclude_prediction(
    db: Session,
    prediction_id: str,
    body: ExcludePredictionRequest,
) -> dict:
    """Resolve an invalid prediction without affecting credibility scoring."""
    try:
        pid = uuid.UUID(prediction_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Prediction not found") from exc
    prediction = db.get(Prediction, pid)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if prediction.verdict is not None:
        raise HTTPException(status_code=409, detail="Prediction already resolved")

    prediction.verdict = "excluded"
    prediction.score = None
    prediction.verified_at = datetime.now(timezone.utc)
    prediction.verified_by = "manual_exclusion"
    prediction.note = body.reason.strip()
    recompute_blogger(db, prediction.blogger_handle)
    db.commit()

    tweet = db.get(Tweet, prediction.tweet_id)
    latest_verification = db.execute(
        select(PredictionMarketVerification)
        .where(PredictionMarketVerification.prediction_id == prediction.id)
        .order_by(PredictionMarketVerification.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return _serialize_prediction(prediction, tweet, latest_verification)


def correct_prediction_instrument(
    db: Session,
    prediction_id: str,
    body: CorrectInstrumentRequest,
    *,
    corrected_by: uuid.UUID | None = None,
) -> dict:
    """Replace an incorrectly mapped instrument while retaining audit history."""
    try:
        pid = uuid.UUID(prediction_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Prediction not found") from exc
    prediction = db.get(Prediction, pid)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if prediction.verdict is not None:
        raise HTTPException(status_code=409, detail="Prediction already resolved")

    old_symbol = prediction.ticker
    symbol = body.symbol.strip().upper().lstrip("$")
    name = body.name.strip()
    reason = body.reason.strip()
    if not symbol or not name or not reason:
        raise HTTPException(status_code=422, detail="Symbol, name and reason are required")

    validation = validate_instrument_candidate(
        symbol=symbol,
        name=name,
        asset_type=body.asset_type,
        market=body.market,
    )
    if not validation.get("accepted"):
        raise HTTPException(status_code=422, detail=validation.get("reason"))
    snapshot = dict(validation["instrument"])
    symbol = str(snapshot["symbol"]).upper()
    duplicate = db.execute(
        select(Prediction.id).where(
            Prediction.id != prediction.id,
            Prediction.blogger_handle == prediction.blogger_handle,
            Prediction.ticker == symbol,
            Prediction.sentiment == prediction.sentiment,
            Prediction.published_at >= prediction.published_at - timedelta(hours=24),
            Prediction.published_at <= prediction.published_at + timedelta(hours=24),
        ).limit(1)
    ).scalar_one_or_none()
    snapshot["manual_correction_reason"] = reason
    supported = is_downstream_verified_ticker(snapshot)

    analysis = db.get(AnalysisResult, prediction.analysis_id)
    old_item = next(
        (
            item for item in ((analysis.result or {}).get("tickers") or [])
            if isinstance(item, dict)
            and str(item.get("symbol") or "").upper() == old_symbol.upper()
        ),
        None,
    ) if analysis else None
    prediction.ticker = symbol
    prediction.instrument_snapshot = snapshot
    prediction.note = reason

    analysis_updated = _replace_analysis_instrument(analysis, old_symbol, snapshot)
    if analysis_updated:
        enqueue_outbox_event(
            db,
            "tweet.index_requested",
            {"tweet_id": str(prediction.tweet_id)},
        )
        enqueue_outbox_event(
            db,
            "analysis.index_requested",
            {"analysis_result_id": str(analysis.id)},
        )
        enqueue_outbox_event(
            db,
            "intelligence.project_requested",
            {"analysis_result_id": str(analysis.id)},
        )

    context_terms = list(dict.fromkeys(
        term.strip().lower()
        for term in (body.context_terms or _default_context_terms(old_symbol, old_item))
        if term.strip()
    ))
    learned_rule = None
    if old_symbol.upper() != symbol and context_terms:
        learned_rule = InstrumentCorrectionRule(
            source_symbol=old_symbol.upper(),
            context_terms=context_terms,
            corrected_instrument=snapshot,
            reason=reason,
            created_by=corrected_by,
        )
        db.add(learned_rule)

    duplicate_id = str(duplicate) if duplicate else None
    status = (
        "excluded_duplicate"
        if duplicate
        else "tracking"
        if supported
        else "market_data_unavailable"
    )
    evidence_reason = (
        f"标的已修正为 {symbol}；同一博主 24 小时内已有同方向预测，当前记录已合并排除"
        if duplicate
        else "标的已人工修正，将按新标的继续自动验证"
        if supported
        else "标的已人工修正；该资产不参与自动行情计分"
    )
    evidence = {
        "prediction_id": str(prediction.id),
        "status": status,
        "review_type": "duplicate_prediction" if duplicate else "instrument_identity",
        "reason": evidence_reason,
        "correction": {
            "old_symbol": old_symbol,
            "new_symbol": symbol,
            "name": name,
            "asset_type": body.asset_type,
            "market": body.market,
            "reason": reason,
            "validation": validation,
            "analysis_updated": analysis_updated,
            "context_terms": context_terms,
            "duplicate_prediction_id": duplicate_id,
        },
        "write_back_allowed": False,
    }
    applied_at = None
    if duplicate:
        applied_at = datetime.now(timezone.utc)
        prediction.verdict = "excluded"
        prediction.score = None
        prediction.verified_at = applied_at
        prediction.verified_by = "system_duplicate_after_correction_v1"
        prediction.note = evidence_reason
    verification = PredictionMarketVerification(
        prediction_id=prediction.id,
        status=status,
        provider="manual correction",
        provider_symbol=symbol,
        market=body.market,
        rule_version=(
            "manual_instrument_dedup_v1" if duplicate else "manual_instrument_v1"
        ),
        evidence=evidence,
        error_message=None if supported else evidence["reason"],
        applied=bool(duplicate),
        applied_at=applied_at,
    )
    db.add(verification)
    db.flush()
    if learned_rule:
        evidence["correction"]["learned_rule_id"] = str(learned_rule.id)
        verification.evidence = evidence
    if duplicate:
        recompute_blogger(db, prediction.blogger_handle)
    db.commit()
    db.refresh(verification)

    tweet = db.get(Tweet, prediction.tweet_id)
    return _serialize_prediction(prediction, tweet, verification)


def list_prediction_review_queue(
    db: Session,
    *,
    status: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return unresolved predictions using only their latest verification attempt."""
    ranked = (
        select(
            PredictionMarketVerification.id.label("verification_id"),
            PredictionMarketVerification.prediction_id,
            PredictionMarketVerification.status,
            func.row_number()
            .over(
                partition_by=PredictionMarketVerification.prediction_id,
                order_by=PredictionMarketVerification.created_at.desc(),
            )
            .label("row_number"),
        )
        .subquery()
    )
    latest = (
        select(ranked.c.verification_id, ranked.c.prediction_id, ranked.c.status)
        .where(ranked.c.row_number == 1)
        .subquery()
    )
    unresolved_statuses = ("manual_review", "market_data_unavailable")
    filters = [
        Prediction.verdict.is_(None),
        latest.c.status.in_(unresolved_statuses),
    ]
    if status != "all":
        filters.append(latest.c.status == status)

    base = (
        select(Prediction, Tweet, PredictionMarketVerification)
        .join(latest, latest.c.prediction_id == Prediction.id)
        .join(
            PredictionMarketVerification,
            PredictionMarketVerification.id == latest.c.verification_id,
        )
        .join(Tweet, Tweet.id == Prediction.tweet_id)
        .where(*filters)
    )
    total = db.scalar(
        select(func.count()).select_from(Prediction).join(
            latest, latest.c.prediction_id == Prediction.id
        ).where(*filters)
    ) or 0
    rows = db.execute(
        base.order_by(PredictionMarketVerification.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    latest_counts = dict(
        db.execute(
            select(latest.c.status, func.count())
            .join(Prediction, Prediction.id == latest.c.prediction_id)
            .where(
                Prediction.verdict.is_(None),
                latest.c.status.in_(unresolved_statuses),
            )
            .group_by(latest.c.status)
        ).all()
    )
    now = datetime.now(timezone.utc)
    stats = {
        "manual_review": int(latest_counts.get("manual_review", 0)),
        "market_data_unavailable": int(
            latest_counts.get("market_data_unavailable", 0)
        ),
        "due_pending": int(
            db.scalar(
                select(func.count()).select_from(Prediction)
                .outerjoin(latest, latest.c.prediction_id == Prediction.id)
                .where(
                    Prediction.verdict.is_(None),
                    Prediction.verifiable_at <= now,
                    or_(
                        latest.c.status.is_(None),
                        ~latest.c.status.in_(unresolved_statuses),
                    ),
                )
            )
            or 0
        ),
        "tracking": int(
            db.scalar(
                select(func.count()).select_from(Prediction)
                .outerjoin(latest, latest.c.prediction_id == Prediction.id)
                .where(
                    Prediction.verdict.is_(None),
                    Prediction.verifiable_at > now,
                    or_(
                        latest.c.status.is_(None),
                        ~latest.c.status.in_(unresolved_statuses),
                    ),
                )
            )
            or 0
        ),
        "auto_verified": int(
            db.scalar(
                select(func.count()).select_from(Prediction).where(
                    Prediction.verified_by == "market_auto_v1"
                )
            )
            or 0
        ),
    }
    return {
        "items": [
            _serialize_prediction(prediction, tweet, verification)
            for prediction, tweet, verification in rows
        ],
        "total": int(total),
        "stats": stats,
    }


def save_predictions_batch(db: Session, predictions: list[dict]) -> int:
    """批量保存预测记录（Celery 预测任务调用），内置去重逻辑。"""
    from datetime import timedelta

    from sqlalchemy import and_

    inserted = 0
    for cand in predictions:
        if cand.get("sentiment") not in {"bullish", "bearish"}:
            continue
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
