from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_memory_identity_default_removal_is_alembic_head():
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_revision(scripts.get_current_head())

    assert head.down_revision == "a13c9f42b801"
    assert "memory" in head.doc.lower()
    assert Path(head.path).name.endswith("remove_memory_user_defaults.py")
