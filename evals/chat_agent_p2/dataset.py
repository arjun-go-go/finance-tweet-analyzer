"""Frozen business cases for the focused Twitter intelligence assistant."""

from __future__ import annotations


def selection_cases() -> list[dict]:
    return [
        {
            "id": "conversation-greeting",
            "category": "conversation",
            "input": "你好",
            "expected_tool": None,
        },
        {
            "id": "database-ranking",
            "category": "database",
            "input": "数据库里粉丝最多的博主是谁？",
            "expected_tool": "query_database",
        },
        {
            "id": "signals-btc",
            "category": "public_signals",
            "input": "市场里的博主怎么看 BTC？",
            "expected_tool": "search_public_signals",
        },
        {
            "id": "followed-bloggers",
            "category": "research_scope",
            "input": "我关注了哪些博主？",
            "expected_tool": "list_my_followed_bloggers",
        },
        {
            "id": "watchlist",
            "category": "research_scope",
            "input": "查看我的 watchlist",
            "expected_tool": "list_my_tracked_tickers",
        },
        {
            "id": "follow-action",
            "category": "follow",
            "input": "关注博主 @qinbafrank",
            "expected_tool": "set_blogger_follow",
        },
        {
            "id": "fetch-tweets",
            "category": "ingest",
            "input": "同步 qinbafrank 的推文",
            "expected_tool": "fetch_and_save_tweets",
        },
        {
            "id": "fetch-profile",
            "category": "ingest",
            "input": "获取 profile",
            "expected_tool": "fetch_and_save_profile",
        },
        {
            "id": "blogger-overview",
            "category": "blogger",
            "input": "@qinbafrank 的 profile",
            "expected_tool": "get_blogger_overview",
        },
        {
            "id": "blogger-analysis",
            "category": "blogger",
            "input": "@qinbafrank 最近分析",
            "expected_tool": "get_blogger_recent_analysis",
        },
        {
            "id": "blogger-predictions",
            "category": "prediction",
            "input": "@qinbafrank 的预测",
            "expected_tool": "get_blogger_predictions",
        },
        {
            "id": "ticker-predictions",
            "category": "prediction",
            "input": "TSLA predictions",
            "expected_tool": "get_ticker_predictions",
        },
    ]


def evidence_cases() -> list[dict]:
    success = [
        (
            "list_my_followed_bloggers",
            "我关注了哪些博主？",
            "你正式关注了 @qinbafrank。",
            "qinbafrank",
        ),
        (
            "list_my_tracked_tickers",
            "我关注哪些标的？",
            "你的关注列表包含 TSLA。",
            "TSLA",
        ),
        (
            "query_database",
            "数据库里有多少推文？",
            "数据库查询结果：共有 18 条推文。",
            "18",
        ),
        (
            "search_public_signals",
            "博主怎么看 BTC？",
            "[1] @qinbafrank 对 BTC 持看多观点。",
            "看多",
        ),
    ]
    cases = []
    for tool_name, question, result, fact in success:
        cases.append(
            {
                "id": f"evidence-success-{tool_name}",
                "kind": "success",
                "tool": tool_name,
                "input": question,
                "tool_result": result,
                "required_fact": fact,
                "required_citation": f"【tool:{tool_name}】",
            }
        )
        cases.append(
            {
                "id": f"evidence-error-{tool_name}",
                "kind": "error",
                "tool": tool_name,
                "input": question,
                "tool_error": "数据服务暂时不可用。",
                "forbidden_citation": f"【tool:{tool_name}】",
            }
        )
    return cases
