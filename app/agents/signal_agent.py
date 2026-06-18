"""信号 Agent —— 单条推文独立分析（早期版本/工具调用入口）。

与 analysis_agent 的区别：
    - signal_agent: 同步、单条调用，无 blogger_context 注入，用于 chat_agent 工具链
    - analysis_agent: 异步批量并发，注入博主画像上下文，用于 Supervisor 管道

本模块作为独立入口保留，供不经过 Supervisor 的场景使用
（如手动调试、单条推文快速分析等）。
"""
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.llm import get_signal_llm
from app.prompts import get_chat_prompt
from app.schemas.signal import TweetAnalysis

# ============================================================
# 推文分析 Prompt —— 已迁移至 prompts/signal.yaml
# ------------------------------------------------------------
# Prompt 模板通过 get_chat_prompt("signal/system_prompt") 加载，
# 运行时变量 author_handle / content 由 Jinja2 渲染。
# ============================================================


def _to_lc_messages(msg_dicts: list[dict]) -> list:
    """将 get_chat_prompt 返回的 dict 列表转换为 LangChain Message 对象。"""
    _ROLE_MAP = {"system": SystemMessage, "human": HumanMessage}
    return [_ROLE_MAP[m["role"]](content=m["content"]) for m in msg_dicts]


def analyze_tweet(content: str, author_handle: str) -> dict:
    """同步分析单条推文，返回结构化字典。

    适用场景：chat_agent 工具调用 / 手动调试 / 实时单条分析。
    不注入 blogger_context（无批量上下文优化）。
    """
    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(TweetAnalysis)
    messages = _to_lc_messages(get_chat_prompt("signal/system_prompt", author_handle=author_handle, content=content))
    result = structured_llm.invoke(messages)
    return result.model_dump()
