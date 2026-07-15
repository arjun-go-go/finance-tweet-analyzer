import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.core.deps import get_db
from app.core.rate_limit import enforce_auth_rate_limit


@pytest.fixture(scope="module")
def unauthenticated_client():
    focused_app = FastAPI()
    focused_app.include_router(api_router)
    focused_app.dependency_overrides[get_db] = lambda: object()
    focused_app.dependency_overrides[enforce_auth_rate_limit] = lambda: None
    return TestClient(focused_app)


@pytest.mark.parametrize(
    "path",
    [
        "/api/bloggers",
        "/api/bloggers/example/predictions",
        "/api/bloggers/example",
        "/api/tweets",
        "/api/analyses",
        "/api/ticker-summaries",
        "/api/dashboard/overview",
    ],
)
def test_shared_read_endpoints_require_authentication(
    unauthenticated_client, path
):
    response = unauthenticated_client.get(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/auth/register"),
        ("post", "/api/auth/login"),
        ("post", "/api/auth/refresh"),
    ],
)
def test_intentionally_public_endpoints_are_not_auth_guarded(
    unauthenticated_client, method, path
):
    response = getattr(unauthenticated_client, method)(path, json={})

    assert response.status_code != 401


def test_health_endpoint_has_no_authentication_dependency():
    health_route = next(
        route
        for route in api_router.routes
        if getattr(route, "path", None) == "/api/health"
    )

    assert health_route.dependant.dependencies == []
