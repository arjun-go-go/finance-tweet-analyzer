from app.agents import chat_agent
from app.agents.chat.nodes import agent as agent_nodes


def test_agent_node_impl_lives_in_dedicated_module():
    assert chat_agent._agent_node_impl is agent_nodes.agent_node_impl
