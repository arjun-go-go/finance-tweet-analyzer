"""Clear project history from PostgreSQL, Elasticsearch, Redis and Milvus.

The operation deliberately preserves user accounts, schema migration records,
and instrument correction rules. It does not touch MinIO objects.

Usage:
    uv run python -m app.scripts.clear_project_history --confirm CLEAR_PROJECT_HISTORY
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from elasticsearch import Elasticsearch
from pymilvus import MilvusClient
from redis import Redis
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.deps import engine


CONFIRMATION = "CLEAR_PROJECT_HISTORY"
PRESERVED_PG_TABLES = {
    "alembic_version",
    "checkpoint_migrations",
    "instrument_correction_rules",
    "users",
}


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def clear_postgres() -> dict[str, Any]:
    tables = sorted(
        table
        for table in inspect(engine).get_table_names(schema="public")
        if table not in PRESERVED_PG_TABLES
    )
    if tables:
        quoted = ", ".join(f"public.{_quote_identifier(table)}" for table in tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    return {"cleared_tables": tables, "preserved_tables": sorted(PRESERVED_PG_TABLES)}


def _elasticsearch_client() -> Elasticsearch:
    kwargs: dict[str, Any] = {"request_timeout": max(settings.es_request_timeout_sec, 30)}
    if settings.elasticsearch_username or settings.elasticsearch_password:
        kwargs["basic_auth"] = (
            settings.elasticsearch_username,
            settings.elasticsearch_password,
        )
    return Elasticsearch(settings.elasticsearch_url, **kwargs)


def clear_elasticsearch() -> dict[str, Any]:
    client = _elasticsearch_client()
    alias = settings.es_rag_index
    current_indexes: list[str] = []
    if client.indices.exists_alias(name=alias):
        current_indexes = sorted(client.indices.get_alias(name=alias).keys())
        client.delete_by_query(
            index=alias,
            query={"match_all": {}},
            conflicts="proceed",
            refresh=True,
        )

    all_versions = sorted(client.indices.get(index=f"{alias}_v*", allow_no_indices=True).keys())
    stale_indexes = [index for index in all_versions if index not in current_indexes]
    if stale_indexes:
        client.indices.delete(index=",".join(stale_indexes))

    remaining = client.count(index=alias).get("count", 0) if current_indexes else 0
    return {
        "alias": alias,
        "current_indexes": current_indexes,
        "deleted_stale_indexes": stale_indexes,
        "remaining_documents": int(remaining),
    }


def clear_redis() -> dict[str, Any]:
    cleared: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for label, url in (
        ("application", settings.redis_url),
        ("celery_broker", settings.celery_broker_url),
        ("celery_results", settings.celery_result_backend),
    ):
        client = Redis.from_url(url, decode_responses=True)
        info = client.connection_pool.connection_kwargs
        key = (str(info.get("host")), int(info.get("port", 6379)), int(info.get("db", 0)))
        if key in seen:
            continue
        seen.add(key)
        before = client.dbsize()
        client.flushdb()
        cleared.append({"label": label, "database": key[2], "keys_before": before, "keys_after": client.dbsize()})
        client.close()
    return {"databases": cleared}


def clear_milvus() -> dict[str, Any]:
    client = MilvusClient(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        db_name=settings.milvus_db_name,
        timeout=settings.milvus_timeout_sec,
    )
    existing = set(client.list_collections())
    prefix = settings.milvus_collection_prefix.strip("_") + "_"
    project_collections = sorted(
        name
        for name in existing
        if name.startswith(prefix)
        or name == settings.mem0_milvus_collection
        or name == "mem0migrations"
    )
    for name in project_collections:
        client.drop_collection(name)
    return {"dropped_collections": project_collections}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Refusing cleanup: pass --confirm {CONFIRMATION}")

    result = {
        "postgresql": clear_postgres(),
        "elasticsearch": clear_elasticsearch(),
        "redis": clear_redis(),
        "milvus": clear_milvus(),
        "minio": "preserved",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
