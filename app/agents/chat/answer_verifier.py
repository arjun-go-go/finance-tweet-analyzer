"""Deterministic Claim–Evidence checks for final chat answers."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.chat.tool_results import parse_tool_envelope


def _current_turn_tool_envelopes(messages: list) -> list[tuple[str, dict]]:
    results: list[tuple[str, dict]] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
            continue
        envelope = parse_tool_envelope(message.content)
        if envelope and envelope.get("ok") is True:
            results.append((message.name or "unknown_tool", envelope))
    return list(reversed(results))


def verify_grounded_answer(content: str, messages: list) -> tuple[str, dict]:
    """Reject fabricated evidence references and ungrounded retrieval summaries."""
    envelopes = _current_turn_tool_envelopes(messages)
    evidence_ids: set[str] = set()
    tool_names: set[str] = set()
    for tool_name, envelope in envelopes:
        tool_names.add(tool_name)
        data = envelope.get("data") or {}
        for item in data.get("evidence") or []:
            evidence_id = str(item.get("evidence_id") or "")
            if evidence_id:
                evidence_ids.add(evidence_id)

    cited_evidence = set(re.findall(r"\[(E[A-Z]+(?:-[A-F0-9]+)?|E\d+)\]", content))
    cited_tools = set(re.findall(r"【tool:([^】]+)】", content))
    invalid_evidence = cited_evidence - evidence_ids
    invalid_tools = cited_tools - tool_names

    if invalid_evidence or invalid_tools:
        return (
            "回答草稿包含无法对应到本轮工具结果的引用，已停止输出。当前证据不足，请重新检索后再试。",
            {
                "status": "rejected",
                "invalid_evidence": sorted(invalid_evidence),
                "invalid_tools": sorted(invalid_tools),
            },
        )

    if evidence_ids and not cited_evidence:
        return (
            "本轮已检索到证据，但回答草稿未建立具体 Claim–Evidence 引用，已停止输出。当前证据不足，请重新提问或查看证据板。",
            {"status": "rejected", "reason": "missing_evidence_reference"},
        )

    return content, {
        "status": "passed",
        "evidence_count": len(evidence_ids),
        "cited_evidence_count": len(cited_evidence),
        "tool_count": len(tool_names),
    }


def grounding_repair_prompt(content: str, messages: list) -> str | None:
    """Build a compact, evidence-only rewrite prompt after citation verification fails."""
    evidence_lines: list[str] = []
    for _, envelope in _current_turn_tool_envelopes(messages):
        for item in (envelope.get("data") or {}).get("evidence") or []:
            evidence_id = str(item.get("evidence_id") or "")
            if not evidence_id:
                continue
            excerpt = str(item.get("content") or item.get("excerpt") or "")[:600]
            evidence_lines.append(
                f"[{evidence_id}] {item.get('source_type', '')} | {item.get('ticker', '')} | "
                f"{item.get('author', '')}\n{excerpt}"
            )
    if not evidence_lines:
        return None
    return (
        "请重写下面的回答草稿。只能使用提供的证据，不得补充外部事实；每个事实或判断句末必须引用"
        "对应证据编号，例如 [EA1]。删除所有不存在的编号和【tool:...】引用。若证据冲突，要明确说明。"
        "只输出给用户的最终中文回答。\n\n"
        f"回答草稿：\n{content}\n\n可用证据：\n" + "\n\n".join(evidence_lines[:12])
    )
