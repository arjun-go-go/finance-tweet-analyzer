from unittest.mock import AsyncMock, Mock

from app.agents import analysis_agent
from app.agents.supervisor import route_after_classification


def test_mixed_batch_generates_result_for_every_tweet(monkeypatch):
    tweets = [
        {"id": "finance", "author_handle": "alice", "content": "I am bullish NVDA"},
        {"id": "personal", "author_handle": "alice", "content": "Good morning"},
    ]
    state = {
        "tweets": tweets,
        "classification": {"classifications": [
            {"tweet_id": "finance", "category": "stock", "needs_risk_analysis": True, "confidence": 0.9},
            {"tweet_id": "personal", "category": "non_financial", "needs_risk_analysis": True, "confidence": 0.9},
        ]},
    }
    analysis_send, risk_send = route_after_classification(state)
    assert analysis_send.node == "analysis_agent"
    assert risk_send.arg["tweets"] == tweets[:1]

    model = AsyncMock(return_value={"tweet_id": "finance"})
    monkeypatch.setattr(analysis_agent, "fetch_blogger_contexts", lambda _handles: {})
    monkeypatch.setattr(analysis_agent, "get_signal_llm", Mock())
    monkeypatch.setattr(analysis_agent, "analyze_tweet_with_llm", model)
    result = analysis_agent.analysis_agent_node(analysis_send.arg)["partial_analyses"]
    assert {r["tweet_id"]: r.get("skip_reason") for r in result} == {
        "finance": None, "personal": "non_financial",
    }
    assert model.await_count == 1
