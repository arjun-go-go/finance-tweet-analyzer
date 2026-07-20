from __future__ import annotations

from langchain_core.messages import HumanMessage


READ_ONLY_TOOL_NAMES = [
    "query_database",
    "search_public_signals",
    "search_my_documents",
    "list_my_tracked_tickers",
    "list_my_followed_bloggers",
]
INGEST_TOOL_NAMES = READ_ONLY_TOOL_NAMES + [
    "fetch_and_save_profile",
    "fetch_and_save_tweets",
]
ANALYSIS_TOOL_NAMES = READ_ONLY_TOOL_NAMES + [
    "preview_tweet_analysis",
    "confirm_tweet_analysis",
]
REPORT_TOOL_NAMES = READ_ONLY_TOOL_NAMES + [
    "generate_tracking_report",
]


def latest_human_text(state: dict) -> str:
    messages = state.get("messages") or []
    return next(
        (
            m.content
            for m in reversed(messages)
            if isinstance(m, HumanMessage) and isinstance(m.content, str)
        ),
        "",
    )


def classify_tool_route(text: str) -> tuple[str, list[str]]:
    normalized = text.lower()
    if any(k in normalized for k in ("报告", "周报", "跟踪报告", "生成报告", "report")):
        return "report", REPORT_TOOL_NAMES
    if any(k in normalized for k in ("待分析", "预览分析", "确认分析", "分析任务", "执行分析", "confirm analysis", "preview analysis")):
        return "analysis", ANALYSIS_TOOL_NAMES
    if any(k in normalized for k in ("抓取", "采集", "获取最新", "拉取", "同步推文", "fetch", "crawl", "最新推文")):
        return "ingest", INGEST_TOOL_NAMES
    return "read_only", READ_ONLY_TOOL_NAMES


def has_explicit_report_confirmation(message: str, ticker: str) -> bool:
    text = message.lower()
    ticker_text = ticker.lower()
    action_words = ("确认", "立即", "开始", "执行", "生成", "创建", "确认生成", "go ahead", "confirm")
    report_words = ("报告", "周报", "跟踪报告", "report")
    return (
        ticker_text in text
        and any(word in text for word in action_words)
        and any(word in text for word in report_words)
    )


def has_explicit_ingest_confirmation(
    message: str,
    *,
    handle: str,
    target_words: tuple[str, ...],
) -> bool:
    text = message.lower()
    handle_text = handle.lower().lstrip("@")
    action_words = ("确认", "立即", "开始", "执行", "获取", "抓取", "采集", "同步", "拉取", "fetch", "crawl", "confirm")
    return (
        handle_text in text
        and any(word in text for word in action_words)
        and any(word.lower() in text for word in target_words)
    )
