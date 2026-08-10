from app.agents.chat.graph import build_chat_agent


_chat_agent = None


def get_chat_agent():
    global _chat_agent
    if _chat_agent is None:
        try:
            from app.memory.checkpointer import get_checkpointer

            _chat_agent = build_chat_agent(checkpointer=get_checkpointer())
        except RuntimeError:
            _chat_agent = build_chat_agent()
    return _chat_agent
