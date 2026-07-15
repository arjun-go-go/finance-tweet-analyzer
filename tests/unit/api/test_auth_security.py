import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
import uuid

from app.api import auth
from app.api.auth import RefreshRequest, RegisterRequest, refresh, register
from app.models.user import User


@pytest.mark.parametrize("password", ["short", "onlyeight"])
def test_registration_rejects_passwords_shorter_than_twelve(password):
    request = RegisterRequest(
        email="user@example.com",
        username="user",
        password=password,
    )

    with pytest.raises(HTTPException) as exc:
        register(request, db=object())

    assert exc.value.status_code == 400


def test_registration_requires_mixed_password_characters():
    request = RegisterRequest(
        email="user@example.com",
        username="user",
        password="abcdefghijkl",
    )

    with pytest.raises(HTTPException) as exc:
        register(request, db=object())

    assert exc.value.status_code == 400


def test_refresh_rejects_replayed_token(monkeypatch):
    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        username="user",
        password_hash="unused",
        status="active",
    )
    expires = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda _token: {
            "sub": str(user.id),
            "type": "refresh",
            "jti": "used-token",
            "exp": expires,
        },
    )
    monkeypatch.setattr(auth, "get_user_by_id", lambda *_args: user)
    monkeypatch.setattr(auth, "consume_refresh_token", lambda *_args, **_kwargs: False)

    with pytest.raises(HTTPException) as exc:
        refresh(RefreshRequest(refresh_token="token"), db=object())

    assert exc.value.status_code == 401
