import pytest

from app.core import database_guard


def test_resolve_test_database_url_reads_environment(monkeypatch):
    expected = (
        "postgresql+psycopg://postgres:secret@db.example.com:5432/"
        "finance_tweets_test"
    )
    monkeypatch.setenv("TEST_DATABASE_URL", expected)

    resolver = getattr(database_guard, "resolve_test_database_url", None)

    assert resolver is not None
    assert resolver() == expected


def test_resolve_test_database_url_rejects_non_test_database(monkeypatch):
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:secret@db.example.com:5432/finance_tweets",
    )

    with pytest.raises(ValueError, match="_test"):
        database_guard.resolve_test_database_url()
