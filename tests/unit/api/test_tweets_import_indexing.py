import uuid
from datetime import datetime, timezone

from app.api.tweets import import_tweets_endpoint
from app.schemas.tweet import TweetImportItem, TweetImportRequest


def test_import_endpoint_delegates_indexing_to_import_service(monkeypatch):
    tweet_id = uuid.uuid4()

    def fake_import_tweets(_db, _tweets, _blogger, *, return_ids=False):
        assert return_ids is True
        return 1, 0, [tweet_id]

    monkeypatch.setattr("app.api.tweets.import_tweets", fake_import_tweets)

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
    assert tweet_id is not None
