"""Deterministic target matching shared by report and chat retrieval."""

from __future__ import annotations

import re


def target_tokens(ticker: str) -> set[str]:
    normalized = ticker.strip().lstrip("$").upper()
    tokens = {normalized}
    if "." in normalized:
        tokens.add(normalized.split(".", 1)[0])
    if normalized == "XAU":
        tokens.update({"GOLD", "黄金"})
    elif normalized == "WTI":
        tokens.update({"USOIL", "原油"})
    return {token for token in tokens if token}


def contains_target(value: object, tokens: set[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(contains_target(item, tokens) for item in value)

    text = str(value).upper()
    for token in tokens:
        if token.isascii():
            if re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", text):
                return True
        elif token in text:
            return True
    return False


def matches_target(item: dict, ticker: str) -> bool:
    tokens = target_tokens(ticker)
    metadata = item.get("metadata") or {}
    for key in ("ticker", "tickers", "symbol", "symbols", "provider_symbol"):
        if contains_target(metadata.get(key), tokens):
            return True
    return contains_target(item.get("content"), tokens)


def infer_ticker(text: str) -> str:
    """Infer only explicit ticker-like tokens; return empty on ambiguity."""
    dollar_match = re.search(r"\$([A-Za-z]{2,10}|\d{5,6}(?:\.(?:SH|SZ|HK))?)\b", text)
    if dollar_match:
        return dollar_match.group(1).upper()
    candidates = re.findall(
        r"(?<![A-Za-z0-9])([A-Z]{2,10}|\d{5,6}(?:\.(?:SH|SZ|HK))?)(?![A-Za-z0-9])",
        text,
    )
    ignored = {"AI", "KOL", "PDF", "URL", "IPO", "ETF", "USD", "RAG"}
    filtered = [candidate.upper() for candidate in candidates if candidate.upper() not in ignored]
    return filtered[0] if len(set(filtered)) == 1 else ""
