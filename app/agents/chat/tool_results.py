from __future__ import annotations

import json


def truncate_result(text: str, max_chars: int) -> str:
    """Truncate tool output to prevent context overflow."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...(结果已截断，原始长度 {len(text)} 字符)"


def tool_ok(message: str, *, max_chars: int = 3000, data: dict | None = None) -> str:
    """Return a structured successful tool result."""
    return json.dumps(
        {
            "ok": True,
            "message": truncate_result(message, max_chars),
            "data": data or {},
        },
        ensure_ascii=False,
    )


def tool_error(
    error_code: str,
    message: str,
    *,
    max_chars: int = 3000,
    retryable: bool = False,
) -> str:
    """Return a structured failed tool result."""
    return json.dumps(
        {
            "ok": False,
            "error_code": error_code,
            "message": truncate_result(message, max_chars),
            "retryable": retryable,
        },
        ensure_ascii=False,
    )


def parse_tool_envelope(content: str) -> dict | None:
    """Parse a structured tool result envelope, returning None for legacy text."""
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or "ok" not in parsed:
        return None
    return parsed
