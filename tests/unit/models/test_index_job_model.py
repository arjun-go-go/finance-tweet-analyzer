import uuid

from app.models.index_job import IndexJob


def test_index_job_is_a_per_target_projection_ledger():
    content_chunk_id = uuid.uuid4()
    job = IndexJob(
        content_chunk_id=content_chunk_id,
        target="elasticsearch",
        status="pending",
        attempts=0,
    )

    assert job.content_chunk_id == content_chunk_id
    assert job.target == "elasticsearch"
    assert job.status == "pending"
    assert job.attempts == 0
    assert job.error_message is None
