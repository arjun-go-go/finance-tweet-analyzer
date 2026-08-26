"""Durable deep-research workflow over the project's existing evidence sources."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agents.llm import get_report_llm
from app.rag.hybrid_retrieval import build_retrieval_intent, evidence_from_items, hybrid_retrieve


class DeepResearchState(TypedDict):
    user_id: str
    question: str
    tickers: list[str]
    source_scope: list[str]
    evidence: list[dict]
    synthesis: dict


class ResearchSynthesis(BaseModel):
    conclusion: str = Field(description="一句话结论，必须忠于证据")
    thesis: str = Field(description="支持结论的核心逻辑")
    counter_evidence: str = Field(description="反面证据、冲突观点或证据缺口")
    risks: list[str] = Field(default_factory=list)
    evidence_keys: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


def retrieve_evidence(state: DeepResearchState) -> dict:
    from uuid import UUID

    ticker = (state.get("tickers") or [""])[0]
    query = f"{ticker} {state['question']}".strip()
    intent = build_retrieval_intent(state["question"], ticker=ticker)
    result = hybrid_retrieve(
        intent,
        user_id=UUID(state["user_id"]),
        query=query,
        source_scope=state.get("source_scope") or ["public_signals", "tweets"],
    )
    return {"evidence": evidence_from_items(result["reranked"])}


def synthesize(state: DeepResearchState) -> dict:
    evidence = state.get("evidence") or []
    if not evidence:
        return {"synthesis": {
            "conclusion": "当前没有检索到足够的直接证据。",
            "thesis": "",
            "counter_evidence": "缺少目标范围内的 Twitter 原文或结构化分析。",
            "risks": ["证据不足"],
            "evidence_keys": [],
            "confidence": 0.0,
        }}
    evidence_text = "\n\n".join(
        f"[{item['evidence_id']}] {item.get('source_type')} | {item.get('ticker')} | {item.get('author')}\n{item.get('content')}"
        for item in evidence[:20]
    )
    prompt = (
        "你是投资研究负责人。只根据下面证据回答研究问题，必须同时讨论支持证据、反面证据和证据缺口。"
        "evidence_keys 只能填写下方存在的 E 编号，不得编造。\n\n"
        f"研究问题：{state['question']}\n\n证据：\n{evidence_text}"
    )
    result = get_report_llm().with_structured_output(ResearchSynthesis).invoke(prompt)
    valid = {item["evidence_id"] for item in evidence}
    data = result.model_dump()
    data["evidence_keys"] = [key for key in data["evidence_keys"] if key in valid]
    if not data["evidence_keys"]:
        data["confidence"] = min(data["confidence"], 0.2)
    return {"synthesis": data}


def build_deep_research_graph():
    graph = StateGraph(DeepResearchState)
    graph.add_node("retrieve_evidence", retrieve_evidence)
    graph.add_node("synthesize", synthesize)
    graph.add_edge(START, "retrieve_evidence")
    graph.add_edge("retrieve_evidence", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


deep_research_graph = build_deep_research_graph()
