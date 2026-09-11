from app.agents import signal_agent
from app.schemas.signal import TweetAnalysis


def test_v4_signal_accepts_market_index_as_extraction_candidate():
    result = TweetAnalysis(
        is_investment_relevant=True,
        claims=[
            {
                "instrument": {
                    "symbol": "SOX",
                    "original_name": "SOX",
                    "asset_type": "index",
                    "market_hint": "US",
                },
                "claim_type": "opinion",
            }
        ],
    )

    assert result.claims[0].instrument.asset_type == "index"


def test_v4_signal_distinguishes_reference_from_author_recommendation():
    result = TweetAnalysis(
        is_investment_relevant=True,
        claims=[
            {
                "instrument": {
                    "symbol": "$nvda",
                    "original_name": "NVDA",
                    "asset_type": "equity",
                    "market_hint": "US",
                },
                "direction": "none",
                "horizon": "unknown",
                "claim_type": "news",
                "opinion_source": "third_party",
                "thesis": "报道转述了公司最新进展",
                "evidence": ["报道提到 NVDA"],
                "confidence": 0.8,
            }
        ],
        tweet_summary="报道转述了公司最新进展",
    )

    data = result.model_dump()
    assert data["analysis_schema_version"] == "v4"
    assert data["is_investment_related"] is True
    assert data["claims"][0]["instrument"]["symbol"] == "NVDA"
    assert data["claims"][0]["claim_type"] == "news"
    assert data["claims"][0]["direction"] == "none"
    assert data["markets"] == ["US"]
    assert "overall_sentiment" not in data


def test_v3_signal_keeps_different_instruments_and_directions_independent():
    result = TweetAnalysis(
        is_investment_relevant=True,
        claims=[
            {
                "instrument": {
                    "symbol": "AAPL",
                    "asset_type": "equity",
                    "market_hint": "US",
                },
                "direction": "bullish",
                "horizon": "short",
                "claim_type": "prediction",
                "opinion_source": "author",
                "thesis": "短期可能上涨",
                "evidence": ["AAPL 短期可能上涨"],
                "confidence": 1.4,
            },
            {
                "instrument": {
                    "symbol": "TSLA",
                    "asset_type": "equity",
                    "market_hint": "US",
                },
                "direction": "bearish",
                "horizon": "long",
                "claim_type": "opinion",
                "opinion_source": "author",
                "thesis": "长期估值承压",
                "evidence": ["TSLA 长期估值承压"],
                "confidence": 0.75,
            },
        ],
    )

    assert [
        (
            claim.instrument.symbol,
            claim.direction,
            claim.horizon,
        )
        for claim in result.claims
    ] == [
        ("AAPL", "bullish", "short"),
        ("TSLA", "bearish", "long"),
    ]
    assert result.claims[0].confidence == 1.0


def test_v3_signal_keeps_price_targets_inside_the_related_commodity_claim():
    result = TweetAnalysis(
        is_investment_relevant=True,
        markets=["US", "COMMODITY"],
        claims=[
            {
                "instrument": {
                    "symbol": "xau",
                    "asset_type": "commodity",
                    "market_hint": "US",
                },
                "direction": "bullish",
                "horizon": "medium",
                "claim_type": "prediction",
                "opinion_source": "author",
                "thesis": "黄金突破后可能继续上行",
                "evidence": ["黄金突破后可能继续上行"],
                "price_targets": [
                    {
                        "symbol": "xau",
                        "target_type": "target",
                        "value": "2500-2550",
                        "currency": "USD",
                    }
                ],
            }
        ],
    )

    claim = result.claims[0]
    assert claim.instrument.symbol == "XAU"
    assert claim.instrument.market_hint == "COMMODITY"
    assert claim.price_targets[0].symbol == "XAU"
    assert claim.price_targets[0].value == "2500-2550"
    assert result.markets == ["COMMODITY"]


def test_single_text_analysis_cannot_invent_claim_media_evidence(monkeypatch):
    parsed = TweetAnalysis(
        is_investment_relevant=True,
        claims=[
            {
                "instrument": {
                    "symbol": "NVDA",
                    "asset_type": "equity",
                    "market_hint": "US",
                },
                "direction": "bullish",
                "horizon": "medium",
                "claim_type": "opinion",
                "opinion_source": "author",
                "thesis": "新品周期改善",
                "evidence": ["NVDA 发布新品"],
                "media_evidence": ["不存在的图片证据"],
            }
        ],
        media_summary="不存在的图片摘要",
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
    assert result["claims"][0]["media_evidence"] == []
    assert result["text_image_consistency"] == "no_media"
    assert result["media_confidence"] == 0.0
