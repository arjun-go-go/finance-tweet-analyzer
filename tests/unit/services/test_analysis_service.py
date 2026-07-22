import uuid
from types import SimpleNamespace

from app.services.analysis_service import (
    _dispatch_analysis_indexing,
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


def test_dispatch_analysis_indexing_uses_analysis_source_type(monkeypatch):
    analysis_id = uuid.uuid4()
    dispatched = []

    class FakeEmbedTask:
        @staticmethod
        def delay(source_type, source_id):
            dispatched.append((source_type, source_id))

    monkeypatch.setattr("app.scheduler.tasks.embed_signal_task", FakeEmbedTask)

    _dispatch_analysis_indexing([analysis_id])

    assert dispatched == [("analysis", str(analysis_id))]
