import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.agents.prediction_agent import (
    PREDICTION_RULE_VERSION,
    _generate_predictions,
    evaluate_claim_prediction_eligibility,
)
from app.models.analysis import AnalysisResult
from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.services.market_verification_service import (
    _audit_from_result,
    _identity_tracking_result,
    _identity_gate,
    preview_prediction_identity,
)
from app.services import instrument_resolver, market_verification_service
from app.services.prediction_service import _default_context_terms, save_predictions_batch


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _ticker(sentiment: str) -> dict:
    return {
        "symbol": "NET",
        "sentiment": sentiment,
        "horizon": "medium",
        "asset_type": "equity",
        "market": "US",
        "tradable": True,
        "validation_status": "verified",
        "validation_sources": ["sec_edgar"],
        "original_name": "Cloudflare",
        "resolved_name": "Cloudflare, Inc.",
        "mention_type": "prediction",
        "evidence": ["未来三个月可能继续上涨"],
    }


def _claim(
    direction: str,
    *,
    symbol: str = "NET",
    tweet_id: str | None = None,
    **overrides,
) -> dict:
    data = {
        "id": str(uuid.uuid4()),
        "analysis_result_id": str(uuid.uuid4()),
        "tweet_id": tweet_id or str(uuid.uuid4()),
        "blogger_handle": "researcher",
        "published_at": NOW,
        "tweet_type": "original",
        "is_investment_relevant": True,
        "is_sponsored": False,
        "instrument": {**_ticker(direction), "symbol": symbol},
        "direction": direction,
        "horizon": "medium",
        "forecast": {
            "prediction_type": "price_direction",
            "target_metric": "price_direction",
            "target_operator": "up" if direction == "bullish" else "down",
            "target_value": direction,
            "target_unit": "direction",
            "target_condition": "",
            "temporal_expression": "未来三个月",
            "forecast_source": "author",
            "author_adopted": True,
        },
        "claim_type": "prediction",
        "opinion_source": "author",
        "thesis": "未来三个月可能继续上涨",
        "evidence": ["未来三个月可能继续上涨"],
        "media_evidence": [],
        "confidence": 0.9,
        "downstream_eligible": True,
    }
    data.update(overrides)
    return data


def test_prediction_generation_keeps_only_directional_views():
    tweet_id = str(uuid.uuid4())
    claims = [
        _claim("neutral", tweet_id=tweet_id),
        _claim("bullish", symbol="AAPL", tweet_id=tweet_id),
    ]

    predictions = _generate_predictions(claims)

    assert [(item["ticker"], item["sentiment"]) for item in predictions] == [
        ("AAPL", "bullish")
    ]
    assert predictions[0]["creation_rule_version"] == PREDICTION_RULE_VERSION
    assert predictions[0]["eligibility_passed"] is True
    assert predictions[0]["instrument_snapshot"]["symbol"] == "AAPL"
    assert predictions[0]["claim_id"] == claims[1]["id"]


def test_prediction_eligibility_rejects_quote_sponsor_and_retweet():
    claim = _claim(
        "bullish",
        opinion_source="quoted",
    )

    decision = evaluate_claim_prediction_eligibility(
        claim,
        analysis={"is_investment_relevant": True, "is_sponsored": True},
        tweet={"tweet_type": "retweet"},
    )

    assert decision["eligible"] is False
    assert decision["reason_codes"] == [
        "sponsor_relation_unclear",
        "pure_retweet",
        "opinion_not_author",
    ]


def test_unrelated_platform_ad_does_not_exclude_author_prediction():
    decision = evaluate_claim_prediction_eligibility(
        _claim("bullish", sponsor_relation="unrelated"),
        analysis={"is_investment_relevant": True, "is_sponsored": True},
        tweet={"tweet_type": "original"},
    )

    assert decision["eligible"] is True
    assert decision["reason_codes"] == []


