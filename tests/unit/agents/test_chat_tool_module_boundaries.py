from app.agents import chat_agent
from app.agents.chat.tools import ingestion, reports


def test_ingestion_external_api_impls_live_in_dedicated_module():
    assert chat_agent._fetch_profile_impl is ingestion.fetch_profile_impl
    assert chat_agent._fetch_tweets_impl is ingestion.fetch_tweets_impl


def test_report_execution_impl_lives_in_dedicated_module():
    assert chat_agent._generate_tracking_report_impl is reports.generate_tracking_report_impl
