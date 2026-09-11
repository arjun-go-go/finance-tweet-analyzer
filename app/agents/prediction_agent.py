"""Convert canonical claims into auditable, type-aware prediction contracts."""

from datetime import datetime, timedelta, timezone

from app.services.instrument_resolver import is_downstream_verified_ticker
from app.services.event_verification_service import (
    SUPPORTED_EVENT_METRICS,
    canonical_event_metric,
)
from app.services.fundamental_verification_service import (
    SUPPORTED_METRICS,
    canonical_fundamental_metric,
)
from app.services.prediction_contract_math import parse_numeric_target
from app.services.prediction_time_resolver import resolve_prediction_time


PREDICTION_RULE_VERSION = "prediction_contract_v2"
PREDICTION_MIN_CONFIDENCE = 0.65
VERIFIER_BY_TYPE = {
    "price_direction": "market_price_direction",
    "price_target": "market_price_target",
    "fundamental_metric": "fundamental_metric",
    "event_outcome": "event_outcome",
}
ACTIVE_AUTO_VERIFIERS = {
    "market_price_direction",
    "market_price_target",
    "fundamental_metric",
    "event_outcome",
}


def evaluate_claim_prediction_eligibility(
    claim: dict,
    *,
    analysis: dict | None = None,
    tweet: dict | None = None,
) -> dict:
    """Return the auditable eligibility decision for one atomic claim."""
    analysis = analysis or {}
    tweet = tweet or {}
    instrument = claim.get("instrument") or {}
    forecast = dict(claim.get("forecast") or {})
    prediction_type = str(forecast.get("prediction_type") or "none")
    forecast_source = str(forecast.get("forecast_source") or "unclear")
    author_adopted = forecast.get("author_adopted") is True
    verifier_type = VERIFIER_BY_TYPE.get(prediction_type, "unsupported")
    reason_codes: list[str] = []

    if not (
        analysis.get("is_investment_relevant", True)
        or analysis.get("is_investment_related", False)
    ):
        reason_codes.append("not_investment_relevant")
    raw_sponsor_relation = claim.get("sponsor_relation")
    sponsor_relation = str(
        raw_sponsor_relation
        or ("unclear" if analysis.get("is_sponsored") is True else "none")
    )
    if sponsor_relation == "direct":
        reason_codes.append("sponsor_related")
    elif sponsor_relation == "unclear":
        reason_codes.append("sponsor_relation_unclear")
    if tweet.get("tweet_type") == "retweet":
        reason_codes.append("pure_retweet")
    if claim.get("opinion_source") != "author":
        reason_codes.append("opinion_not_author")
    if forecast_source != "author" and not author_adopted:
        reason_codes.append("forecast_not_author_committed")
    if claim.get("claim_type") not in {"prediction", "recommendation"}:
        reason_codes.append("claim_type_not_predictive")
    if prediction_type not in VERIFIER_BY_TYPE:
        reason_codes.append("forecast_target_missing")
    if prediction_type == "price_direction" and claim.get("direction") not in {
        "bullish",
        "bearish",
    }:
        reason_codes.append("direction_missing")
    if prediction_type == "price_target" and not forecast.get("target_value"):
        reason_codes.append("price_target_missing")
    if prediction_type == "price_target" and forecast.get("target_value"):
        try:
            parse_numeric_target(
                str(forecast.get("target_value") or ""),
                str(forecast.get("target_unit") or ""),
            )
        except ValueError:
            reason_codes.append("price_target_unparseable")
    if prediction_type == "fundamental_metric":
        metric = canonical_fundamental_metric(str(forecast.get("target_metric") or ""))
        if not metric or not forecast.get("target_value"):
            reason_codes.append("fundamental_target_missing")
        elif metric not in SUPPORTED_METRICS:
            reason_codes.append("fundamental_metric_unsupported")
        elif str(instrument.get("market") or instrument.get("market_hint") or "").upper() not in {"CN", "HK", "US"}:
            reason_codes.append("fundamental_market_unsupported")
        else:
            try:
                parse_numeric_target(
                    str(forecast.get("target_value") or ""),
                    str(forecast.get("target_unit") or ""),
                )
            except ValueError:
                reason_codes.append("fundamental_target_unparseable")
    if prediction_type == "event_outcome" and not any(
        forecast.get(field)
        for field in ("target_metric", "target_value", "target_condition")
    ):
        reason_codes.append("event_definition_missing")
    if prediction_type == "event_outcome":
        event_metric = canonical_event_metric(
            str(forecast.get("target_metric") or forecast.get("target_condition") or "")
        )
        if event_metric not in SUPPORTED_EVENT_METRICS:
            reason_codes.append("event_verifier_unsupported")
    if float(claim.get("confidence") or 0) < PREDICTION_MIN_CONFIDENCE:
        reason_codes.append("claim_confidence_below_threshold")
    if not (claim.get("evidence") or claim.get("media_evidence")):
        reason_codes.append("grounding_evidence_missing")
    if not (
        claim.get("downstream_eligible") is True
        or is_downstream_verified_ticker(instrument)
    ):
        reason_codes.append("instrument_not_verified")

    published_at = claim.get("published_at") or tweet.get("published_at")
    time_resolution = None
    if isinstance(published_at, datetime):
        time_resolution = resolve_prediction_time(claim, published_at)
        if time_resolution.status == "missing":
            reason_codes.append("time_basis_missing")
        elif time_resolution.status == "invalid_past_target":
            reason_codes.append("time_target_not_future")
    else:
        reason_codes.append("published_at_missing")

    scoring_reason_codes: list[str] = []
    if verifier_type not in ACTIVE_AUTO_VERIFIERS:
        scoring_reason_codes.append("verifier_not_active")
    target_date_required = verifier_type in {
        "market_price_direction",
        "market_price_target",
        "event_outcome",
    }
    if target_date_required and (
        time_resolution is None or time_resolution.target_at is None
    ):
        scoring_reason_codes.append("target_date_unresolved")
    scoring_eligible = not reason_codes and not scoring_reason_codes

    return {
        "rule_version": PREDICTION_RULE_VERSION,
        "claim_id": str(claim.get("id") or ""),
        "eligible": not reason_codes,
        "reason_codes": reason_codes,
        "prediction_type": prediction_type,
        "forecast_source": forecast_source,
        "author_adopted": author_adopted,
        "verifier_type": verifier_type,
        "scoring_eligible": scoring_eligible,
        "scoring_reason_codes": scoring_reason_codes,
        "time_resolution": time_resolution.evidence() if time_resolution else None,
        "minimum_confidence": PREDICTION_MIN_CONFIDENCE,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def evaluate_prediction_eligibility(
    analysis: dict,
    tweet: dict | None = None,
    claims: list[dict] | None = None,
) -> dict:
    """Aggregate claim decisions for the analysis processing status only."""
    claim_items = claims if claims is not None else list(analysis.get("claims") or [])
    decisions = []
    for claim in claim_items:
        if not isinstance(claim, dict):
            continue
        decisions.append(
            evaluate_claim_prediction_eligibility(
            {
                **claim,
                "published_at": claim.get("published_at")
                or (tweet or {}).get("published_at"),
            },
            analysis=analysis,
            tweet=tweet,
        )
        )
    eligible_claim_ids = [
        decision["claim_id"]
        for decision in decisions
        if decision["eligible"] and decision["claim_id"]
    ]
    scoring_claim_ids = [
        decision["claim_id"]
        for decision in decisions
        if decision["scoring_eligible"] and decision["claim_id"]
    ]
    return {
        "rule_version": PREDICTION_RULE_VERSION,
        "eligible": bool(eligible_claim_ids),
        "reason_codes": [] if eligible_claim_ids else ["no_eligible_claim"],
        "eligible_claim_ids": eligible_claim_ids,
        "scoring_claim_ids": scoring_claim_ids,
        "claim_decisions": decisions,
        "minimum_confidence": PREDICTION_MIN_CONFIDENCE,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def prediction_agent_node(state: dict) -> dict:
    """Deterministically generate prediction candidates from canonical claims."""
    return {"predictions": _generate_predictions(state.get("claims", []))}


def _generate_predictions(claims: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen_by_key: dict[tuple[str, str, str, str, str, str], datetime] = {}
    sorted_claims = sorted(
        [claim for claim in claims if claim.get("published_at")],
        key=lambda claim: claim["published_at"],
    )

    for claim in sorted_claims:
        decision = evaluate_claim_prediction_eligibility(
            claim,
            analysis={
                "is_investment_relevant": claim.get("is_investment_relevant", True),
                "is_investment_related": claim.get("is_investment_related", True),
            },
            tweet={
                "tweet_type": claim.get("tweet_type", "original"),
                "published_at": claim.get("published_at"),
            },
        )
        if not decision["eligible"]:
            continue

        instrument = claim.get("instrument") or {}
        symbol = str(instrument.get("symbol") or "").upper()
        direction = str(claim.get("direction") or "none")
        forecast = dict(claim.get("forecast") or {})
        prediction_type = str(forecast.get("prediction_type") or "none")
        published_at: datetime = claim["published_at"]
        time_resolution = resolve_prediction_time(claim, published_at)
        horizon = time_resolution.horizon
        key = (
            str(claim.get("blogger_handle") or ""),
            symbol,
            prediction_type,
            direction,
            horizon,
            str(forecast.get("target_value") or forecast.get("target_condition") or ""),
        )
        prior = seen_by_key.get(key)
        if prior is not None and abs(published_at - prior) < timedelta(hours=24):
            continue
        seen_by_key[key] = published_at
        output.append(
            {
                "claim_id": str(claim["id"]),
                "analysis_id": str(claim["analysis_result_id"]),
                "tweet_id": str(claim["tweet_id"]),
                "blogger_handle": claim["blogger_handle"],
                "ticker": symbol,
                "sentiment": direction,
                "prediction_type": prediction_type,
                "target_spec": forecast,
                "temporal_expression": time_resolution.temporal_expression or None,
                "investment_horizon": horizon,
                "horizon_source": time_resolution.source,
                "time_confidence": time_resolution.confidence,
                "published_at": published_at,
                "verifiable_at": time_resolution.target_at,
                "verifier_type": decision["verifier_type"],
                "scoring_eligible": decision["scoring_eligible"],
                "verification_policy_version": (
                    "market_price_direction_v2"
                    if decision["verifier_type"] == "market_price_direction"
                    else "market_price_target_v1"
                    if decision["verifier_type"] == "market_price_target"
                    else "fundamental_metric_v1"
                    if decision["verifier_type"] == "fundamental_metric"
                    else "event_outcome_v1"
                    if decision["verifier_type"] == "event_outcome"
                    else "pending_verifier_v1"
                ),
                "instrument_snapshot": instrument,
                "eligibility_passed": True,
                "creation_rule_version": PREDICTION_RULE_VERSION,
                "creation_evidence": decision,
            }
        )
    return output
