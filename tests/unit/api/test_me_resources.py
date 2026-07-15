from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.router import api_router
from app.api.me import router as me_router
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.models import Blogger, Tweet, User, UserBloggerFollow, UserTweetBookmark
from app.schemas.blogger import BloggerDetail, BloggerListItem


def _persist_user(db_session, auth, alias: str) -> User:
    user = User(
        id=UUID(auth.user_id(alias)),
        email=f"{alias}-{uuid4()}@example.test",
        username=f"{alias}-{uuid4()}",
        password_hash="unused",
        status="active",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _blogger(alias: str) -> Blogger:
    return Blogger(handle=f"{alias}-{uuid4()}", name=alias)


def _tweet(alias: str) -> Tweet:
    return Tweet(
        tweet_id=str(uuid4()),
        author_handle=alias,
        author_name=f"{alias} name",
        content=f"tweet from {alias}",
        published_at=datetime.now(timezone.utc),
        metrics={"likes": 3},
    )


def test_follow_is_user_scoped_and_delete_hides_ownership(client, db_session, auth):
    _persist_user(db_session, auth, "alice")
    _persist_user(db_session, auth, "bob")
    blogger = _blogger("analyst")
    db_session.add(blogger)
    db_session.flush()

    created = client.post(
        f"/api/me/bloggers/{blogger.id}/follow",
        headers=auth.headers("alice"),
    )
    assert created.status_code == 201
    assert created.json()["blogger_id"] == str(blogger.id)
    assert "user_id" not in created.json()

    bob_list = client.get("/api/me/bloggers", headers=auth.headers("bob"))
    assert bob_list.status_code == 200
    assert bob_list.json() == {"items": [], "total": 0}
    assert client.delete(
        f"/api/me/bloggers/{blogger.id}/follow", headers=auth.headers("bob")
    ).status_code == 404
    assert client.delete(
        f"/api/me/bloggers/{blogger.id}/follow", headers=auth.headers("alice")
    ).status_code == 204
    assert client.delete(
        f"/api/me/bloggers/{blogger.id}/follow", headers=auth.headers("alice")
    ).status_code == 404


def test_bookmark_is_user_scoped_and_delete_hides_ownership(client, db_session, auth):
    _persist_user(db_session, auth, "alice")
    _persist_user(db_session, auth, "bob")
    tweet = _tweet("analyst")
    db_session.add(tweet)
    db_session.flush()

    created = client.post(
        f"/api/me/tweets/{tweet.id}/bookmark", headers=auth.headers("alice")
    )
    assert created.status_code == 201
    assert created.json()["tweet_id"] == str(tweet.id)
    assert "user_id" not in created.json()
    assert client.get("/api/me/tweets", headers=auth.headers("bob")).json() == {
        "items": [],
        "total": 0,
    }
    assert client.delete(
        f"/api/me/tweets/{tweet.id}/bookmark", headers=auth.headers("bob")
    ).status_code == 404
    assert client.delete(
        f"/api/me/tweets/{tweet.id}/bookmark", headers=auth.headers("alice")
    ).status_code == 204
    assert client.delete(
        f"/api/me/tweets/{tweet.id}/bookmark", headers=auth.headers("alice")
    ).status_code == 404


@pytest.mark.parametrize("kind", ["follow", "bookmark"])
def test_duplicate_mutation_is_201_and_creates_one_row(
    client, db_session, auth, kind
):
    user = _persist_user(db_session, auth, "alice")
    target = _blogger("analyst") if kind == "follow" else _tweet("analyst")
    db_session.add(target)
    db_session.flush()
    path = (
        f"/api/me/bloggers/{target.id}/follow"
        if kind == "follow"
        else f"/api/me/tweets/{target.id}/bookmark"
    )

    assert client.post(path, headers=auth.headers("alice")).status_code == 201
    assert client.post(path, headers=auth.headers("alice")).status_code == 201
    relation = UserBloggerFollow if kind == "follow" else UserTweetBookmark
    assert db_session.scalar(
        select(func.count()).select_from(relation).where(relation.user_id == user.id)
    ) == 1


@pytest.mark.parametrize(
    "path", [
        "/api/me/bloggers/{id}/follow",
        "/api/me/tweets/{id}/bookmark",
    ]
)
def test_missing_shared_resource_returns_safe_404(client, db_session, auth, path):
    _persist_user(db_session, auth, "alice")
    missing_id = uuid4()
    response = client.post(
        path.format(id=missing_id), headers=auth.headers("alice")
    )
    assert response.status_code == 404
    assert str(missing_id) not in response.text


def test_follow_limit_uses_setting_but_existing_follow_stays_idempotent(
    client, db_session, auth, monkeypatch
):
    _persist_user(db_session, auth, "alice")
    first = _blogger("first")
    second = _blogger("second")
    db_session.add_all([first, second])
    db_session.flush()
    monkeypatch.setattr(settings, "max_followed_bloggers_per_user", 1)

    first_path = f"/api/me/bloggers/{first.id}/follow"
    assert client.post(first_path, headers=auth.headers("alice")).status_code == 201
    assert client.post(first_path, headers=auth.headers("alice")).status_code == 201
    limited = client.post(
        f"/api/me/bloggers/{second.id}/follow", headers=auth.headers("alice")
    )
    assert limited.status_code == 429
    assert "alice" not in limited.text


def test_lists_paginate_with_total_and_canonical_items(client, db_session, auth):
    _persist_user(db_session, auth, "alice")
    bloggers = [_blogger("first"), _blogger("second")]
    tweets = [_tweet("first"), _tweet("second")]
    db_session.add_all([*bloggers, *tweets])
    db_session.flush()
    for blogger in bloggers:
        client.post(
            f"/api/me/bloggers/{blogger.id}/follow", headers=auth.headers("alice")
        )
    for tweet in tweets:
        client.post(
            f"/api/me/tweets/{tweet.id}/bookmark", headers=auth.headers("alice")
        )

    followed = client.get(
        "/api/me/bloggers?limit=1&offset=1", headers=auth.headers("alice")
    )
    bookmarked = client.get(
        "/api/me/tweets?limit=1&offset=1", headers=auth.headers("alice")
    )
    assert followed.status_code == bookmarked.status_code == 200
    assert followed.json()["total"] == bookmarked.json()["total"] == 2
    assert len(followed.json()["items"]) == len(bookmarked.json()["items"]) == 1
    assert followed.json()["items"][0]["id"] in {str(item.id) for item in bloggers}
    tweet_item = bookmarked.json()["items"][0]
    assert tweet_item["id"] in {str(item.id) for item in tweets}
    assert set(tweet_item) == {
        "id", "tweet_id", "author_handle", "author_name", "content",
        "published_at", "status", "metrics",
    }
    assert client.get(
        "/api/me/bloggers?limit=0", headers=auth.headers("alice")
    ).status_code == 422
    assert client.get(
        "/api/me/tweets?offset=-1", headers=auth.headers("alice")
    ).status_code == 422


@pytest.mark.parametrize("kind", ["follow", "bookmark"])
def test_client_user_id_inputs_do_not_change_owner(client, db_session, auth, kind):
    alice = _persist_user(db_session, auth, "alice")
    mallory = _persist_user(db_session, auth, "mallory")
    target = _blogger("analyst") if kind == "follow" else _tweet("analyst")
    db_session.add(target)
    db_session.flush()
    path = (
        f"/api/me/bloggers/{target.id}/follow"
        if kind == "follow"
        else f"/api/me/tweets/{target.id}/bookmark"
    )

    response = client.post(
        f"{path}?user_id={mallory.id}",
        json={"user_id": str(mallory.id)},
        headers=auth.headers("alice"),
    )
    assert response.status_code == 201
    relation = UserBloggerFollow if kind == "follow" else UserTweetBookmark
    owners = db_session.scalars(select(relation.user_id)).all()
    assert owners == [alice.id]


def test_shared_blogger_schemas_require_canonical_id():
    assert BloggerListItem.model_fields["id"].is_required()
    assert BloggerDetail.model_fields["id"].is_required()


def test_public_blogger_list_returns_canonical_id(client, db_session, auth):
    _persist_user(db_session, auth, "reader")
    blogger = _blogger("public-list")
    db_session.add(blogger)
    db_session.flush()

    response = client.get("/api/bloggers", headers=auth.headers("reader"))

    assert response.status_code == 200
    item = next(
        item for item in response.json() if item["handle"] == blogger.handle
    )
    assert item["id"] == str(blogger.id)


def test_public_blogger_detail_returns_canonical_id(client, db_session, auth):
    _persist_user(db_session, auth, "reader")
    blogger = Blogger(
        handle=f"encoded/analyst-{uuid4()}",
        name="Encoded Analyst",
    )
    db_session.add(blogger)
    db_session.flush()

    encoded_handle = quote(blogger.handle, safe="")
    response = client.get(
        f"/api/bloggers/{encoded_handle}", headers=auth.headers("reader")
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(blogger.id)


def test_me_routes_require_real_authentication(db_session):
    focused_app = FastAPI()
    focused_app.include_router(api_router)

    def override_get_db():
        yield db_session

    focused_app.dependency_overrides[get_db] = override_get_db
    with TestClient(focused_app) as unauthenticated:
        response = unauthenticated.get("/api/me/bloggers")
    assert response.status_code == 401

    me_routes = list(me_router.routes)
    assert len(me_routes) == 6
    assert all(
        get_current_user in {dependency.call for dependency in route.dependant.dependencies}
        for route in me_routes
    )
