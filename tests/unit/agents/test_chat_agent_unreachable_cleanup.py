from pathlib import Path


CHAT_AGENT_SOURCE = Path("app/agents/chat_agent.py").read_text(encoding="utf-8")


def test_chat_agent_no_longer_contains_delegated_tool_legacy_calls():
    delegated_legacy_calls = [
        "create_and_run_report(",
        "UserDocumentRepository(",
        "get_vector_store()",
        "get_embedder()",
        "list_subscriptions(db, user_id)",
        "user_resource_service.list_followed_bloggers(",
        "create_analysis_job(",
        "list_confirmable_analysis_jobs_by_batch(",
    ]

    for call in delegated_legacy_calls:
        assert call not in CHAT_AGENT_SOURCE
