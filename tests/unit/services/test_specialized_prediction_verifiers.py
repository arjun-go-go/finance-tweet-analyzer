import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import (
    event_verification_service,
    fundamental_verification_service,
    price_target_verification_service,
)
from app.services.market_verification_service import PricePoint, PriceWindow


PUBLISHED_AT = datetime(2026, 8, 1, tzinfo=timezone.utc)
VERIFIABLE_AT = datetime(2026, 8, 20, tzinfo=timezone.utc)
AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _prediction(verifier_type: str, target_spec: dict, **overrides):
    values = {
        "id": uuid.uuid4(),
        "analysis_id": uuid.uuid4(),
        "tweet_id": uuid.uuid4(),
        "blogger_handle": "researcher",
        "ticker": "NVDA",
        "sentiment": "none",
        "prediction_type": verifier_type.replace("market_", ""),
        "target_spec": target_spec,
        "temporal_expression": "FY2026",
        "investment_horizon": "medium",
        "published_at": PUBLISHED_AT,
        "verifiable_at": VERIFIABLE_AT,
        "verifier_type": verifier_type,
        "scoring_eligible": True,
        "verdict": None,
        "instrument_snapshot": {
            "symbol": "NVDA",
            "market": "US",
            "asset_type": "equity",
            "validation_status": "verified",
            "validation_sources": ["sec_edgar"],
            "external_ids": {"cik": "1045810"},
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_price_target_uses_terminal_close_without_requiring_direction(monkeypatch):
    prediction = _prediction(
        "market_price_target",
        {
            "target_metric": "price",
            "target_operator": "gte",
            "target_value": "100",
            "target_unit": "USD",
        },
    )
    monkeypatch.setattr(
        price_target_verification_service,
        "preview_prediction_identity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        price_target_verification_service,
        "load_prediction_price_window",
        lambda *_args, **_kwargs: {
            "market": "US",
            "window": PriceWindow(
                source="fixture",
                symbol="NVDA",
                start=PricePoint(PUBLISHED_AT.isoformat(), 90.0),
                end=PricePoint(VERIFIABLE_AT.isoformat(), 110.0),
            ),
            "price_proxy": None,
        },
    )

    result = price_target_verification_service.preview_price_target_verification(
        object(), prediction, as_of=AS_OF
    )

    assert result["status"] == "ready"
    assert result["observed_value"] == 110.0
    assert result["preview_verdict"] == "correct"


def test_price_target_rejects_quote_currency_mismatch(monkeypatch):
    prediction = _prediction(
        "market_price_target",
        {
            "target_metric": "price",
            "target_operator": "gte",
            "target_value": "100",
            "target_unit": "CNY",
        },
    )
    monkeypatch.setattr(
        price_target_verification_service,
        "preview_prediction_identity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        price_target_verification_service,
        "load_prediction_price_window",
        lambda *_args, **_kwargs: {
            "market": "US",
            "window": PriceWindow(
                source="fixture",
                symbol="NVDA",
                start=PricePoint(PUBLISHED_AT.isoformat(), 90.0),
                end=PricePoint(VERIFIABLE_AT.isoformat(), 110.0),
            ),
            "price_proxy": None,
        },
    )

    result = price_target_verification_service.preview_price_target_verification(
        object(), prediction, as_of=AS_OF
    )

    assert result["status"] == "manual_review"
    assert result["review_type"] == "unit_mismatch"


def test_fundamental_metric_uses_formal_filing_value(monkeypatch):
    prediction = _prediction(
        "fundamental_metric",
        {
            "target_metric": "revenue",
            "target_operator": "gte",
            "target_value": "2000",
            "target_unit": "亿美元",
        },
        verifiable_at=None,
    )
    monkeypatch.setattr(
        fundamental_verification_service,
        "preview_prediction_identity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        fundamental_verification_service,
        "load_fundamental_observation",
        lambda _prediction: (
            {
                "value": 215_938_000_000.0,
                "unit": "USD",
                "period": "2026-01-25",
                "filed_at": "2026-02-25",
                "provider": "SEC EDGAR Company Facts",
                "provider_metric": "RevenueFromContractWithCustomerExcludingAssessedTax",
            },
            {"metric": "revenue", "fiscal_year": 2026, "market": "US", "symbol": "NVDA"},
        ),
    )

    result = fundamental_verification_service.preview_fundamental_verification(
        object(), prediction, as_of=AS_OF
    )

    assert result["status"] == "ready"
    assert result["observation"]["scaled_value"] == 2159.38
    assert result["preview_verdict"] == "correct"


def test_event_without_authoritative_date_is_not_auto_scored(monkeypatch):
    prediction = _prediction(
        "event_outcome",
        {
            "target_metric": "listing_status",
            "target_operator": "occurs",
            "target_value": "listed",
        },
    )
    monkeypatch.setattr(
        event_verification_service,
        "preview_prediction_identity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        event_verification_service,
        "validate_instrument_candidate",
        lambda **_kwargs: {
            "accepted": True,
            "reason": "verified",
            "instrument": {
                "symbol": "NVDA",
                "market": "US",
                "listing_status": "listed",
                "validation_status": "verified",
                "validation_sources": ["sec_edgar"],
            },
        },
    )

    result = event_verification_service.preview_event_verification(
        object(), prediction, as_of=AS_OF
    )

    assert result["status"] == "manual_review"
    assert result["review_type"] == "event_date_evidence"
