from datetime import datetime, timezone
from uuid import UUID

from app.agents.self_query_agent import QueryIntent
from app.rag.retrievers import bm25_retriever


def _intent():
    return QueryIntent(
        ticker="BTC",
        keywords=["ETF", "risk"],
        time_range_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_range_end=datetime(2026, 1, 31, tzinfo=timezone.utc),
        blogger_filter=["satoshi"],
    )


def test_retrieve_bm25_uses_postgres_backend_by_default(monkeypatch):
    monkeypatch.setattr(bm25_retriever.settings, "rag_keyword_backend", "postgres")
    captured = {}

    def fake_pg(intent, user_id=None):
        captured["intent"] = intent
        captured["user_id"] = user_id
        return [{"unique_id": "pg:1"}]

    monkeypatch.setattr(bm25_retriever, "retrieve_pg_bm25", fake_pg)

    result = bm25_retriever.retrieve_bm25(
        _intent(),
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
    )

    assert result == [{"unique_id": "pg:1"}]
    assert captured["user_id"] == UUID("10000000-0000-0000-0000-000000000001")


def test_retrieve_bm25_uses_elasticsearch_backend_when_configured(monkeypatch):
    monkeypatch.setattr(bm25_retriever.settings, "rag_keyword_backend", "elasticsearch")
    captured = {}

    class Store:
        def search(self, **kwargs):
            captured.update(kwargs)
            return [{"unique_id": "es:1"}]

    monkeypatch.setattr(bm25_retriever, "get_keyword_store", lambda: Store())

    result = bm25_retriever.retrieve_bm25(
        _intent(),
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
    )

    assert result == [{"unique_id": "es:1"}]
    assert captured == {
        "query_text": "BTC ETF risk",
        "user_id": UUID("10000000-0000-0000-0000-000000000001"),
        "blogger_filter": ["satoshi"],
        "time_range_start": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "time_range_end": datetime(2026, 1, 31, tzinfo=timezone.utc),
        "top_k": bm25_retriever.settings.rag_bm25_top_k,
    }


def test_retrieve_bm25_falls_back_to_postgres_when_elasticsearch_fails(monkeypatch):
    monkeypatch.setattr(bm25_retriever.settings, "rag_keyword_backend", "elasticsearch")

    class Store:
        def search(self, **kwargs):
            raise RuntimeError("es unavailable")

    monkeypatch.setattr(bm25_retriever, "get_keyword_store", lambda: Store())
    monkeypatch.setattr(
        bm25_retriever,
        "retrieve_pg_bm25",
        lambda intent, user_id=None: [{"unique_id": "pg:fallback", "user_id": str(user_id)}],
    )

    result = bm25_retriever.retrieve_bm25(
        _intent(),
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
    )

    assert result == [
        {
            "unique_id": "pg:fallback",
            "user_id": "10000000-0000-0000-0000-000000000001",
        }
    ]
