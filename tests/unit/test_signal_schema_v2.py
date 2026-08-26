from app.schemas.signal import TweetAnalysis
from app.agents import signal_agent


def test_v2_signal_distinguishes_reference_from_recommendation():
    result = TweetAnalysis(
        is_investment_relevant=True,
        statement_type="news_relay",
        opinion_source="third_party",
        tickers=[
            {
                "symbol": "$nvda",
                "original_name": "NVDA",
                "asset_type": "equity",
                "market_hint": "US",
                "sentiment": "neutral",
                "horizon": "unknown",
                "mention_type": "news",
                "evidence": ["报道提到 NVDA"],
            }
        ],
        thesis="报道转述了公司最新进展",
        text_evidence=["报道提到 NVDA"],
        is_prediction=False,
    )

    data = result.model_dump()
    assert data["analysis_schema_version"] == "v2"
    assert data["is_investment_related"] is True
    assert data["tickers"][0]["symbol"] == "NVDA"
    assert data["tickers"][0]["mention_type"] == "news"
    assert data["markets"] == ["US"]
    assert data["is_prediction"] is False


def test_v2_signal_keeps_legacy_payload_compatible():
    result = TweetAnalysis(
        is_investment_related=True,
        overall_sentiment="bullish",
        tickers=[{"symbol": "BTC", "sentiment": "bullish", "horizon": "short"}],
        key_points=["突破关键阻力位"],
        risk_factors=["成交量不足"],
        confidence=1.4,
    )

    assert result.is_investment_relevant is True
    assert result.thesis == "突破关键阻力位"
    assert result.key_points == ["突破关键阻力位"]
    assert result.confidence == 1.0
    assert result.statement_type == "opinion"


def test_v2_signal_derives_legacy_key_points_from_thesis():
    result = TweetAnalysis(
        is_investment_relevant=True,
        statement_type="prediction",
        opinion_source="author",
        thesis="黄金突破后可能继续上行",
        is_prediction=True,
        price_targets=[
            {
                "symbol": "xau",
                "target_type": "target",
                "value": "2500-2550",
                "currency": "USD",
            }
        ],
    )

    assert result.key_points == ["黄金突破后可能继续上行"]
    assert result.price_targets[0].symbol == "XAU"
    assert result.price_targets[0].value == "2500-2550"


def test_v2_signal_normalizes_commodity_market():
    result = TweetAnalysis(
        is_investment_relevant=True,
        statement_type="prediction",
        markets=["US", "COMMODITY"],
        tickers=[
            {
                "symbol": "WTI",
                "asset_type": "commodity",
                "market_hint": "US",
                "sentiment": "bullish",
                "horizon": "medium",
                "mention_type": "prediction",
            }
        ],
    )

    assert result.tickers[0].market_hint == "COMMODITY"
    assert result.markets == ["COMMODITY"]


def test_single_text_analysis_cannot_invent_media_evidence(monkeypatch):
    parsed = TweetAnalysis(
        is_investment_relevant=True,
        statement_type="fact",
        media_summary="不存在的图片摘要",
        media_evidence=["不存在的图片证据"],
        text_image_consistency="consistent",
        media_confidence=0.9,
    )

    class FakeStructuredLLM:
        def invoke(self, _messages):
            return parsed

    class FakeLLM:
        def with_structured_output(self, schema):
            assert schema is TweetAnalysis
            return FakeStructuredLLM()

    monkeypatch.setattr(signal_agent, "get_signal_llm", lambda: FakeLLM())
    result = signal_agent.analyze_tweet("NVDA 发布新品", "analyst")

    assert result["media_summary"] == ""
    assert result["media_evidence"] == []
    assert result["text_image_consistency"] == "no_media"
    assert result["media_confidence"] == 0.0
