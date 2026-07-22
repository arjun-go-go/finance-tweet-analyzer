from datetime import datetime, timezone
from uuid import UUID

from app.scheduler import tasks
from app.models.es_index_job import EsIndexJob


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


def test_best_effort_upsert_es_chunks_records_success_job(monkeypatch):
    recorded = []

    class Store:
        def bulk_upsert_documents(self, docs):
            return 1, []

    class FakeSession:
        def merge(self, row):
            recorded.append(row)

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())

    result = tasks._best_effort_upsert_es_chunks([Chunk()], db=FakeSession())

    assert result == {"attempted": 1, "indexed": 1, "errors": 0}
    assert len(recorded) == 1
    assert recorded[0].doc_chunk_id == Chunk.id
    assert recorded[0].status == "success"
    assert recorded[0].attempts == 1
    assert recorded[0].error_message is None


def test_best_effort_upsert_es_chunks_records_failure_job(monkeypatch):
    recorded = []

    class Store:
        def bulk_upsert_documents(self, docs):
            raise RuntimeError("es down")

    class FakeSession:
        def merge(self, row):
            recorded.append(row)

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())

    result = tasks._best_effort_upsert_es_chunks([Chunk()], db=FakeSession())

    assert result == {"attempted": 1, "indexed": 0, "errors": 1}
    assert len(recorded) == 1
    assert recorded[0].doc_chunk_id == Chunk.id
    assert recorded[0].status == "failed"
    assert recorded[0].attempts == 1
    assert "es down" in recorded[0].error_message


def test_retry_failed_es_index_jobs_task_reindexes_failed_jobs(monkeypatch):
    job = EsIndexJob(
        doc_chunk_id=Chunk.id,
        status="failed",
        attempts=2,
        error_message="old error",
    )
    calls = []

    class JobResult:
        def scalars(self):
            return self

        def all(self):
            return [job]

    class FakeSession:
        def execute(self, stmt):
            return JobResult()

        def get(self, model, row_id):
            if model is tasks.DocChunk and row_id == Chunk.id:
                return Chunk()
            if model is tasks.Document and row_id == Chunk.document_id:
                return type("Doc", (), {"user_id": UUID("10000000-0000-0000-0000-000000000001")})()
            return None

        def close(self):
            pass

    def fake_upsert(chunks, user_id=None, db=None):
        calls.append((list(chunks), user_id, db))
        return {"attempted": 1, "indexed": 1, "errors": 0}

    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(tasks, "_best_effort_upsert_es_chunks", fake_upsert)

    result = tasks.retry_failed_es_index_jobs_task.run(batch_size=10)

    assert result == {"scanned": 1, "attempted": 1, "indexed": 1, "errors": 0, "missing_chunks": 0}
    assert calls[0][1] == UUID("10000000-0000-0000-0000-000000000001")


def test_delete_existing_source_chunks_deletes_pg_chunks_and_es_documents(monkeypatch):
    deleted_rows = []
    es_calls = []

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [Chunk()]

    class FakeSession:
        def execute(self, stmt):
            return Result()

        def delete(self, row):
            deleted_rows.append(row)

    class Store:
        def delete_by_source(self, source_type, source_id):
            es_calls.append((source_type, source_id))
            return {"deleted": 1}

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())

    result = tasks._delete_existing_source_chunks(FakeSession(), "tweet", "tweet-1")

    assert result == {"pg_deleted": 1, "es_deleted": 1}
    assert deleted_rows[0].id == Chunk.id
    assert es_calls == [("tweet", "tweet-1")]


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
