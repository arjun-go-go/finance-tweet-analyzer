"""Unit tests for mem0_recall_node and mem0_store_node."""
import time
import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage


_USER_ID = str(uuid.UUID("10000000-0000-0000-0000-000000000001"))


def _make_config(user_id=_USER_ID):
    return {"metadata": {"user_id": user_id}, "configurable": {"thread_id": "t1"}}


def test_recall_node_injects_memories():
    """mem0_recall_node returns memories list from mem0 search result."""
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [{"memory": "用户看好BTC短线"}, {"memory": "投资风格：短线"}]
    }
    with patch("app.agents.chat_agent.get_mem0_client", return_value=mock_client), \
         patch("app.agents.chat_agent.settings") as mock_settings, \
         patch("app.agents.chat_agent._is_mem0_spacy_model_available", return_value=True):
        mock_settings.mem0_top_k = 5
        mock_settings.mem0_enabled = True
        from app.agents.chat_agent import mem0_recall_node
        state = {"messages": [HumanMessage(content="BTC 现在怎么样？")], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_recall_node(state, _make_config())
    assert result == {"memories": ["用户看好BTC短线", "投资风格：短线"]}
    mock_client.search.assert_called_once_with("BTC 现在怎么样？", filters={"user_id": _USER_ID}, top_k=5)


def test_recall_node_disabled_returns_empty():
    """mem0_recall_node returns empty memories when client is None (disabled)."""
    with patch("app.agents.chat_agent.get_mem0_client", return_value=None):
        from app.agents.chat_agent import mem0_recall_node
        state = {"messages": [HumanMessage(content="hello")], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_recall_node(state, _make_config())
    assert result == {"memories": []}


def test_recall_node_exception_returns_empty():
    """mem0_recall_node silently degrades on exception."""
    mock_client = MagicMock()
    mock_client.search.side_effect = RuntimeError("timeout")
    with patch("app.agents.chat_agent.get_mem0_client", return_value=mock_client), \
         patch("app.agents.chat_agent.settings") as mock_settings, \
         patch("app.agents.chat_agent._is_mem0_spacy_model_available", return_value=True):
        mock_settings.mem0_top_k = 5
        from app.agents.chat_agent import mem0_recall_node
        state = {"messages": [HumanMessage(content="hello")], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_recall_node(state, _make_config())
    assert result == {"memories": []}


def test_recall_node_system_exit_returns_empty():
    """mem0_recall_node degrades when a dependency calls sys.exit."""
    mock_client = MagicMock()
    mock_client.search.side_effect = SystemExit(1)
    with patch("app.agents.chat_agent.get_mem0_client", return_value=mock_client), \
         patch("app.agents.chat_agent.settings") as mock_settings, \
         patch("app.agents.chat_agent._is_mem0_spacy_model_available", return_value=True):
        mock_settings.mem0_top_k = 5
        from app.agents.chat_agent import mem0_recall_node
        state = {"messages": [HumanMessage(content="hello")], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_recall_node(state, _make_config())
    assert result == {"memories": []}


def test_recall_node_skips_search_when_spacy_model_missing():
    """mem0_recall_node does not trigger mem0's runtime spaCy download."""
    mock_client = MagicMock()
    with patch("app.agents.chat_agent.get_mem0_client", return_value=mock_client), \
         patch("app.agents.chat_agent._is_mem0_spacy_model_available", return_value=False):
        from app.agents.chat_agent import mem0_recall_node
        state = {"messages": [HumanMessage(content="hello")], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_recall_node(state, _make_config())
    assert result == {"memories": []}
    mock_client.search.assert_not_called()


def test_recall_node_no_human_message_returns_empty():
    """mem0_recall_node returns empty memories when no HumanMessage in state."""
    mock_client = MagicMock()
    with patch("app.agents.chat_agent.get_mem0_client", return_value=mock_client):
        from app.agents.chat_agent import mem0_recall_node
        state = {"messages": [], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_recall_node(state, _make_config())
    assert result == {"memories": []}
    mock_client.search.assert_not_called()


def test_store_node_spawns_background_thread():
    """mem0_store_node returns {} immediately and calls mem0 add in background."""
    stored = []
    mock_client = MagicMock()

    def fake_add(messages, user_id):
        stored.append((messages, user_id))

    mock_client.add.side_effect = fake_add

    with patch("app.agents.chat_agent.get_mem0_client", return_value=mock_client):
        from app.agents.chat_agent import mem0_store_node
        state = {
            "messages": [
                HumanMessage(content="看好BTC"),
                AIMessage(content="好的，BTC目前..."),
            ],
            "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": [],
        }
        result = mem0_store_node(state, _make_config())

    assert result == {}
    time.sleep(0.1)  # let daemon thread complete
    assert len(stored) == 1
    messages, user_id = stored[0]
    assert user_id == _USER_ID
    assert messages == [
        {"role": "user", "content": "看好BTC"},
        {"role": "assistant", "content": "好的，BTC目前..."},
    ]


def test_store_node_disabled_returns_empty():
    """mem0_store_node returns {} immediately when client is None."""
    with patch("app.agents.chat_agent.get_mem0_client", return_value=None):
        from app.agents.chat_agent import mem0_store_node
        state = {"messages": [HumanMessage(content="hi"), AIMessage(content="hey")], "user_profile": {}, "user_prefs": {}, "consecutive_tool_failures": 0, "memories": []}
        result = mem0_store_node(state, _make_config())
    assert result == {}


def test_build_prompt_includes_memories():
    """_build_prompt_from_state appends <memories> section when memories present."""
    from app.agents.chat_agent import _build_prompt_from_state
    base = "You are a helpful assistant."
    result = _build_prompt_from_state(base, {}, {}, memories=["用户看好BTC", "短线风格"])
    assert "<memories>" in result
    assert "用户看好BTC" in result
    assert "短线风格" in result


def test_build_prompt_no_memories_unchanged():
    """_build_prompt_from_state does not add <memories> section when list is empty."""
    from app.agents.chat_agent import _build_prompt_from_state
    base = "You are a helpful assistant."
    result = _build_prompt_from_state(base, {}, {}, memories=[])
    assert "<memories>" not in result
    assert result.startswith(base)
