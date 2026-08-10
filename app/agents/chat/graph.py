import importlib.util

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agents.chat.nodes.agent import agent_node_impl, build_prompt_from_state
from app.agents.chat.nodes.context import init_context_node_impl
from app.agents.chat.nodes.memory import (
    extract_preferences_node_impl,
    mem0_recall_node_impl,
    mem0_store_node_impl,
)
from app.agents.chat.nodes.tool_executor import route_tools_node, tools_node
from app.agents.chat.routing import READ_ONLY_TOOL_NAMES
from app.agents.chat.state import AgentState
from app.agents.chat.tools.registry import TOOLS_BY_NAME
from app.agents.llm import get_report_llm
from app.core.config import settings
from app.memory.mem0_client import get_mem0_client
from app.prompts import get_prompt


def estimate_tokens(messages: list) -> int:
    total_chars = sum(
        len(message.content)
        if hasattr(message, "content") and isinstance(message.content, str)
        else 100
        for message in messages
    )
    return total_chars // 4


def is_mem0_spacy_model_available() -> bool:
    return importlib.util.find_spec("en_core_web_sm") is not None


def init_context_node(state: AgentState, config: RunnableConfig) -> dict:
    return init_context_node_impl(state, config)


def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    return agent_node_impl(
        state,
        config,
        tools_by_name=TOOLS_BY_NAME,
        default_tool_names=READ_ONLY_TOOL_NAMES,
        estimate_tokens=estimate_tokens,
        settings_obj=settings,
        get_prompt_fn=get_prompt,
        get_llm=get_report_llm,
        build_prompt=build_prompt_from_state,
    )


def mem0_recall_node(state: AgentState, config: RunnableConfig) -> dict:
    return mem0_recall_node_impl(
        state,
        config,
        get_client=get_mem0_client,
        settings_obj=settings,
        spacy_checker=is_mem0_spacy_model_available,
    )


def mem0_store_node(state: AgentState, config: RunnableConfig) -> dict:
    return mem0_store_node_impl(state, config, get_client=get_mem0_client)


def extract_preferences_node(state: AgentState, config: RunnableConfig) -> dict:
    return extract_preferences_node_impl(state, config)


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "extract_preferences"


def build_chat_agent(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("init", init_context_node)
    graph.add_node("mem0_recall", mem0_recall_node)
    graph.add_node("route_tools", route_tools_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("extract_preferences", extract_preferences_node)
    graph.add_node("mem0_store", mem0_store_node)

    graph.add_edge(START, "init")
    graph.add_edge("init", "mem0_recall")
    graph.add_edge("mem0_recall", "route_tools")
    graph.add_edge("route_tools", "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        ["tools", "extract_preferences"],
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("extract_preferences", "mem0_store")
    graph.add_edge("mem0_store", END)
    return graph.compile(checkpointer=checkpointer)
