from app.agents import chat_agent
from app.agents.chat.nodes import context as context_nodes
from app.agents.chat.nodes import memory as memory_nodes


def test_context_node_impls_live_in_dedicated_modules():
    assert chat_agent._init_context_node_impl is context_nodes.init_context_node_impl
    assert chat_agent._mem0_recall_node_impl is memory_nodes.mem0_recall_node_impl
    assert chat_agent._mem0_store_node_impl is memory_nodes.mem0_store_node_impl
    assert chat_agent._extract_preferences_node_impl is memory_nodes.extract_preferences_node_impl
