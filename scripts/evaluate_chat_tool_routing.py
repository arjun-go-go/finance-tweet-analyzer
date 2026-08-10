"""Offline verifier for Chat Agent route and candidate-tool selection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.chat.routing import classify_tool_route


DEFAULT_CASES = PROJECT_ROOT / "evals" / "chat_tool_routing" / "cases.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    route_hits = 0
    required_hits = 0
    required_total = 0
    forbidden_hits = 0
    forbidden_total = 0
    failures = []

    for case in cases:
        route, allowed = classify_tool_route(case["input"], case.get("context", ""))
        route_ok = route == case["expected_route"]
        route_hits += int(route_ok)

        missing = [name for name in case.get("required_tools", []) if name not in allowed]
        leaked = [name for name in case.get("forbidden_tools", []) if name in allowed]
        required_total += len(case.get("required_tools", []))
        required_hits += len(case.get("required_tools", [])) - len(missing)
        forbidden_total += len(case.get("forbidden_tools", []))
        forbidden_hits += len(case.get("forbidden_tools", [])) - len(leaked)

        if not route_ok or missing or leaked:
            failures.append({
                "id": case["id"],
                "expected_route": case["expected_route"],
                "actual_route": route,
                "missing_required_tools": missing,
                "exposed_forbidden_tools": leaked,
            })

    route_accuracy = route_hits / len(cases) if cases else 0
    required_exposure = required_hits / required_total if required_total else 1
    forbidden_exclusion = forbidden_hits / forbidden_total if forbidden_total else 1
    summary = {
        "cases": len(cases),
        "route_accuracy": round(route_accuracy, 4),
        "required_tool_exposure": round(required_exposure, 4),
        "forbidden_tool_exclusion": round(forbidden_exclusion, 4),
        "failures": failures,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
