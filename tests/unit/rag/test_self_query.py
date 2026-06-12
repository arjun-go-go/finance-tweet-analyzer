"""Unit tests for Self-Query intent parser."""

from app.agents.self_query_agent import _fallback_parse, QueryIntent


def test_fallback_extracts_ticker():
    result = _fallback_parse("生成 TSLA 本周跟踪报告")
    assert result.ticker == "TSLA"


def test_fallback_extracts_btc():
    result = _fallback_parse("BTC 最近趋势如何")
    assert result.ticker == "BTC"


def test_fallback_default_time_range():
    result = _fallback_parse("AAPL 分析")
    assert result.time_range_start is not None
    assert result.time_range_end is not None
    delta = result.time_range_end - result.time_range_start
    assert 6 <= delta.days <= 8


def test_fallback_unknown_ticker():
    result = _fallback_parse("最近市场怎么样")
    assert result.ticker == "UNKNOWN"


def test_fallback_focus_aspects():
    result = _fallback_parse("TSLA 风险分析")
    assert "sentiment" in result.focus_aspects
    assert "risk" in result.focus_aspects


def test_query_intent_model():
    intent = QueryIntent(
        ticker="TSLA",
        focus_aspects=["sentiment"],
        keywords=["趋势"],
    )
    assert intent.ticker == "TSLA"
    assert intent.time_range_start is None
    assert intent.sentiment_filter == []
