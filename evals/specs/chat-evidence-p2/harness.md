# Harness

Approved by the user's P2 execution request on 2026-08-10.

- Entrypoint: `scripts/evaluate_chat_agent_p2.py evidence`.
- Preserved production components: `agent_node_impl`, `chat/system`, model factory,
  evidence envelopes, and production tool schemas.
- Frozen ToolMessages are inserted after realistic AI tool calls with valid arguments.
- No application tool is executed.
