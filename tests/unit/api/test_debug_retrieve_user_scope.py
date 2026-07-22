import asyncio
import uuid

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


def test_debug_retrieve_passes_current_user_to_bm25(monkeypatch):
    user_id = uuid.UUID("10000000-0000-0000-0000-000000000001")
    captured = {}

    class Intent:
        ticker = "BTC"
        keywords = ["risk"]
        blogger_filter = []
        time_range_start = None
        time_range_end = None

        def model_dump(self):
            return {"ticker": self.ticker, "keywords": self.keywords}

        def model_copy(self, update):
            clone = Intent()
            for key, value in update.items():
                setattr(clone, key, value)
            return clone

    monkeypatch.setattr(debug.settings, "debug_mode", True)
    monkeypatch.setattr(debug.settings, "feature_rag_enabled", True)
    monkeypatch.setattr("app.agents.self_query_agent.parse_intent", lambda query: Intent())
    monkeypatch.setattr("app.rag.retrievers.document_retriever.retrieve_documents", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.retrievers.tweet_retriever.retrieve_tweets", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.retrievers.analysis_retriever.retrieve_analyses", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.retrievers.structured_retriever.retrieve_structured", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.fusion.reciprocal_rank_fusion", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.reranker.rerank", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.reranker.apply_time_decay", lambda items: items)

    def fake_retrieve_bm25(intent, user_id=None):
        captured["user_id"] = user_id
        return [{"unique_id": "es:1", "content": "hit", "source_type": "document", "metadata": {}, "score": 1.0}]

    monkeypatch.setattr("app.rag.retrievers.bm25_retriever.retrieve_bm25", fake_retrieve_bm25)

    result = asyncio.run(
        debug.debug_retrieve(
            debug.DebugRetrieveRequest(query="BTC risk"),
            current_user=_user(user_id),
        )
    )

    assert captured["user_id"] == user_id
    assert result["paths"]["bm25"][0]["unique_id"] == "es:1"


def test_debug_retrieve_includes_es_debug_and_rerank_debug(monkeypatch):
    user_id = uuid.UUID("10000000-0000-0000-0000-000000000001")

    class Intent:
        ticker = "BTC"
        keywords = ["risk"]
        blogger_filter = []
        time_range_start = None
        time_range_end = None

        def model_dump(self):
            return {"ticker": self.ticker, "keywords": self.keywords}

        def model_copy(self, update):
            clone = Intent()
            for key, value in update.items():
                setattr(clone, key, value)
            return clone

    class Store:
        def debug_search(self, **kwargs):
            return {
                "index": "finance_rag_chunks",
                "query": {"function_score": {"query": {"bool": {}}}},
                "raw_hits": [{"_id": "chunk-1", "highlight": {"content": ["<em>BTC</em>"]}}],
                "results": [
                    {
                        "unique_id": "es:chunk-1",
                        "content": "BTC risk",
                        "source_type": "tweet",
                        "metadata": {"highlight": {"content": ["<em>BTC</em>"]}},
                        "score": 2.0,
                    }
                ],
            }

    monkeypatch.setattr(debug.settings, "debug_mode", True)
    monkeypatch.setattr(debug.settings, "feature_rag_enabled", True)
    monkeypatch.setattr("app.agents.self_query_agent.parse_intent", lambda query: Intent())
    monkeypatch.setattr("app.rag.retrievers.document_retriever.retrieve_documents", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.retrievers.tweet_retriever.retrieve_tweets", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.retrievers.analysis_retriever.retrieve_analyses", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.rag.retrievers.structured_retriever.retrieve_structured", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "app.rag.retrievers.bm25_retriever.retrieve_bm25",
        lambda *args, **kwargs: Store().debug_search()["results"],
    )
    monkeypatch.setattr("app.rag.keyword_store.get_keyword_store", lambda: Store())
    monkeypatch.setattr("app.rag.fusion.reciprocal_rank_fusion", lambda *args, **kwargs: Store().debug_search()["results"])
    monkeypatch.setattr("app.rag.reranker.rerank", lambda *args, **kwargs: [(0, 0.9)])
    monkeypatch.setattr("app.rag.reranker.apply_time_decay", lambda items: items)

    result = asyncio.run(
        debug.debug_retrieve(
            debug.DebugRetrieveRequest(query="BTC risk"),
            current_user=_user(user_id),
        )
    )

    assert result["es_debug"]["query"]["function_score"]["query"]["bool"] == {}
    assert result["es_debug"]["raw_hits"][0]["highlight"] == {"content": ["<em>BTC</em>"]}
    assert result["rerank_debug"] == {"input_count": 1, "selected_indices": [{"index": 0, "score": 0.9}]}
