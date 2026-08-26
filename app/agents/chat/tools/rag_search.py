from __future__ import annotations

from uuid import UUID

from app.agents.chat.tool_results import tool_ok
from app.rag.hybrid_retrieval import (
    build_retrieval_intent,
    evidence_from_items,
    hybrid_retrieve,
)


def _render_evidence(items: list[dict]) -> str:
    lines = []
    for item in items:
        header = f"[{item['evidence_id']}] {item['source_type']}"
        if item.get("author"):
            header += f" | @{item['author']}"
        if item.get("published_at"):
            header += f" | {str(item['published_at'])[:19]}"
        if item.get("ticker"):
            header += f" | {item['ticker']}"
        lines.append(f"{header}\n{item['content']}")
    return "\n\n".join(lines)


def search_my_documents_impl(user_id: UUID, query: str, ticker: str = "") -> str:
    """Search private documents through the shared vector + ES hybrid pipeline."""
    intent = build_retrieval_intent(query, ticker=ticker)
    result = hybrid_retrieve(
        intent,
        user_id=user_id,
        query=query,
        source_scope=["private_documents"],
    )
    evidence = evidence_from_items(result["reranked"])
    if not evidence:
        return "未找到相关文档内容。"
    return tool_ok(
        _render_evidence(evidence),
        data={"evidence": evidence, "ticker": "" if intent.ticker == "UNKNOWN" else intent.ticker},
    )


def search_public_signals_impl(
    query: str,
    source_type: str = "analysis",
    blogger: str = "",
    user_id: UUID | None = None,
) -> str:
    """Search public signals through the shared Milvus + ES + PG pipeline."""
    if source_type not in ("analysis", "tweet"):
        return "参数错误：source_type 必须是 'analysis' 或 'tweet'。"

    intent = build_retrieval_intent(query, blogger=blogger)
    result = hybrid_retrieve(
        intent,
        user_id=user_id,
        query=query,
        source_scope=[source_type],
    )
    evidence = evidence_from_items(result["reranked"])
    if not evidence:
        blogger_hint = f" 博主 @{blogger}" if blogger else ""
        target = "" if intent.ticker == "UNKNOWN" else intent.ticker
        target_hint = f"且直接属于 {target}" if target else ""
        return f"未找到与“{query}”相关{target_hint}的 {source_type} 内容{blogger_hint}。"

    return tool_ok(
        _render_evidence(evidence),
        data={
            "evidence": evidence,
            "ticker": "" if intent.ticker == "UNKNOWN" else intent.ticker,
            "retrieval_paths": list(result["paths"]),
        },
    )
