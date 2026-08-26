from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


READ_ONLY_TOOL_NAMES = [
    "get_blogger_overview",
    "get_blogger_recent_analysis",
    "get_blogger_predictions",
    "get_ticker_predictions",
    "get_prediction_review_summary",
    "query_database",
    "search_public_signals",
    "search_my_documents",
    "list_my_tracked_tickers",
    "list_my_followed_bloggers",
]
INGEST_TOOL_NAMES = ["fetch_and_save_profile", "fetch_and_save_tweets"]
BLOGGER_OVERVIEW_TOOL_NAMES = ["get_blogger_overview"]
BLOGGER_ANALYSIS_TOOL_NAMES = ["get_blogger_recent_analysis"]
BLOGGER_PREDICTION_TOOL_NAMES = ["get_blogger_predictions"]
TICKER_PREDICTION_TOOL_NAMES = ["get_ticker_predictions"]
PREDICTION_REVIEW_TOOL_NAMES = ["get_prediction_review_summary"]
FOLLOW_TOOL_NAMES = ["set_blogger_follow"]
INGEST_PROFILE_TOOL_NAMES = ["fetch_and_save_profile"]
INGEST_TWEET_TOOL_NAMES = ["fetch_and_save_tweets"]
ANALYSIS_TOOL_NAMES = ["preview_tweet_analysis", "confirm_tweet_analysis"]
ANALYSIS_PREVIEW_TOOL_NAMES = ["preview_tweet_analysis"]
ANALYSIS_CONFIRM_TOOL_NAMES = ["confirm_tweet_analysis"]
REPORT_TOOL_NAMES = ["generate_tracking_report"]
PUBLIC_SIGNAL_TOOL_NAMES = ["search_public_signals"]
PRIVATE_DOCUMENT_TOOL_NAMES = ["search_my_documents"]
DATABASE_QUERY_TOOL_NAMES = ["query_database"]
FOLLOWED_BLOGGER_TOOL_NAMES = ["list_my_followed_bloggers"]
TRACKED_TICKER_TOOL_NAMES = ["list_my_tracked_tickers"]


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


def recent_context_text(state: dict, limit: int = 6) -> str:
    """Return recent assistant/tool context used only for follow-up intent routing."""
    messages = state.get("messages") or []
    parts = []
    for message in messages[-limit:]:
        if isinstance(message, (AIMessage, ToolMessage)) and isinstance(message.content, str):
            parts.append(message.content)
    return "\n".join(parts)


