"""Deterministic parsing and scoring for numeric prediction targets."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NumericTarget:
    low: float
    high: float
    unit: str
    multiplier: float
    is_percent: bool

    def evidence(self) -> dict:
        return {
            "low": self.low,
            "high": self.high,
            "unit": self.unit,
            "multiplier": self.multiplier,
            "is_percent": self.is_percent,
        }


def parse_numeric_target(value: str, unit: str = "") -> NumericTarget:
    raw_value = str(value or "").strip().replace(",", "")
    raw_unit = str(unit or "").strip()
    if not raw_value:
        raise ValueError("预测目标缺少数值")

    normalized = re.sub(r"(?<=\d)\s*(?:-|~|～|—|–|至|到)\s*(?=\d)", "|", raw_value)
    numbers = [float(item) for item in re.findall(r"[+-]?\d+(?:\.\d+)?", normalized)]
    if not numbers:
        raise ValueError(f"无法解析预测目标数值: {value}")

    low = min(numbers[:2])
    high = max(numbers[:2])
    combined_unit = f"{raw_value} {raw_unit}".lower()
    is_percent = "%" in combined_unit or "percent" in combined_unit or "百分" in combined_unit
    if "万亿" in combined_unit or "trillion" in combined_unit:
        multiplier = 1_000_000_000_000.0
    elif "billion" in combined_unit:
        multiplier = 1_000_000_000.0
    elif "million" in combined_unit:
        multiplier = 1_000_000.0
    elif "亿" in combined_unit:
        multiplier = 100_000_000.0
    elif "万" in combined_unit:
        multiplier = 10_000.0
    elif re.search(r"(?:^|\s)k(?:\s|$)", combined_unit):
        multiplier = 1_000.0
    else:
        multiplier = 1.0
    return NumericTarget(
        low=low,
        high=high,
        unit=raw_unit,
        multiplier=multiplier,
        is_percent=is_percent,
    )


def scale_observed_value(value: float, target: NumericTarget) -> float:
    """Convert a provider base-unit value into the target's displayed scale."""
    return float(value) if target.is_percent else float(value) / target.multiplier


def score_numeric_target(
    actual: float,
    target: NumericTarget,
    operator: str,
    *,
    partial_tolerance: float = 0.10,
) -> tuple[str, float, dict]:
    """Score one observation without substituting another metric or unit."""
    normalized_operator = str(operator or "unknown").lower()
    if normalized_operator == "unknown":
        normalized_operator = "range" if target.low != target.high else "equals"

    scale = max(abs(target.low), abs(target.high), 1.0)
    tolerance = scale * partial_tolerance
    if normalized_operator in {"gte", "up"}:
        boundary = target.low
        correct = actual >= boundary
        partial = actual >= boundary - tolerance
        distance = actual - boundary
    elif normalized_operator in {"lte", "down"}:
        boundary = target.high
        correct = actual <= boundary
        partial = actual <= boundary + tolerance
        distance = boundary - actual
    elif normalized_operator == "range" or target.low != target.high:
        correct = target.low <= actual <= target.high
        distance_to_range = min(abs(actual - target.low), abs(actual - target.high))
        partial = distance_to_range <= tolerance
        distance = 0.0 if correct else -distance_to_range
    elif normalized_operator == "equals":
        boundary = target.low
        exact_tolerance = max(abs(boundary) * 0.02, 1e-9)
        distance_to_target = abs(actual - boundary)
        correct = distance_to_target <= exact_tolerance
        partial = distance_to_target <= tolerance
        distance = -distance_to_target
    else:
        raise ValueError(f"数值预测不支持操作符: {operator}")

    if correct:
        verdict, score = "correct", 1.0
    elif partial:
        verdict, score = "partial", 0.5
    else:
        verdict, score = "incorrect", 0.0
    return verdict, score, {
        "actual": actual,
        "operator": normalized_operator,
        "target": target.evidence(),
        "partial_tolerance": partial_tolerance,
        "distance": distance,
    }
