"""Unit-test conftest — intentionally minimal.

Run unit tests from the finance-tweet-analyzer directory:

    cd finance-tweet-analyzer
    uv run python -m pytest tests/unit/ -v --confcutdir=tests/unit --rootdir=.

The --confcutdir flag prevents pytest from loading the integration conftest
(tests/conftest.py) that requires PostgreSQL, FastAPI, and other heavy deps.
"""
