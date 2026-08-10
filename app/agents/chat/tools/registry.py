from app.agents.chat.routing import (
    ANALYSIS_TOOL_NAMES,
    INGEST_TOOL_NAMES,
    READ_ONLY_TOOL_NAMES,
    REPORT_TOOL_NAMES,
)
from app.agents.chat.tools.definitions import tools


TOOLS_BY_NAME = {tool.name: tool for tool in tools}
