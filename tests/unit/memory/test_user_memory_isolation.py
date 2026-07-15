import pytest
from types import SimpleNamespace

from sqlalchemy.sql.dml import Insert
from sqlalchemy.sql.selectable import Select

from app.memory.preferences import (
    extract_and_save_preferences,
    extract_preferences_background,
    get_preferences,
    upsert_preference,
)
from app.memory.profile import get_profile, upsert_profile
from app.models.user_preference import UserPreference
from app.models.user_profile import UserProfile


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _MemorySession:
    def __init__(self):
        self.profiles = {}
        self.preferences = {}

    def execute(self, statement):
        if isinstance(statement, Insert):
            values = {
                column.key: bind.value
                for column, bind in statement._values.items()
            }
            user_id = values["user_id"]
            if statement.table.name == "user_profile":
                current = self.profiles.setdefault(
                    user_id,
                    {
                        "name": None,
                        "nickname": None,
                        "occupation": None,
                        "birthday": None,
                        "location": None,
                    },
                )
                current.update({k: v for k, v in values.items() if k != "user_id"})
            else:
                key = (user_id, values["preference_type"])
                self.preferences[key] = values["value"]
            return _Result([])

        if isinstance(statement, Select):
            user_id = statement._where_criteria[0].right.value
            entity = statement.column_descriptions[0]["entity"]
            if entity.__name__ == "UserProfile":
                values = self.profiles.get(user_id)
                return _Result([SimpleNamespace(**values)] if values else [])
            rows = [
                SimpleNamespace(preference_type=pref_type, value=value)
                for (stored_user_id, pref_type), value in self.preferences.items()
                if stored_user_id == user_id
            ]
            return _Result(rows)

        raise AssertionError(f"Unexpected statement: {statement}")


def test_profiles_and_preferences_are_isolated_by_user_id():
    db_session = _MemorySession()
    alice_id = "10000000-0000-0000-0000-000000000001"
    bob_id = "20000000-0000-0000-0000-000000000002"

    upsert_profile(db_session, alice_id, {"nickname": "alice"})
    upsert_profile(db_session, bob_id, {"nickname": "bob"})
    upsert_preference(
        db_session, alice_id, "reply_style", {"style": "concise"}
    )
    upsert_preference(
        db_session, bob_id, "reply_style", {"style": "detailed"}
    )

    assert get_profile(db_session, alice_id)["nickname"] == "alice"
    assert get_profile(db_session, bob_id)["nickname"] == "bob"
    assert get_preferences(db_session, alice_id)["reply_style"] == "concise"
    assert get_preferences(db_session, bob_id)["reply_style"] == "detailed"

    upsert_profile(db_session, alice_id, {"nickname": "alice-updated"})
    upsert_preference(
        db_session, alice_id, "reply_style", {"style": "detailed"}
    )

    assert get_profile(db_session, alice_id)["nickname"] == "alice-updated"
    assert get_profile(db_session, bob_id)["nickname"] == "bob"
    assert get_preferences(db_session, bob_id)["reply_style"] == "detailed"


def test_memory_entry_points_require_explicit_user_id(monkeypatch):
    db_session = _MemorySession()
    monkeypatch.setattr("threading.Thread.start", lambda self: None)

    with pytest.raises(TypeError):
        get_profile(db_session)
    with pytest.raises(TypeError):
        get_preferences(db_session)
    with pytest.raises(TypeError):
        extract_and_save_preferences(db_session, "hello")
    with pytest.raises(TypeError):
        extract_preferences_background("hello")


def test_memory_models_do_not_fallback_to_a_default_identity():
    assert UserProfile.__table__.c.user_id.default is None
    assert UserPreference.__table__.c.user_id.default is None
