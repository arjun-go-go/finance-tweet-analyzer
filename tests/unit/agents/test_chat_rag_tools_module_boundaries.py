from app.agents import chat_agent
from app.agents.chat.tools import rag_search


def test_rag_search_impls_live_in_dedicated_module():
    assert chat_agent._search_my_documents_impl is rag_search.search_my_documents_impl
    assert chat_agent._search_public_signals_impl is rag_search.search_public_signals_impl
