import uuid

import pytest
from fastapi import HTTPException

from app.core import auth
from app.core.config import settings
from app.models.user import User


def _user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="admin@example.com",
        username="admin",
        password_hash="unused",
        status="active",
    )


def test_get_current_admin_rejects_non_admin(monkeypatch):
    user = _user(uuid.uuid4())
    monkeypatch.setattr(settings, "admin_user_ids", [])

    with pytest.raises(HTTPException) as exc:
        auth.get_current_admin(user)

    assert exc.value.status_code == 403


def test_get_current_admin_accepts_configured_admin(monkeypatch):
    user = _user(uuid.uuid4())
    monkeypatch.setattr(settings, "admin_user_ids", [str(user.id)])

    assert auth.get_current_admin(user) is user


@pytest.mark.parametrize(
    ("module_name", "endpoint_name"),
    [
        ("app.api.analysis", "trigger_analysis_endpoint"),
        ("app.api.analysis", "analyze_single_tweet_endpoint"),
        ("app.api.analysis", "analyze_single_blogger"),
        ("app.api.analysis", "analyze_multiple_bloggers"),
        ("app.api.tweets", "import_tweets_endpoint"),
        ("app.api.bloggers", "upsert_blogger_endpoint"),
        ("app.api.bloggers", "toggle_fetch"),
        ("app.api.predictions", "verify_endpoint"),
        ("app.api.admin_traces", "list_tool_route_traces"),
    ],
)
def test_sensitive_endpoint_declares_admin_dependency(module_name, endpoint_name):
    module = __import__(module_name, fromlist=[endpoint_name])
    endpoint = getattr(module, endpoint_name)
    route = next(route for route in module.router.routes if route.endpoint is endpoint)
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
    assert auth.get_current_admin in dependency_calls


def test_debug_routes_are_not_registered_when_debug_disabled(monkeypatch):
    from app.api import router as router_module

    monkeypatch.setattr(settings, "debug_mode", False)
    paths = {
        route.path
        for route in router_module.build_api_router().routes
        if hasattr(route, "path")
    }

    assert "/api/debug/retrieve" not in paths
