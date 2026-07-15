import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import router
from app.core.auth import get_current_user
from app.core.deps import get_db
from app.models.user import User


@pytest.fixture(scope="module")
def authenticated_stateless_client():
    focused_app = FastAPI()
    focused_app.include_router(router)
    focused_app.dependency_overrides[get_db] = lambda: object()
    focused_app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(),
        email="user@example.test",
        username="user",
        password_hash="unused",
        status="active",
    )
    return TestClient(focused_app)


def test_conversation_create_rejects_client_supplied_user_id(
    authenticated_stateless_client, auth
):
    response = authenticated_stateless_client.post(
        "/api/chat/conversations",
        headers=auth.headers("authenticated-user"),
        json={"title": "private", "user_id": auth.user_id("victim")},
    )

    assert response.status_code == 422


def test_conversation_update_rejects_client_supplied_user_id(
    authenticated_stateless_client, auth
):
    response = authenticated_stateless_client.patch(
        f"/api/chat/conversations/{uuid.uuid4()}",
        headers=auth.headers("authenticated-user"),
        json={"title": "private", "user_id": auth.user_id("victim")},
    )

    assert response.status_code == 422
