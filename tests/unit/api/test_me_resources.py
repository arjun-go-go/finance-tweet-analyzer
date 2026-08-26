from uuid import UUID, uuid4

from app.models import Blogger, User


def _user(db_session, auth, alias: str) -> User:
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


def test_follow_endpoints_are_user_scoped(client, db_session, auth):
    _user(db_session, auth, "alice")
    _user(db_session, auth, "bob")
    blogger = Blogger(handle=f"analyst-{uuid4()}", name="Analyst")
    db_session.add(blogger)
    db_session.flush()

    created = client.post(
        f"/api/me/bloggers/{blogger.id}/follow",
        headers=auth.headers("alice"),
    )
    assert created.status_code == 201
    assert created.json()["blogger_id"] == str(blogger.id)

    assert client.get(
        "/api/me/bloggers", headers=auth.headers("bob")
    ).json() == {"items": [], "total": 0}
    assert client.delete(
        f"/api/me/bloggers/{blogger.id}/follow",
        headers=auth.headers("bob"),
    ).status_code == 404
    assert client.delete(
        f"/api/me/bloggers/{blogger.id}/follow",
        headers=auth.headers("alice"),
    ).status_code == 204


def test_follow_missing_blogger_returns_safe_404(client, db_session, auth):
    _user(db_session, auth, "alice")
    missing_id = uuid4()
    response = client.post(
        f"/api/me/bloggers/{missing_id}/follow",
        headers=auth.headers("alice"),
    )
    assert response.status_code == 404
    assert str(missing_id) not in response.text
