import pytest

from app.agents.chat.routing import classify_tool_route


@pytest.mark.parametrize(
    ("message", "expected_route", "allowed_tool"),
    [
        ("你好", "conversation", None),
        ("我关注了哪些博主？", "followed_bloggers", "list_my_followed_bloggers"),
        ("查看我的 watchlist", "tracked_tickers", "list_my_tracked_tickers"),
        ("关注博主 @qinbafrank", "follow", "set_blogger_follow"),
        ("列出博主粉丝排名", "database_query", "query_database"),
        ("市场里的博主怎么看 BTC？", "public_signals", "search_public_signals"),
        ("同步 qinbafrank 的推文", "ingest", "fetch_and_save_tweets"),
        ("获取 profile", "ingest", "fetch_and_save_profile"),
        ("@qinbafrank 最近分析", "blogger_analysis", "get_blogger_recent_analysis"),
        ("@qinbafrank 的预测", "blogger_predictions", "get_blogger_predictions"),
        ("TSLA predictions", "ticker_predictions", "get_ticker_predictions"),
        ("prediction review", "prediction_review", "get_prediction_review_summary"),
    ],
)
def test_tool_routing_golden_matrix(message, expected_route, allowed_tool):
    route, tools = classify_tool_route(message)
    assert route == expected_route
    if allowed_tool is None:
        assert tools == []
    else:
        assert tools == [allowed_tool]


def test_retired_product_tools_are_never_exposed():
    retired = {
        "search_my_documents",
        "generate_tracking_report",
        "preview_tweet_analysis",
        "confirm_tweet_analysis",
    }
    for message in ("生成 TSLA 报告", "搜索我的文档", "开始批量分析"):
        _, tools = classify_tool_route(message)
        assert retired.isdisjoint(tools)
