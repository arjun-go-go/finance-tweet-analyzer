from uuid import UUID

from app.agents import report_agent
from app.agents.self_query_agent import QueryIntent


def test_retrieve_bm25_node_passes_user_id_to_keyword_retriever(monkeypatch):
    captured = {}
    intent = QueryIntent(ticker="BTC", keywords=["risk"])

    def fake_retrieve_bm25(intent_arg, user_id=None):
        captured["intent"] = intent_arg
        captured["user_id"] = user_id
        return [{"unique_id": "es:1"}]

    monkeypatch.setattr(report_agent, "retrieve_bm25", fake_retrieve_bm25)

    result = report_agent.retrieve_bm25_node(
        {
            "path": "bm25",
            "user_id": "10000000-0000-0000-0000-000000000001",
            "intent": intent.model_dump(),
        }
    )

    assert result == {"retrieve_results": [[{"unique_id": "es:1"}]]}
    assert captured["user_id"] == UUID("10000000-0000-0000-0000-000000000001")
