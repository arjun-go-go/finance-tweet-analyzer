import asyncio
import uuid

from app.agents.self_query_agent import QueryIntent
from app.api import debug
from app.models.user import User


def _user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="debug@example.com",
        username="debug-user",
        password_hash="unused",
        status="active",
    )


def _empty_result():
    return {
        "paths": {"documents": [], "tweets": [], "analyses": [], "structured": [], "bm25": []},
        "errors": {},
        "es_debug": None,
        "fused": [],
        "reranked": [],
        "rerank_debug": {"input_count": 0, "selected_indices": []},
        "latency_ms": {},
    }


def test_debug_retrieve_passes_current_user_to_hybrid_pipeline(monkeypatch):
    user_id = uuid.UUID("10000000-0000-0000-0000-000000000001")
    captured = {}

    monkeypatch.setattr(debug.settings, "debug_mode", True)
    monkeypatch.setattr(debug.settings, "feature_rag_enabled", True)
    monkeypatch.setattr(
        "app.agents.self_query_agent.parse_intent",
        lambda query: QueryIntent(ticker="BTC", keywords=["risk"]),
    )

    def fake_hybrid_retrieve(intent, **kwargs):
        captured["intent"] = intent
        captured.update(kwargs)
        result = _empty_result()
        result["paths"]["bm25"] = [
            {
                "unique_id": "es:1",
                "content": "hit",
                "source_type": "document",
                "metadata": {},
                "score": 1.0,
            }
        ]
        return result

    monkeypatch.setattr("app.rag.hybrid_retrieval.hybrid_retrieve", fake_hybrid_retrieve)

    result = asyncio.run(
        debug.debug_retrieve(
            debug.DebugRetrieveRequest(query="BTC risk"),
            current_user=_user(user_id),
        )
    )

    assert captured["user_id"] == user_id
    assert captured["include_es_debug"] is True
    assert result["paths"]["bm25"][0]["unique_id"] == "es:1"


def test_debug_retrieve_returns_shared_pipeline_debug_payload(monkeypatch):
    user_id = uuid.UUID("10000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(debug.settings, "debug_mode", True)
    monkeypatch.setattr(debug.settings, "feature_rag_enabled", True)
    monkeypatch.setattr(
        "app.agents.self_query_agent.parse_intent",
        lambda query: QueryIntent(ticker="BTC", keywords=["risk"]),
    )

    expected = _empty_result()
    expected["es_debug"] = {
        "index": "finance_rag_chunks",
        "query": {"function_score": {"query": {"bool": {}}}},
        "raw_hits": [{"_id": "chunk-1", "highlight": {"content": ["<em>BTC</em>"]}}],
        "results": [],
    }
    expected["rerank_debug"] = {
        "input_count": 1,
        "selected_indices": [{"index": 0, "score": 0.9}],
    }
    monkeypatch.setattr("app.rag.hybrid_retrieval.hybrid_retrieve", lambda *args, **kwargs: expected)

    result = asyncio.run(
        debug.debug_retrieve(
            debug.DebugRetrieveRequest(query="BTC risk"),
            current_user=_user(user_id),
        )
    )

    assert result["es_debug"]["query"]["function_score"]["query"]["bool"] == {}
    assert result["es_debug"]["raw_hits"][0]["highlight"] == {"content": ["<em>BTC</em>"]}
    assert result["rerank_debug"] == expected["rerank_debug"]
