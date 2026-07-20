import pytest

from app.agents.chat.routing import classify_tool_route


@pytest.mark.parametrize(
    ("message", "expected_route", "must_allow", "must_block"),
    [
        (
            "我关注了哪些博主？",
            "read_only",
            {"query_database", "list_my_followed_bloggers"},
            {"generate_tracking_report", "fetch_and_save_tweets", "confirm_tweet_analysis"},
        ),
        (
            "帮我看看 BTC 最近消息，不要生成报告",
            "read_only",
            {"query_database", "search_public_signals"},
            {"generate_tracking_report", "fetch_and_save_tweets", "confirm_tweet_analysis"},
        ),
        (
            "生成一份 TSLA 日报",
            "report",
            {"generate_tracking_report"},
            {"fetch_and_save_tweets", "confirm_tweet_analysis"},
        ),
        (
            "写一个 BTC 周报",
            "report",
            {"generate_tracking_report"},
            {"fetch_and_save_tweets", "confirm_tweet_analysis"},
        ),
        (
            "开始分析我关注博主的待处理推文",
            "analysis",
            {"preview_tweet_analysis", "confirm_tweet_analysis"},
            {"generate_tracking_report", "fetch_and_save_tweets"},
        ),
        (
            "请提交这个分析任务",
            "analysis",
            {"preview_tweet_analysis", "confirm_tweet_analysis"},
            {"generate_tracking_report", "fetch_and_save_tweets"},
        ),
        (
            "同步 qinbafrank 的推文",
            "ingest",
            {"fetch_and_save_profile", "fetch_and_save_tweets"},
            {"generate_tracking_report", "confirm_tweet_analysis"},
        ),
        (
            "拉取 qinbafrank 最近动态",
            "ingest",
            {"fetch_and_save_profile", "fetch_and_save_tweets"},
            {"generate_tracking_report", "confirm_tweet_analysis"},
        ),
    ],
)
def test_tool_routing_golden_matrix(message, expected_route, must_allow, must_block):
    route, allowed_tools = classify_tool_route(message)

    assert route == expected_route
    assert must_allow.issubset(set(allowed_tools))
    assert must_block.isdisjoint(set(allowed_tools))
