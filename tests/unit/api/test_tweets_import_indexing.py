import uuid
from datetime import datetime, timezone

from app.api.tweets import import_tweets_endpoint
from app.schemas.tweet import TweetImportItem, TweetImportRequest


def test_import_endpoint_dispatches_raw_tweet_rag_indexing(monkeypatch):
    tweet_id = uuid.uuid4()
    dispatched = []

    def fake_import_tweets(_db, _tweets, _blogger, *, return_ids=False):
        assert return_ids is True
        return 1, 0, [tweet_id]

    class FakeEmbedTask:
        @staticmethod
        def delay(source_type, source_id):
            dispatched.append((source_type, source_id))

    monkeypatch.setattr("app.api.tweets.import_tweets", fake_import_tweets)
    monkeypatch.setattr("app.api.tweets.embed_signal_task", FakeEmbedTask)

    response = import_tweets_endpoint(
        TweetImportRequest(
            tweets=[
                TweetImportItem(
                    tweet_id="tw-1",
                    author_handle="alice",
                    content="NVDA earnings look strong",
                    published_at=datetime.now(timezone.utc),
                )
            ]
        ),
        _admin=object(),
        db=object(),
    )

    assert response.imported == 1
    assert response.skipped == 0
    assert dispatched == [("tweet", str(tweet_id))]
