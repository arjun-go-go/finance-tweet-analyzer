import uuid
from types import SimpleNamespace

from app.services.analysis_service import (
    _enqueue_analysis_indexing,
    _mark_successful_tweets,
)


def _tweet(tweet_id: uuid.UUID):
    return SimpleNamespace(id=tweet_id, status="pending")


def test_mark_successful_tweets_leaves_missing_analysis_pending():
    successful_id = uuid.uuid4()
    failed_id = uuid.uuid4()
    successful = _tweet(successful_id)
    failed = _tweet(failed_id)

    completed = _mark_successful_tweets(
        [successful, failed],
        [{"tweet_id": str(successful_id)}],
    )

    assert completed == [successful]
    assert successful.status == "analyzed"
    assert failed.status == "pending"


def test_mark_successful_tweets_ignores_unknown_analysis_ids():
    tweet = _tweet(uuid.uuid4())

    completed = _mark_successful_tweets(
        [tweet],
        [{"tweet_id": str(uuid.uuid4())}],
    )

    assert completed == []
    assert tweet.status == "pending"


def test_enqueue_analysis_indexing_uses_transactional_outbox(monkeypatch):
    analysis_id = uuid.uuid4()
    enqueued = []

    def fake_enqueue(db, event_type, payload):
        enqueued.append((db, event_type, payload))

    monkeypatch.setattr("app.services.outbox_service.enqueue_outbox_event", fake_enqueue)
    fake_db = object()

    _enqueue_analysis_indexing(fake_db, [analysis_id])

    assert enqueued == [
        (fake_db, "analysis.index_requested", {"analysis_result_id": str(analysis_id)}),
        (fake_db, "intelligence.project_requested", {"analysis_result_id": str(analysis_id)}),
    ]
