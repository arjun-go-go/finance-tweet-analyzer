import uuid

import pytest
from sqlalchemy.exc import OperationalError
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_admin, get_current_user
from app.core.deps import get_db
from app.core.database_guard import resolve_test_database_url
from app.main import app
from app.models import Base
from app.models.user import User


class TestAuth:
    _namespace = uuid.UUID("6f320a6c-84c8-4bbd-86e4-26ca3a4c7d56")

    @classmethod
    def user_id(cls, alias: str) -> str:
        return str(uuid.uuid5(cls._namespace, alias))

    @staticmethod
    def headers(alias: str = "default") -> dict[str, str]:
        return {"X-Test-User": alias}


def _test_user(request: Request) -> User:
    alias = request.headers.get("X-Test-User", "default")
    return User(
        id=uuid.UUID(TestAuth.user_id(alias)),
        email=f"{alias}@example.test",
        username=alias,
        password_hash="unused",
        status="active",
    )


@pytest.fixture
def auth() -> TestAuth:
    return TestAuth()


@pytest.fixture(scope="session")
def engine():
    test_database_url = resolve_test_database_url()
    eng = create_engine(
        test_database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with eng.connect():
            pass
    except OperationalError:
        eng.dispose()
        pytest.skip(
            "PostgreSQL test database finance_tweets_test is unavailable"
        )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(
        bind=connection, autoflush=False, expire_on_commit=False
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = _test_user
    app.dependency_overrides[get_current_admin] = _test_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
