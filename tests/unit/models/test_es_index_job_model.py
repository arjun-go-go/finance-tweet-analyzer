import uuid

from app.models.es_index_job import EsIndexJob


def test_es_index_job_has_retry_ledger_fields():
    doc_chunk_id = uuid.uuid4()
    job = EsIndexJob(
        doc_chunk_id=doc_chunk_id,
        target="elasticsearch",
        status="pending",
        attempts=0,
    )

    assert job.doc_chunk_id == doc_chunk_id
    assert job.target == "elasticsearch"
    assert job.status == "pending"
    assert job.attempts == 0
    assert job.error_message is None
