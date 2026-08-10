from langgraph.graph import MessagesState


class AgentState(MessagesState):
    user_profile: dict
    user_prefs: dict
    consecutive_tool_failures: int = 0
    memories: list
    tool_route: str = "read_only"
    allowed_tool_names: list[str]
