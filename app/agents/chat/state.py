from langgraph.graph import MessagesState


class AgentState(MessagesState):
    research_scope: dict
    consecutive_tool_failures: int = 0
    memories: list
    tool_route: str = "read_only"
    allowed_tool_names: list[str]
    answer_verification: dict
