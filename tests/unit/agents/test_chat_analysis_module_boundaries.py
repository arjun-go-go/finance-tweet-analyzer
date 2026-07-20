from app.agents import chat_agent
from app.agents.chat.tools import analysis_jobs


def test_analysis_job_impls_live_in_dedicated_module():
    assert chat_agent._preview_tweet_analysis_impl is analysis_jobs.preview_tweet_analysis_impl
    assert chat_agent._confirm_tweet_analysis_impl is analysis_jobs.confirm_tweet_analysis_impl