def test_prediction_eligibility_requires_time_basis_and_evidence():
    claim = _claim(
        "bullish",
        horizon="unknown",
        evidence=[],
        forecast={
            "prediction_type": "price_direction",
            "target_metric": "price_direction",
            "target_operator": "up",
            "target_value": "bullish",
            "target_unit": "direction",
            "target_condition": "",
            "temporal_expression": "",
            "forecast_source": "author",
            "author_adopted": True,
        },
    )

    decision = evaluate_claim_prediction_eligibility(
        claim,
        analysis={"is_investment_relevant": True},
        tweet={"tweet_type": "original"},
    )

    assert decision["eligible"] is False
    assert decision["reason_codes"] == [
        "grounding_evidence_missing",
        "time_basis_missing",
    ]


def test_persistence_layer_rejects_neutral_candidates():
    class NoWriteSession:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("neutral prediction must not query or write")

        def add(self, *_args, **_kwargs):
            raise AssertionError("neutral prediction must not query or write")

    assert save_predictions_batch(NoWriteSession(), [{"sentiment": "neutral"}]) == 0


def test_persistence_keeps_creation_audit_and_instrument_snapshot():
    class EmptyResult:
        def first(self):
            return None

        def scalars(self):
            return []

    class CaptureSession:
        def __init__(self):
            self.added = []

        def execute(self, *_args, **_kwargs):
            return EmptyResult()

        def add(self, value):
            self.added.append(value)

    db = CaptureSession()
    evidence = {"eligible": True, "rule_version": PREDICTION_RULE_VERSION}
    candidate = {
        "analysis_id": str(uuid.uuid4()),
        "claim_id": str(uuid.uuid4()),
        "tweet_id": str(uuid.uuid4()),
        "blogger_handle": "researcher",
        "ticker": "NET",
        "sentiment": "bullish",
        "investment_horizon": "medium",
        "published_at": NOW,
        "verifiable_at": NOW + timedelta(days=30),
        "instrument_snapshot": _ticker("bullish"),
        "eligibility_passed": True,
        "creation_rule_version": PREDICTION_RULE_VERSION,
        "creation_evidence": evidence,
    }

    assert save_predictions_batch(db, [candidate]) == 1
    stored = db.added[0]
    assert stored.creation_rule_version == PREDICTION_RULE_VERSION
    assert stored.creation_evidence == evidence
    assert stored.instrument_snapshot["symbol"] == "NET"


def test_circle_conflict_learns_context_for_future_corrections():
    assert _default_context_terms("COIN", {"original_name": "Circle/USDC"}) == [
        "circle",
        "usdc",
    ]


def test_neutral_legacy_prediction_is_classified_for_automatic_exclusion():
    prediction = Prediction(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        tweet_id=uuid.uuid4(),
        blogger_handle="researcher",
        ticker="NET",
        sentiment="neutral",
        investment_horizon="medium",
        published_at=NOW,
        verifiable_at=NOW + timedelta(days=30),
    )

    class FakeSession:
        def get(self, model, _key):
            if model is AnalysisResult:
                return SimpleNamespace(result={"tickers": [_ticker("neutral")]})
            if model is Tweet:
                return SimpleNamespace(content="Cloudflare 提供了 Agent 流量统计")
            raise AssertionError(model)

    result = preview_prediction_identity(FakeSession(), prediction)

    assert result["status"] == "excluded_non_directional"
    assert result["review_type"] == "non_directional"
    assert result["identity"]["symbol"] == "NET"
    assert result["identity"]["market"] == "US"


def test_manual_review_audit_preserves_recognized_identity():
    prediction = SimpleNamespace(
        id=uuid.uuid4(), ticker="NET", verifier_type="market_price_direction"
    )
    result = {
        "status": "manual_review",
        "review_type": "instrument_identity",
        "reason": "原文只是引用数据来源",
        "identity": {
            "symbol": "NET",
            "market": "US",
            "validation_sources": ["sec_edgar"],
        },
    }

    audit = _audit_from_result(prediction, result)

    assert audit.provider == "sec_edgar"
    assert audit.provider_symbol == "NET"
    assert audit.market == "US"
    assert audit.evidence["review_type"] == "instrument_identity"
    assert audit.rule_version == "instrument_identity_v1"


