from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text


def _column_default(connection, table_name: str):
    return connection.execute(
        text(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = 'user_id'
            """
        ),
        {"table_name": table_name},
    ).scalar_one()


def test_memory_user_id_defaults_downgrade_and_upgrade(engine):
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    migration = scripts.get_revision("c7b6e2d9f104").module
    with engine.connect() as connection, connection.begin():
        migration.op = Operations(MigrationContext.configure(connection))

        migration.downgrade()
        assert _column_default(connection, "user_preferences") is not None
        assert _column_default(connection, "user_profile") is not None

        migration.upgrade()
        assert _column_default(connection, "user_preferences") is None
        assert _column_default(connection, "user_profile") is None
