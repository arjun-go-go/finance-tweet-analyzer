import pytest
from fastapi import HTTPException

from app.core import rate_limit


class _Redis:
    def __init__(self, count):
        self.count = count
        self.calls = []

    def eval(self, script, key_count, key, window):
        self.calls.append((key_count, key, window))
        return self.count


def test_fixed_window_rate_limit_allows_requests_within_limit(monkeypatch):
    client = _Redis(count=3)
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: client)

    assert rate_limit.allow_request("auth:login:127.0.0.1", limit=5, window=60)
    assert client.calls == [(1, "rate:auth:login:127.0.0.1", 60)]


def test_fixed_window_rate_limit_rejects_requests_over_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: _Redis(count=6))

    assert not rate_limit.allow_request(
        "auth:login:127.0.0.1", limit=5, window=60
    )


def test_user_limit_uses_scoped_key_and_fails_closed(monkeypatch):
    seen = {}

    def allow(key, *, limit, window):
        seen.update(key=key, limit=limit, window=window)
        return True

    monkeypatch.setattr(rate_limit, "allow_request", allow)
    rate_limit.enforce_user_limit(
        "user-analysis:user-id", limit=10, window=86400
    )
    assert seen == {
        "key": "user-analysis:user-id",
        "limit": 10,
        "window": 86400,
    }

    monkeypatch.setattr(rate_limit, "allow_request", lambda *a, **k: False)
    with pytest.raises(HTTPException) as exc:
        rate_limit.enforce_user_limit(
            "user-analysis:user-id", limit=10, window=86400
        )
    assert (exc.value.status_code, exc.value.detail) == (
        429,
        "Daily analysis request limit exceeded",
    )