def classify_tool_route(text: str, context_text: str = "") -> tuple[str, list[str]]:
    """Classify user intent into the narrowest safe tool set.

    Production rule: default to read-only. Open high-cost/write-capable tools only
    when the user's wording clearly asks for that operation.
    """
    normalized = text.lower().strip()
    normalized_context = context_text.lower()

    handle_match = re.search(r"@([A-Za-z0-9_]{1,15})", text)
    plain_handle_match = re.search(r"(?:博主|kol)\s+([A-Za-z0-9_]{1,15})", text, re.IGNORECASE)
    has_handle = bool(handle_match or plain_handle_match)
    if any(word in normalized for word in ("预测复核概况", "预测复核统计", "待复核预测", "prediction review")):
        return "prediction_review", PREDICTION_REVIEW_TOOL_NAMES
    if has_handle and any(word in normalized for word in ("最近分析", "分析结果", "分析观点", "重要观点", "recent analysis")):
        return "blogger_analysis", BLOGGER_ANALYSIS_TOOL_NAMES
    if has_handle and any(word in normalized for word in ("预测", "命中", "胜率", "predictions")):
        return "blogger_predictions", BLOGGER_PREDICTION_TOOL_NAMES
    if (
        has_handle
        and any(word in normalized for word in ("资料", "简介", "粉丝", "可信度", "主页", "档案", "profile"))
        and not any(word in normalized for word in ("更新", "获取最新", "同步"))
    ):
        return "blogger_overview", BLOGGER_OVERVIEW_TOOL_NAMES
    if not has_handle and any(word in normalized for word in ("预测", "prediction")) and re.search(r"(?:\$)?[A-Z]{2,10}\b", text):
        return "ticker_predictions", TICKER_PREDICTION_TOOL_NAMES

    if any(word in normalized for word in ("我关注的博主", "关注了哪些博主", "我的博主", "关注列表")):
        return "followed_bloggers", FOLLOWED_BLOGGER_TOOL_NAMES
    if any(word in normalized for word in ("关注标的", "订阅标的", "我的标的", "watchlist")):
        return "tracked_tickers", TRACKED_TICKER_TOOL_NAMES
    if any(word in normalized for word in ("私人文档", "私人资料", "我上传的", "我的文档", "文档里")):
        return "private_documents", PRIVATE_DOCUMENT_TOOL_NAMES

    if re.search(r"(?:取消关注|不再关注|unfollow)\s*@?[A-Za-z0-9_]{1,15}", normalized):
        return "follow", FOLLOW_TOOL_NAMES
    if re.search(r"(?:正式关注|加入.*关注列表|关注博主|(?:^|\s)关注|follow)\s*@?[A-Za-z0-9_]{1,15}", normalized):
        return "follow", FOLLOW_TOOL_NAMES

    confirmation_words = ("确认", "好的", "可以", "执行", "开始", "go ahead", "confirm")
    confirmation_phrases = (
        "确认提交",
        "立即执行",
        "是的",
        "继续",
        "没问题",
        "提交吧",
    )
    analysis_confirmation_markers = (
        "确认id",
        "confirm_tweet_analysis",
        "是否确认提交后台分析",
        "请用户确认是否执行分析",
    )
    if (
        (normalized in confirmation_words or any(phrase in normalized for phrase in confirmation_phrases))
        and any(marker in normalized_context for marker in analysis_confirmation_markers)
    ):
        return "analysis", ANALYSIS_CONFIRM_TOOL_NAMES

    negation_words = ("不要", "不用", "别", "无需", "不需要", "不要生成", "no report", "don't")
    report_words = ("报告", "日报", "周报", "跟踪报告", "生成报告", "report")
    report_actions = ("生成", "写", "做", "创建", "出", "给我", "generate", "create", "write")
    if any(neg in normalized for neg in negation_words) and any(word in normalized for word in report_words):
        return "public_signals", PUBLIC_SIGNAL_TOOL_NAMES

    ingest_negations = (
        "不要抓取",
        "不用抓取",
        "别抓取",
        "无需抓取",
        "不要采集",
        "不用采集",
        "不要同步",
        "不用同步",
        "don't fetch",
        "do not fetch",
    )
    if any(phrase in normalized for phrase in ingest_negations):
        return "public_signals", PUBLIC_SIGNAL_TOOL_NAMES

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
        "分析待处理",
        "创建推文分析",
        "有多少待分析",
        "tweet analysis",
        "分析所有 pending",
        "准备执行推文分析",
        "分析新采集",
        "深度分析推文",
        "分析任务预览",
        "confirm analysis",
        "preview analysis",
    )
    if any(word in normalized for word in analysis_words):
        if "确认分析" in normalized or "confirm analysis" in normalized:
            return "analysis", ANALYSIS_CONFIRM_TOOL_NAMES
        return "analysis", ANALYSIS_PREVIEW_TOOL_NAMES

    profile_words = (
        "更新资料",
        "获取资料",
        "最新资料",
        "同步博主",
        "profile",
    )
    if any(word in normalized for word in profile_words):
        return "ingest", INGEST_PROFILE_TOOL_NAMES

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
        "最近发了什么",
    )
    if any(word in normalized for word in ingest_words):
        return "ingest", INGEST_TWEET_TOOL_NAMES

    if any(word in normalized for word in (
        "博主排行", "粉丝排名", "历史统计", "总共有多少", "数据库", "跨博主统计",
    )):
        return "database_query", DATABASE_QUERY_TOOL_NAMES
    if any(word in normalized for word in (
        "观点", "怎么看", "市场情绪", "风险信号", "最近消息", "相关推文", "twitter", "推文",
    )) or re.search(r"(?:\$)?[A-Z]{2,10}\b", text):
        return "public_signals", PUBLIC_SIGNAL_TOOL_NAMES
    return "conversation", []


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
