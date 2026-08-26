"""Compatibility exports for the modular Chat Agent implementation.

New code should import from ``app.agents.chat`` modules directly. The API keeps
using ``get_chat_agent`` from this module so existing callers remain stable.
"""

from app.agents.chat.graph import (
    agent_node,
    build_chat_agent,
    build_prompt_from_state as _build_prompt_from_state,
    estimate_tokens as _estimate_tokens,
    init_context_node,
    is_mem0_spacy_model_available as _is_mem0_spacy_model_available,
    mem0_recall_node,
    mem0_store_node,
    should_continue,
)
from app.agents.chat.nodes.agent import agent_node_impl as _agent_node_impl
from app.agents.chat.nodes.context import (
    get_authenticated_user_id as _get_authenticated_user_id,
    init_context_node_impl as _init_context_node_impl,
)
from app.agents.chat.nodes.memory import (
    mem0_recall_node_impl as _mem0_recall_node_impl,
    mem0_store_node_impl as _mem0_store_node_impl,
)
from app.agents.chat.nodes.tool_executor import (
    route_tools_node,
    tool_node as _tool_node,
    tools_node,
)
from app.agents.chat.routing import (
    INGEST_TOOL_NAMES as _INGEST_TOOL_NAMES,
    READ_ONLY_TOOL_NAMES as _READ_ONLY_TOOL_NAMES,
    classify_tool_route as _classify_tool_route,
    has_explicit_ingest_confirmation as _has_explicit_ingest_confirmation,
    latest_human_text as _latest_human_text,
)
from app.agents.chat.runtime import get_chat_agent
from app.agents.chat.state import AgentState
from app.agents.chat.tool_results import (
    parse_tool_envelope as _parse_tool_envelope,
    tool_error as _tool_error,
    tool_ok as _tool_ok,
)
from app.agents.chat.tools.definitions import (
    FetchProfileArgs,
    FetchTweetsArgs,
    _current_user_message,
    _fetch_profile_impl,
    _fetch_tweets_impl,
    _list_my_followed_bloggers_impl,
    _list_my_tracked_tickers_impl,
    _query_database_impl,
    _search_public_signals_impl,
    _truncate_result,
    fetch_and_save_profile,
    fetch_and_save_tweets,
    list_my_followed_bloggers,
    list_my_tracked_tickers,
    query_database,
    search_public_signals,
    tools,
)
from app.agents.chat.tools.registry import TOOLS_BY_NAME as _TOOLS_BY_NAME
from app.core.config import settings
from app.memory.mem0_client import get_mem0_client


__all__ = [
    "AgentState",
    "build_chat_agent",
    "get_chat_agent",
    "tools",
]
