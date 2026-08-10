# Chat Agent P2 evaluation

P2 contains two independent, read-only capabilities:

1. Top-1 tool selection using the production prompt, production model factory,
   production tool schemas, and deterministic route gate. No tool is executed.
2. Evidence-grounded answer generation using frozen successful, empty, and error
   tool results. The verifier checks required facts, citations, and abstention.

The selection dataset expands deterministic business templates to more than 200
cases. Run a smoke sample first, then the full suite:

```bash
uv run python scripts/evaluate_chat_agent_p2.py selection --limit 12 --concurrency 4
uv run python scripts/evaluate_chat_agent_p2.py selection --concurrency 8
uv run python scripts/evaluate_chat_agent_p2.py evidence --concurrency 4
```

These evaluations call OpenRouter and therefore incur model usage. They never
execute application tools or write application databases.
