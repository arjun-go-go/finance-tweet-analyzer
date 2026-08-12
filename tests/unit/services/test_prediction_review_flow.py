import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.agents.prediction_agent import _generate_predictions
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
    }


def test_prediction_generation_keeps_only_directional_views():
    tweet_id = str(uuid.uuid4())
    tweets = [{"id": tweet_id, "published_at": NOW}]
    analyses = [
        {
            "tweet_id": tweet_id,
            "author_handle": "researcher",
            "is_investment_related": True,
            "confidence": 0.9,
            "tickers": [_ticker("neutral"), {**_ticker("bullish"), "symbol": "AAPL"}],
        }
    ]

    predictions = _generate_predictions(analyses, tweets)

    assert [(item["ticker"], item["sentiment"]) for item in predictions] == [
        ("AAPL", "bullish")
    ]


def test_persistence_layer_rejects_neutral_candidates():
    class NoWriteSession:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("neutral prediction must not query or write")

        def add(self, *_args, **_kwargs):
            raise AssertionError("neutral prediction must not query or write")

    assert save_predictions_batch(NoWriteSession(), [{"sentiment": "neutral"}]) == 0


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
    prediction = SimpleNamespace(id=uuid.uuid4(), ticker="NET")
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
