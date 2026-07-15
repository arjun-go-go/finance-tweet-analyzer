import inspect

import pytest

from app.agents import chat_agent, sql_agent


def test_chat_agent_requires_identity_in_runtime_config():
    assert hasattr(chat_agent, "_get_authenticated_user_id")
    get_user_id = chat_agent._get_authenticated_user_id

    assert get_user_id({"metadata": {"user_id": "authenticated-user"}}) == (
        "authenticated-user"
    )
    with pytest.raises(ValueError):
        get_user_id({"metadata": {}})
    with pytest.raises(ValueError):
        get_user_id({"metadata": {"user_id": "default"}})


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
