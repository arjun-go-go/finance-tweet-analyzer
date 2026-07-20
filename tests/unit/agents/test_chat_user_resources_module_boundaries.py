from app.agents import chat_agent
from app.agents.chat.tools import user_resources


def test_user_resource_impls_live_in_dedicated_module():
    assert chat_agent._list_my_tracked_tickers_impl is user_resources.list_my_tracked_tickers_impl
    assert chat_agent._list_my_followed_bloggers_impl is user_resources.list_my_followed_bloggers_impl
