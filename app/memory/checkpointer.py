from psycopg import Connection
from langgraph.checkpoint.postgres import PostgresSaver
from loguru import logger

from app.core.config import settings

_saver: PostgresSaver | None = None
_conn: Connection | None = None


def get_checkpointer() -> PostgresSaver:
    if _saver is None:
        raise RuntimeError("Checkpointer not initialized. Call setup_checkpointer() first.")
    return _saver


def _checkpoint_tables_exist(conn: Connection) -> bool:
    cur = conn.execute(
        "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'checkpoint%'"
    )
    count = cur.fetchone()[0]
    return count >= 3


def setup_checkpointer() -> None:
    global _saver, _conn
    conn_str = settings.database_url.replace("+psycopg", "")
    _conn = Connection.connect(conn_str, autocommit=True, connect_timeout=10)
    _saver = PostgresSaver(conn=_conn)
    if not _checkpoint_tables_exist(_conn):
        _saver.setup()
        logger.info("Checkpointer initialized (tables created)")
    else:
        logger.info("Checkpointer initialized (tables already exist)")


def teardown_checkpointer() -> None:
    global _saver, _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _saver = None
    _conn = None
    logger.info("Checkpointer shut down")
