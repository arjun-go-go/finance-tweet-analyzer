from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from loguru import logger

from app.core.config import settings

_saver: PostgresSaver | None = None
_pool: ConnectionPool | None = None


def get_checkpointer() -> PostgresSaver:
    if _saver is None:
        raise RuntimeError("Checkpointer not initialized. Call setup_checkpointer() first.")
    return _saver


def _checkpoint_tables_exist(conn) -> bool:
    cur = conn.execute(
        "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'checkpoint%'"
    )
    count = cur.fetchone()[0]
    return count >= 3


def setup_checkpointer() -> None:
    global _saver, _pool
    conn_str = settings.database_url.replace("+psycopg", "")

    _pool = ConnectionPool(
        conn_str,
        min_size=2,
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "connect_timeout": 10},
    )
    _saver = PostgresSaver(conn=_pool)

    with _pool.connection() as conn:
        if not _checkpoint_tables_exist(conn):
            _saver.setup()
            logger.info("Checkpointer initialized (tables created)")
        else:
            logger.info("Checkpointer initialized (tables already exist)")


def teardown_checkpointer() -> None:
    global _saver, _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
    _saver = None
    _pool = None
    logger.info("Checkpointer shut down")
