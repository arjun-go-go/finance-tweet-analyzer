"""Live-model, no-side-effect P2 evaluator for Chat Agent."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.chat.routing import classify_tool_route
from app.agents.chat.nodes.agent import agent_node_impl, build_prompt_from_state
from app.agents.chat.tool_results import attach_tool_evidence, tool_error, tool_ok
from app.agents.chat.tools.registry import TOOLS_BY_NAME
from app.agents.llm import get_report_llm
from app.prompts import get_prompt
from evals.chat_agent_p2.dataset import evidence_cases, selection_cases


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


def _selection_preflight(cases: list[dict]) -> list[dict]:
    failures = []
    for case in cases:
        _, allowed = classify_tool_route(case["input"], case.get("history", ""))
        expected = case["expected_tool"]
        if expected is not None and expected not in allowed:
            failures.append({
                "id": case["id"],
                "category": case["category"],
                "expected_tool": expected,
                "allowed_tools": allowed,
            })
    return failures


def _run_selection_case(case: dict, llm) -> dict:
    history = case.get("history", "")
    _, allowed_names = classify_tool_route(case["input"], history)
    messages = []
    if history:
        messages.append(AIMessage(content=history))
    messages.append(HumanMessage(content=case["input"]))
    try:
        node_result = agent_node_impl(
            {
                "messages": messages,
                "user_profile": {},
                "user_prefs": {},
                "memories": [],
                "consecutive_tool_failures": 0,
                "allowed_tool_names": allowed_names,
                "tool_route": classify_tool_route(case["input"], history)[0],
            },
            {},
            tools_by_name=TOOLS_BY_NAME,
            default_tool_names=allowed_names,
            estimate_tokens=lambda items: sum(len(_content_text(item.content)) for item in items) // 4,
            get_llm=lambda: llm,
            build_prompt=build_prompt_from_state,
        )
        response = node_result["messages"][0]
        actual_tool = response.tool_calls[0]["name"] if response.tool_calls else None
        return {
            "id": case["id"],
            "category": case["category"],
            "expected_tool": case["expected_tool"],
            "actual_tool": actual_tool,
            "passed": actual_tool == case["expected_tool"],
            "error": None,
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "category": case["category"],
            "expected_tool": case["expected_tool"],
            "actual_tool": None,
            "passed": False,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }


def _run_evidence_case(case: dict, llm) -> dict:
    tool_name = case["tool"]
    call_id = f"call-{case['id']}"
    tool_args = {
        "query_database": {"natural_language_query": case["input"]},
        "search_public_signals": {
            "query": case["input"],
            "source_type": "analysis",
            "blogger": "",
        },
        "search_my_documents": {"query": case["input"], "ticker": ""},
        "list_my_followed_bloggers": {},
        "list_my_tracked_tickers": {},
    }[tool_name]
    if case["kind"] == "error":
        envelope = tool_error("EVAL_TOOL_ERROR", case["tool_error"], retryable=False)
    else:
        envelope = attach_tool_evidence(tool_ok(case["tool_result"]), tool_name)
    messages = [
        SystemMessage(content=get_prompt("chat/system")),
        HumanMessage(content=case["input"]),
        AIMessage(content="", tool_calls=[{
            "name": tool_name,
            "args": tool_args,
            "id": call_id,
            "type": "tool_call",
        }]),
        ToolMessage(content=envelope, tool_call_id=call_id, name=tool_name),
    ]
    try:
        state = {
            "messages": messages[1:],
            "user_profile": {},
            "user_prefs": {},
            "memories": [],
            "consecutive_tool_failures": 1 if case["kind"] == "error" else 0,
            "allowed_tool_names": [tool_name],
        }
        node_result = agent_node_impl(
            state,
            {},
            tools_by_name=TOOLS_BY_NAME,
            default_tool_names=[tool_name],
            estimate_tokens=lambda items: sum(len(_content_text(item.content)) for item in items) // 4,
            get_llm=lambda: llm,
            build_prompt=build_prompt_from_state,
        )
        response = node_result["messages"][0]
        answer = _content_text(response.content)
        problems = []
        if response.tool_calls:
            problems.append("model_called_another_tool")
        required_fact = case.get("required_fact")
        if required_fact and required_fact not in answer:
            problems.append("missing_required_fact")
        required_citation = case.get("required_citation")
        if required_citation and required_citation not in answer:
            problems.append("missing_required_citation")
        forbidden_citation = case.get("forbidden_citation")
        if forbidden_citation and forbidden_citation in answer:
            problems.append("cited_failed_tool")
        if case["kind"] in ("empty", "error") and not any(
            phrase in answer for phrase in ("未找到", "没有", "证据不足", "无法确认", "暂时不可用", "无法查询")
        ):
            problems.append("missing_abstention")
        return {
            "id": case["id"],
            "kind": case["kind"],
            "tool": tool_name,
            "passed": not problems,
            "problems": problems,
            "answer": answer[:500],
            "error": None,
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "kind": case["kind"],
            "tool": tool_name,
            "passed": False,
            "problems": ["infrastructure_error"],
            "answer": "",
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }


def _run_parallel(cases: list[dict], worker, concurrency: int) -> list[dict]:
    llm = get_report_llm()
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, case, llm) for case in cases]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _selection_summary(cases: list[dict], results: list[dict], gate_failures: list[dict]) -> dict:
    category_total = Counter(case["category"] for case in cases)
    category_passed = Counter(result["category"] for result in results if result["passed"])
    per_category = {
        category: {
            "passed": category_passed[category],
            "total": total,
            "accuracy": round(category_passed[category] / total, 4),
        }
        for category, total in sorted(category_total.items())
    }
    passed = sum(result["passed"] for result in results)
    return {
        "suite": "selection",
        "cases": len(cases),
        "passed": passed,
        "accuracy": round(passed / len(cases), 4) if cases else 0,
        "route_gate_failures": gate_failures,
        "per_category": per_category,
        "failures": [result for result in results if not result["passed"]],
    }


def _evidence_summary(cases: list[dict], results: list[dict]) -> dict:
    by_kind = defaultdict(lambda: {"passed": 0, "total": 0})
    for result in results:
        by_kind[result["kind"]]["total"] += 1
        by_kind[result["kind"]]["passed"] += int(result["passed"])
    for counts in by_kind.values():
        counts["accuracy"] = round(counts["passed"] / counts["total"], 4)
    passed = sum(result["passed"] for result in results)
    return {
        "suite": "evidence",
        "cases": len(cases),
        "passed": passed,
        "accuracy": round(passed / len(cases), 4) if cases else 0,
        "per_kind": dict(by_kind),
        "failures": [result for result in results if not result["passed"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("selection", "evidence"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    cases = selection_cases() if args.suite == "selection" else evidence_cases()
    if args.category:
        cases = [case for case in cases if case.get("category") == args.category or case.get("kind") == args.category]
    if args.limit > 0:
        cases = cases[: args.limit]

    if args.suite == "selection":
        gate_failures = _selection_preflight(cases)
        if args.preflight:
            summary = {
                "suite": "selection-preflight",
                "cases": len(cases),
                "route_gate_failures": gate_failures,
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if not gate_failures else 1
        results = _run_parallel(cases, _run_selection_case, args.concurrency)
        summary = _selection_summary(cases, results, gate_failures)
    else:
        results = _run_parallel(cases, _run_evidence_case, args.concurrency)
        summary = _evidence_summary(cases, results)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
