import inspect
import uuid

import pytest

from app.agents import chat_agent, sql_agent


def test_chat_agent_requires_identity_in_runtime_config():
    assert hasattr(chat_agent, "_get_authenticated_user_id")
    get_user_id = chat_agent._get_authenticated_user_id

    user_id = uuid.uuid4()
    assert get_user_id({"metadata": {"user_id": str(user_id).upper()}}) == str(
        user_id
    )
    assert get_user_id({"metadata": {"user_id": user_id}}) == str(user_id)

    for invalid_user_id in (None, "", "default", "authenticated-user", 123):
        with pytest.raises(ValueError):
            get_user_id({"metadata": {"user_id": invalid_user_id}})


def test_sql_generation_rejects_non_uuid_identity_before_database_access(monkeypatch):
    class _LLM:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return sql_agent.SQLGenResult(sql="", thought_process="", confidence=0)

    monkeypatch.setattr(sql_agent, "_get_user_context", lambda _user_id: "")
    monkeypatch.setattr(sql_agent, "get_signal_llm", lambda: _LLM())

    with pytest.raises(ValueError):
        sql_agent.generate_sql_node(
            {"question": "show my preferences", "user_id": "not-a-uuid"}
        )


def test_sql_execution_rejects_non_uuid_identity_before_database_access(monkeypatch):
    class _Db:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            raise AssertionError("database must not be accessed")

    monkeypatch.setattr(sql_agent, "SessionLocal", _Db)

    with pytest.raises(ValueError):
        sql_agent.execute_sql_node(
            {"generated_sql": "SELECT 1", "user_id": "not-a-uuid"}
        )


@pytest.mark.parametrize(
    ("function", "parameter"),
    [
        (chat_agent._query_database_impl, "user_id"),
        (sql_agent._get_user_context, "user_id"),
        (sql_agent.run_sql_query, "user_id"),
    ],
)
def test_agent_memory_entry_points_require_explicit_identity(function, parameter):
    assert inspect.signature(function).parameters[parameter].default is inspect.Parameter.empty


def test_sql_generation_fails_closed_without_user_identity():
    with pytest.raises(KeyError):
        sql_agent.generate_sql_node({"question": "show my preferences"})
