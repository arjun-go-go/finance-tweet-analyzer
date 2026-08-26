"""Shared PostgreSQL history adapter for mem0 OSS.

mem0 2.0.6 hard-codes a local SQLite manager for memory history and the last
messages used during extraction.  The application replaces that manager with
this small API-compatible adapter so every API/worker instance sees the same
state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.deps import engine as app_engine


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class PostgresMemoryHistory:
    """Implement the storage methods consumed by ``mem0.Memory``."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or app_engine

    def add_history(
        self,
        memory_id: str,
        old_memory: str | None,
        new_memory: str | None,
        event: str,
        *,
        created_at: str | None = None,
        updated_at: str | None = None,
        is_deleted: int = 0,
        actor_id: str | None = None,
        role: str | None = None,
    ) -> None:
        self.batch_add_history([{
            "memory_id": memory_id,
            "old_memory": old_memory,
            "new_memory": new_memory,
            "event": event,
            "created_at": created_at,
            "updated_at": updated_at,
            "is_deleted": is_deleted,
            "actor_id": actor_id,
            "role": role,
        }])

    def batch_add_history(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        statement = text("""
            INSERT INTO mem0_history (
                id, memory_id, old_memory, new_memory, event,
                created_at, updated_at, is_deleted, actor_id, role
            ) VALUES (
                :id, :memory_id, :old_memory, :new_memory, :event,
                COALESCE(CAST(:created_at AS timestamptz), now()),
                CAST(:updated_at AS timestamptz), :is_deleted, :actor_id, :role
            )
        """)
        values = [{
            "id": str(uuid.uuid4()),
            "memory_id": record.get("memory_id"),
            "old_memory": record.get("old_memory"),
            "new_memory": record.get("new_memory"),
            "event": record.get("event"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "is_deleted": bool(record.get("is_deleted", 0)),
            "actor_id": record.get("actor_id"),
            "role": record.get("role"),
        } for record in records]
        with self._engine.begin() as connection:
            connection.execute(statement, values)

    def get_history(self, memory_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT id, memory_id, old_memory, new_memory, event,
                       created_at, updated_at, is_deleted, actor_id, role
                FROM mem0_history
                WHERE memory_id = :memory_id
                ORDER BY created_at ASC, updated_at ASC NULLS FIRST
            """), {"memory_id": memory_id}).mappings().all()
        return [{**dict(row), "id": str(row["id"]),
                 "created_at": _as_iso(row["created_at"]),
                 "updated_at": _as_iso(row["updated_at"])} for row in rows]

    def save_messages(self, messages: list[dict[str, Any]], session_scope: str) -> None:
        if not messages:
            return
        now = datetime.now(timezone.utc)
        values = [{
            "id": str(uuid.uuid4()),
            "session_scope": session_scope,
            "role": message.get("role"),
            "content": message.get("content"),
            "name": message.get("name"),
            "created_at": now,
        } for message in messages]
        with self._engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO mem0_messages (
                    id, session_scope, role, content, name, created_at
                ) VALUES (
                    :id, :session_scope, :role, :content, :name, :created_at
                )
            """), values)
            connection.execute(text("""
                DELETE FROM mem0_messages
                WHERE session_scope = :session_scope
                  AND id IN (
                    SELECT id FROM mem0_messages
                    WHERE session_scope = :session_scope
                    ORDER BY created_at DESC, id DESC
                    OFFSET 10
                  )
            """), {"session_scope": session_scope})

    def get_last_messages(self, session_scope: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT role, content, name, created_at FROM (
                    SELECT role, content, name, created_at
                    FROM mem0_messages
                    WHERE session_scope = :session_scope
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                ) recent
                ORDER BY created_at ASC
            """), {"session_scope": session_scope, "limit": limit}).mappings().all()
        return [{**dict(row), "created_at": _as_iso(row["created_at"])} for row in rows]

    def close(self) -> None:
        """Connections are transaction-scoped and owned by SQLAlchemy's pool."""