def test_successful_identity_check_creates_tracking_evidence():
    prediction = SimpleNamespace(
        id=uuid.uuid4(),
        ticker="NET",
        sentiment="bullish",
        investment_horizon="medium",
        published_at=NOW,
        verifiable_at=NOW + timedelta(days=30),
        verifier_type="market_price_direction",
    )

    result = _identity_tracking_result(prediction, _ticker("bullish"))
    audit = _audit_from_result(prediction, result)

    assert audit.status == "tracking"
    assert audit.provider_symbol == "NET"
    assert audit.market == "US"
    assert result["reason"] == "标的身份已核验，等待行情验证时间"


def test_spacex_alias_is_corrected_only_after_sec_confirmation(monkeypatch):
    monkeypatch.setattr(
        instrument_resolver,
        "_sec_match",
        lambda symbol: {"symbol": "SPCX"} if symbol == "SPCX" else None,
    )
    item = {
        "symbol": "SPCE",
        "original_name": "SpaceX",
        "asset_type": "equity",
        "market_hint": "US",
    }

    instrument_resolver._apply_legacy_hints(item)

    assert item["symbol"] == "SPCX"
    assert item["original_extracted_symbol"] == "SPCE"
    assert item["alias_resolution"] == "sec_verified_company_alias"


def test_spacex_is_no_longer_treated_as_an_unlisted_company():
    accepted, reason = _identity_gate(
        {
            "symbol": "SPCX",
            "original_name": "SpaceX",
            "resolved_name": "SPACE EXPLORATION TECHNOLOGIES CORP",
            "asset_type": "equity",
            "validation_sources": ["sec_edgar", "openfigi"],
        },
        "看好 SpaceX 上市后的长期发展",
    )

    assert accepted is True
    assert "公开数据源核验" in reason


def test_spacex_wrong_equity_symbol_still_requires_correction():
    accepted, reason = _identity_gate(
        {
            "symbol": "SPCE",
            "original_name": "SpaceX",
            "resolved_name": "Virgin Galactic Holdings, Inc",
            "asset_type": "equity",
            "validation_sources": ["sec_edgar"],
        },
        "看好 SpaceX",
    )

    assert accepted is False
    assert "SPCX" in reason


def test_hk_prices_fall_back_to_second_akshare_provider(monkeypatch):
    class Frame:
        empty = False

        def to_dict(self, orient):
            assert orient == "records"
            return [{"date": "2026-07-01", "open": 500.0, "close": 510.0}]

    class FakeAkshare:
        @staticmethod
        def stock_hk_hist(**_kwargs):
            raise ConnectionError("Eastmoney unavailable")

        @staticmethod
        def stock_hk_daily(**kwargs):
            assert kwargs == {"symbol": "00700", "adjust": "qfq"}
            return Frame()

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAkshare)

    rows = market_verification_service._load_hk_prices.__wrapped__(
        "00700.HK",
        datetime(2026, 7, 1).date(),
        datetime(2026, 7, 10).date(),
    )

    assert rows[0]["close"] == 510.0


def test_cn_prices_fall_back_to_second_akshare_provider(monkeypatch):
    class Frame:
        empty = False

        def to_dict(self, orient):
            assert orient == "records"
            return [{"date": "2026-07-01", "open": 1180.1, "close": 1193.01}]

    class FakeAkshare:
        @staticmethod
        def stock_zh_a_hist(**_kwargs):
            raise ConnectionError("Eastmoney unavailable")

        @staticmethod
        def stock_zh_a_daily(**kwargs):
            assert kwargs["symbol"] == "sh600519"
            return Frame()

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAkshare)

    rows = market_verification_service._load_cn_prices.__wrapped__(
        "600519.SH",
        datetime(2026, 7, 1).date(),
        datetime(2026, 7, 10).date(),
    )

    assert rows[0]["close"] == 1193.01
