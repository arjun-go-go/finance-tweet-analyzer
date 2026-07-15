import pytest
from fastapi import HTTPException

from app.api import analysis


def _result():
    return {
        "batch_id": "batch",
        "analyzed": 0,
        "analyses": [],
        "ticker_summaries": [],
    }


def test_single_tweet_returns_conflict_when_lock_is_held(monkeypatch):
    monkeypatch.setattr(analysis, "try_acquire", lambda _key: (False, ""))
    monkeypatch.setattr(analysis, "analyze_single_tweet", lambda *_args: _result())

    with pytest.raises(HTTPException) as exc:
        analysis.analyze_single_tweet_endpoint(
            "tweet-id", _admin=object(), db=object()
        )

    assert exc.value.status_code == 409


def test_single_tweet_releases_lock_with_ownership_token(monkeypatch):
    released = []
    monkeypatch.setattr(analysis, "try_acquire", lambda _key: (True, "owner-token"))
    monkeypatch.setattr(analysis, "release", lambda key, token: released.append((key, token)))
    monkeypatch.setattr(analysis, "analyze_single_tweet", lambda *_args: _result())

    result = analysis.analyze_single_tweet_endpoint(
        "tweet-id", _admin=object(), db=object()
    )

    assert result == _result()
    assert released == [("tweet_analysis:tweet-id", "owner-token")]


def test_blogger_releases_lock_when_analysis_raises(monkeypatch):
    released = []
    monkeypatch.setattr(analysis, "try_acquire", lambda _key: (True, "owner-token"))
    monkeypatch.setattr(analysis, "release", lambda key, token: released.append((key, token)))

    def fail(*_args):
        raise RuntimeError("analysis failed")

    monkeypatch.setattr(analysis, "analyze_by_blogger", fail)

    with pytest.raises(RuntimeError, match="analysis failed"):
        analysis.analyze_single_blogger(
            "alice", _admin=object(), db=object()
        )

    assert released == [("alice", "owner-token")]
