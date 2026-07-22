import uuid
from datetime import datetime, timezone

from app.models.tweet import Tweet
from app.schemas.tweet import TweetImportItem
from app.services.tweet_service import import_tweets


class _ScalarResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def execute(self, _stmt):
        return _ScalarResult(None)

    def add(self, row):
        self.added.append(row)
        if isinstance(row, Tweet) and row.id is None:
            row.id = uuid.uuid4()

    def commit(self):
        self.committed = True


def test_import_tweets_can_return_new_tweet_ids_for_rag_dispatch():
    db = _FakeSession()
    item = TweetImportItem(
        tweet_id="tw-1",
        author_handle="alice",
        content="NVDA earnings look strong",
        published_at=datetime.now(timezone.utc),
    )

    imported, skipped, tweet_ids = import_tweets(db, [item], return_ids=True)

    assert imported == 1
    assert skipped == 0
    assert len(tweet_ids) == 1
    assert tweet_ids[0] == db.added[0].id
    assert db.committed is True


def test_import_tweets_default_return_shape_stays_backward_compatible():
    db = _FakeSession()
    item = TweetImportItem(
        tweet_id="tw-1",
        author_handle="alice",
        content="NVDA earnings look strong",
        published_at=datetime.now(timezone.utc),
    )

    result = import_tweets(db, [item])

    assert result == (1, 0)
