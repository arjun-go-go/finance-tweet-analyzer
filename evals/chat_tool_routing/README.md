# Chat tool routing evaluation

This frozen, read-only dataset checks the deterministic route boundary before the
LLM chooses a concrete tool. It verifies the expected route, required candidate
tools, and exclusion of write/high-cost tools.

Run from the repository root:

```bash
uv run python scripts/evaluate_chat_tool_routing.py
```

This evaluation does not execute tools or call OpenRouter. It measures candidate
tool gating, not final model top-1 tool choice or answer factuality.
