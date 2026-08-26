from datetime import datetime, timezone
from uuid import UUID

from app.models.index_job import IndexJob
from app.scheduler import tasks


class Chunk:
    id = UUID("20000000-0000-0000-0000-000000000001")
    source_type = "tweet"
    source_id = "30000000-0000-0000-0000-000000000001"
    index_stage = "raw"
    chunk_index = 0
    content = "BTC tweet"
    metadata_ = {"ticker": "BTC", "blogger_handle": "analyst"}
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_best_effort_upsert_indexes_canonical_content_chunk(monkeypatch):
    captured = {}

    class Store:
        def bulk_upsert_documents(self, docs):
            captured["docs"] = list(docs)
            return 1, []

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())
    result = tasks._best_effort_upsert_es_chunks([Chunk()])

    assert result == {"attempted": 1, "indexed": 1, "errors": 0}
    document = captured["docs"][0]
    assert document["source_type"] == "tweet"
    assert document["source_id"] == Chunk.source_id
    assert document["index_stage"] == "raw"
    assert "user_id" not in document
    assert "document_id" not in document


def test_best_effort_upsert_records_projection_job(monkeypatch):
    recorded = []

    class Store:
        def bulk_upsert_documents(self, docs):
            return 1, []

    class Session:
        def get(self, model, key):
            assert model is IndexJob
            return None

        def merge(self, row):
            recorded.append(row)

        def flush(self):
            pass

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())
    tasks._best_effort_upsert_es_chunks([Chunk()], db=Session())

    assert recorded[0].content_chunk_id == Chunk.id
    assert recorded[0].target == "elasticsearch"
    assert recorded[0].status == "success"


def test_delete_existing_source_chunks_removes_pg_and_es(monkeypatch):
    deleted = []

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [Chunk()]

    class Session:
        def execute(self, statement):
            return Result()

        def delete(self, row):
            deleted.append(row)

    class Store:
        def delete_by_source(self, source_type, source_id):
            assert (source_type, source_id) == ("tweet", Chunk.source_id)
            return {"deleted": 1}

    monkeypatch.setattr(tasks, "get_keyword_store", lambda: Store())
    result = tasks._delete_existing_source_chunks(
        Session(), "tweet", Chunk.source_id
    )

    assert result == {"pg_deleted": 1, "es_deleted": 1}
    assert deleted[0].id == Chunk.id
