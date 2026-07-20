from datetime import datetime, timezone
from uuid import UUID

from app.scheduler import tasks


class Chunk:
    id = UUID("20000000-0000-0000-0000-000000000001")
    document_id = UUID("30000000-0000-0000-0000-000000000001")
    chunk_index = 0
    content = "BTC chunk"
    metadata_ = {"source_type": "document", "tickers": "BTC"}
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_best_effort_upsert_es_chunks_indexes_documents(monkeypatch):
    captured = {}

    class Store:
        def bulk_upsert_documents(self, docs):
            captured["docs"] = list(docs)
            return 1, []

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())

    result = tasks._best_effort_upsert_es_chunks(
        [Chunk()],
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
    )

    assert result == {"attempted": 1, "indexed": 1, "errors": 0}
    assert captured["docs"][0]["chunk_id"] == "20000000-0000-0000-0000-000000000001"
    assert captured["docs"][0]["user_id"] == "10000000-0000-0000-0000-000000000001"
    assert captured["docs"][0]["visibility"] == "private"


def test_best_effort_upsert_es_chunks_swallows_failures(monkeypatch):
    class Store:
        def bulk_upsert_documents(self, docs):
            raise RuntimeError("es down")

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())

    result = tasks._best_effort_upsert_es_chunks([Chunk()])

    assert result == {"attempted": 1, "indexed": 0, "errors": 1}


def test_reindex_elasticsearch_chunks_task_dry_run_does_not_write(monkeypatch):
    class FakeResult:
        def all(self):
            return [(Chunk(), UUID("10000000-0000-0000-0000-000000000001"))]

    class FakeSession:
        def execute(self, stmt):
            return FakeResult()

        def close(self):
            pass

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        tasks,
        "_best_effort_upsert_es_chunks",
        lambda chunks, user_id=None: (_ for _ in ()).throw(AssertionError("must not write")),
    )

    result = tasks.reindex_elasticsearch_chunks_task.run(batch_size=10, dry_run=True)

    assert result == {"scanned": 1, "attempted": 0, "indexed": 0, "errors": 0, "dry_run": True}
