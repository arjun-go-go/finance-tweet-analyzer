def test_import_tweets_success(client):
    payload = {
        "tweets": [
            {
                "tweet_id": "1234567890",
                "author_handle": "@crypto_whale",
                "author_name": "Crypto Whale",
                "content": "BTC looks ready to break 70k. Loading spot here with target 75k.",
                "published_at": "2026-05-26T10:30:00Z",
                "metrics": {"likes": 500, "retweets": 120},
            }
        ]
    }
    response = client.post("/api/tweets/import", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["imported"] == 1
    assert data["skipped"] == 0


def test_import_tweets_dedup(client):
    tweet = {
        "tweet_id": "1234567890",
        "author_handle": "@crypto_whale",
        "author_name": "Crypto Whale",
        "content": "BTC long signal",
        "published_at": "2026-05-26T10:30:00Z",
    }
    client.post("/api/tweets/import", json={"tweets": [tweet]})
    response = client.post("/api/tweets/import", json={"tweets": [tweet]})
    data = response.json()
    assert data["imported"] == 0
    assert data["skipped"] == 1
