from app.services import auth_service


def test_refresh_tokens_include_unique_ids():
    first = auth_service.decode_token(auth_service.create_refresh_token("user-id"))
    second = auth_service.decode_token(auth_service.create_refresh_token("user-id"))

    assert first["jti"]
    assert second["jti"]
    assert first["jti"] != second["jti"]


class _Redis:
    def __init__(self, accepted):
        self.accepted = accepted
        self.calls = []

    def set(self, key, value, *, nx, ex):
        self.calls.append((key, value, nx, ex))
        return self.accepted


def test_refresh_token_can_only_be_consumed_once(monkeypatch):
    client = _Redis(accepted=True)
    monkeypatch.setattr(auth_service, "_get_auth_redis", lambda: client)

    assert auth_service.consume_refresh_token("token-id", ttl_seconds=60)
    assert client.calls == [("auth:refresh-used:token-id", "1", True, 60)]

    client.accepted = False
    assert not auth_service.consume_refresh_token("token-id", ttl_seconds=60)
