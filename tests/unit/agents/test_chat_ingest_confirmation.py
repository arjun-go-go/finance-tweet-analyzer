import json
from unittest.mock import patch

from app.agents import chat_agent


def test_fetch_profile_requires_explicit_confirmation():
    with patch("app.agents.chat_agent._fetch_profile_impl") as fetch_profile:
        result = chat_agent.fetch_and_save_profile.invoke(
            {"blogger_handle": "elonmusk"},
            config={"metadata": {"current_message": "看看 elonmusk 的资料"}},
        )

    fetch_profile.assert_not_called()
    envelope = json.loads(result)
    assert envelope["ok"] is False
    assert envelope["error_code"] == "CONFIRMATION_REQUIRED"
    assert "确认获取 elonmusk 资料" in envelope["message"]


def test_fetch_tweets_requires_explicit_confirmation():
    with patch("app.agents.chat_agent._fetch_tweets_impl") as fetch_tweets:
        result = chat_agent.fetch_and_save_tweets.invoke(
            {"blogger_handle": "elonmusk", "pages": 1},
            config={"metadata": {"current_message": "看看 elonmusk 最新推文"}},
        )

    fetch_tweets.assert_not_called()
    envelope = json.loads(result)
    assert envelope["ok"] is False
    assert envelope["error_code"] == "CONFIRMATION_REQUIRED"
    assert "确认抓取 elonmusk 最新推文" in envelope["message"]


def test_ingest_confirmation_helper_allows_profile_confirmation():
    assert chat_agent._has_explicit_ingest_confirmation(
        "确认获取 elonmusk 资料",
        handle="elonmusk",
        target_words=("资料", "主页", "profile"),
    )


def test_ingest_confirmation_helper_allows_tweets_confirmation():
    assert chat_agent._has_explicit_ingest_confirmation(
        "确认抓取 elonmusk 最新推文",
        handle="elonmusk",
        target_words=("推文", "tweets"),
    )
