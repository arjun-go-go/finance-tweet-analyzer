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
