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
    """Classify user intent into the narrowest safe tool set.

    Production rule: default to read-only. Open high-cost/write-capable tools only
    when the user's wording clearly asks for that operation.
    """
    normalized = text.lower()

    negation_words = ("不要", "不用", "别", "无需", "不需要", "不要生成", "no report", "don't")
    report_words = ("报告", "日报", "周报", "跟踪报告", "生成报告", "report")
    report_actions = ("生成", "写", "做", "创建", "出", "给我", "generate", "create", "write")
    if any(neg in normalized for neg in negation_words) and any(word in normalized for word in report_words):
        return "read_only", READ_ONLY_TOOL_NAMES

    if any(word in normalized for word in report_words) and (
        "report" in normalized or any(action in normalized for action in report_actions)
    ):
        return "report", REPORT_TOOL_NAMES

    analysis_words = (
        "待分析",
        "待处理推文",
        "预览分析",
        "确认分析",
        "分析任务",
        "执行分析",
        "提交分析",
        "开始分析",
        "confirm analysis",
        "preview analysis",
    )
    if any(word in normalized for word in analysis_words):
        return "analysis", ANALYSIS_TOOL_NAMES

    ingest_words = (
        "抓取",
        "采集",
        "获取最新",
        "拉取",
        "同步推文",
        "同步",
        "fetch",
        "crawl",
        "最新推文",
    )
    if any(word in normalized for word in ingest_words):
        return "ingest", INGEST_TOOL_NAMES

    return "read_only", READ_ONLY_TOOL_NAMES


def has_explicit_report_confirmation(message: str, ticker: str) -> bool:
    text = message.lower()
    ticker_text = ticker.lower()
    action_words = ("确认", "立即", "开始", "执行", "生成", "创建", "确认生成", "go ahead", "confirm")
    report_words = ("报告", "日报", "周报", "跟踪报告", "report")
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
