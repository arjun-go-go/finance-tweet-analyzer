from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_memory_identity_default_removal_migration_metadata():
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    migration = scripts.get_revision("c7b6e2d9f104")

    assert migration.down_revision == "a13c9f42b801"
    assert "memory" in migration.doc.lower()
    assert Path(migration.path).name.endswith("remove_memory_user_defaults.py")
