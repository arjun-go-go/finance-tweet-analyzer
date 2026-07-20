from __future__ import annotations

import threading

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger

from app.agents.chat.nodes.context import get_authenticated_user_id
from app.core.config import settings
from app.memory.mem0_client import get_mem0_client


def is_mem0_spacy_model_available() -> bool:
    try:
        import spacy  # type: ignore

        spacy.load("en_core_web_sm")
        return True
    except (Exception, SystemExit):
        return False


def mem0_recall_node_impl(
    state: dict,
    config: RunnableConfig,
    *,
    get_client=get_mem0_client,
    settings_obj=settings,
    spacy_checker=is_mem0_spacy_model_available,
) -> dict:
    """Recall cross-session memories for the latest human message."""
    client = get_client()
    if client is None:
        return {"memories": []}

    messages = state.get("messages") or []
    query = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        None,
    )
    if not query:
        return {"memories": []}

    if not spacy_checker():
        logger.warning("[mem0] recall skipped: spaCy model en_core_web_sm is not installed")
        return {"memories": []}

    user_id = get_authenticated_user_id(config)
    try:
        results = client.search(query, filters={"user_id": user_id}, top_k=settings_obj.mem0_top_k)
        memories = [r["memory"] for r in (results.get("results") or [])]
        logger.debug("[mem0] recalled {} memories for user={}", len(memories), user_id)
        return {"memories": memories}
    except (Exception, SystemExit) as e:
        logger.warning("[mem0] recall failed: {}", e)
        return {"memories": []}


def mem0_store_node_impl(
    state: dict,
    config: RunnableConfig,
    *,
    get_client=get_mem0_client,
) -> dict:
    """Store the latest human/assistant turn in mem0 without blocking response flow."""
    client = get_client()
    if client is None:
        return {}

    messages = state.get("messages") or []
    user_id = get_authenticated_user_id(config)

    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    last_ai = next(
        (m for m in reversed(messages)
         if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        None,
    )
    if not last_human or not last_ai:
        return {}

    mem0_messages = [
        {"role": "user", "content": last_human.content},
        {"role": "assistant", "content": last_ai.content},
    ]

    def _store():
        try:
            client.add(mem0_messages, user_id=user_id)
            logger.debug("[mem0] stored turn for user={}", user_id)
        except (Exception, SystemExit) as e:
            logger.warning("[mem0] store failed: {}", e)

    threading.Thread(target=_store, daemon=True).start()
    return {}


def extract_preferences_node_impl(state: dict, config: RunnableConfig) -> dict:
    """Extract implicit user preferences in the background."""
    from app.memory.preferences import extract_preferences_background

    messages = state["messages"]
    user_id = get_authenticated_user_id(config)
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            extract_preferences_background(msg.content, user_id=user_id)
            break
    return {}
