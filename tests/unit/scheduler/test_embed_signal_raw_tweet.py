import uuid
from datetime import datetime, timezone

from app.models.tweet import Tweet
from app.scheduler import tasks


class _ScalarResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, tweet):
        self.tweet = tweet
        self.added = []
        self.committed = False
        self.closed = False

    def get(self, model, row_id):
        if model is Tweet and row_id == self.tweet.id:
            return self.tweet
        return None

    def execute(self, _stmt):
        return _ScalarResult(None)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class _FakeVectorStore:
    def __init__(self):
        self.calls = []

    def add(self, collection, ids, texts, embeddings, metadatas):
        self.calls.append(
            {
                "collection": collection,
                "ids": ids,
                "texts": texts,
                "embeddings": embeddings,
                "metadatas": metadatas,
            }
        )


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_embed_signal_task_indexes_raw_tweet_without_analysis(monkeypatch):
    tweet = Tweet(
        id=uuid.uuid4(),
        tweet_id="tw-1",
        author_handle="alice",
        author_name="Alice",
        content="NVDA earnings look strong",
        published_at=datetime.now(timezone.utc),
        status="pending",
    )
    db = _FakeSession(tweet)
    vs = _FakeVectorStore()

    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr("app.rag.vector_store.get_vector_store", lambda: vs)
    monkeypatch.setattr("app.rag.embeddings.get_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(
        tasks,
        "_best_effort_upsert_es_chunks",
        lambda rows, **_kwargs: {"indexed": len(rows)},
    )

    result = tasks.embed_signal_task.run("tweet", str(tweet.id))

    assert result["indexed"] == 1
    assert vs.calls[0]["collection"] == "public_signals"
    metadata = vs.calls[0]["metadatas"][0]
    assert metadata["source_type"] == "tweet"
    assert metadata["source_id"] == str(tweet.id)
    assert metadata["index_stage"] == "raw"
    assert metadata["sentiment"] == "unknown"
    assert metadata["horizon"] == "unknown"
    assert metadata["ticker"] == ""
    assert db.committed is True
