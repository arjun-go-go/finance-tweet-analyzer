"""Safety helpers for destructive database operations."""

import os

from sqlalchemy.engine import make_url


DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets_test"
)


def resolve_test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database_name = make_url(database_url).database or ""
    if not database_name.lower().endswith("_test"):
        raise ValueError("TEST_DATABASE_URL database name must end with '_test'")
    return database_url
