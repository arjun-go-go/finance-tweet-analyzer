# Harness

Approved by the user's P2 execution request on 2026-08-10.

- Entrypoint: `scripts/evaluate_chat_agent_p2.py selection`.
- Preserved production components: `chat/system`, `get_report_llm`, route gate,
  and the registered LangChain tool schemas.
- The harness binds tools and records the first model tool call, but never invokes it.
- No memory, checkpointer, database, Redis, ES, or Milvus dependency is used.
