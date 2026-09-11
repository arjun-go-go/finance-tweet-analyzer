"""Deterministically normalize forecast time evidence from one instrument claim."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone


_CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass(frozen=True)
class ResolvedPredictionTime:
    temporal_expression: str
    target_at: datetime | None
    horizon: str
    source: str
    confidence: float
    status: str
    rationale: str

    def evidence(self) -> dict:
        return {
            "temporal_expression": self.temporal_expression,
            "target_at": self.target_at.isoformat() if self.target_at else None,
            "horizon": self.horizon,
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            "rationale": self.rationale,
        }


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _number(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if value in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value]
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        ones = _CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _at_day_end(reference: datetime, year: int, month: int, day: int) -> datetime:
    return datetime.combine(
        datetime(year, month, day).date(),
        time(23, 59, 59),
        tzinfo=reference.tzinfo,
    )


def _end_of_month(reference: datetime, year: int, month: int) -> datetime:
    return _at_day_end(reference, year, month, calendar.monthrange(year, month)[1])


def _add_months(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_business_days(value: datetime, days: int) -> datetime:
    result = value
    remaining = days
    while remaining > 0:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1
    return result


def _bucket(published_at: datetime, target_at: datetime | None, fallback: str = "unknown") -> str:
    if target_at is None:
        return fallback if fallback in {"short", "medium", "long"} else "unknown"
    days = (target_at - published_at).total_seconds() / 86400
    if days <= 30:
        return "short"
    if days <= 180:
        return "medium"
    return "long"


def _resolved(
    expression: str,
    published_at: datetime,
    target_at: datetime,
    *,
    source: str,
    confidence: float,
    rationale: str,
) -> ResolvedPredictionTime:
    if target_at <= published_at:
        return ResolvedPredictionTime(
            expression,
            None,
            "unknown",
            source,
            confidence,
            "invalid_past_target",
            "时间指向推文发布前或发布时，不能作为未来预测期限",
        )
    return ResolvedPredictionTime(
        expression,
        target_at,
        _bucket(published_at, target_at),
        source,
        confidence,
        "resolved",
        rationale,
    )


def _qualitative_default(
    published_at: datetime,
    horizon: str,
    market: str,
) -> datetime:
    if market == "CRYPTO":
        return published_at + timedelta(days={"short": 30, "medium": 90, "long": 365}[horizon])
    return _add_business_days(
        published_at,
        {"short": 20, "medium": 63, "long": 252}[horizon],
    )


def resolve_prediction_time(
    claim: dict,
    published_at: datetime,
) -> ResolvedPredictionTime:
    """Resolve only explicit time evidence; never infer a deadline from sentiment."""
    published_at = _as_aware(published_at)
    forecast = claim.get("forecast") or {}
    expression = str(forecast.get("temporal_expression") or "").strip()
    normalized = expression.lower().replace(" ", "")
    claim_horizon = str(claim.get("horizon") or "unknown").lower()
    instrument = claim.get("instrument") or {}
    market = str(instrument.get("market") or instrument.get("market_hint") or "unknown").upper()

    fiscal_match = re.search(r"fy(\d{2,4})", normalized, re.IGNORECASE)
    if not fiscal_match:
        fiscal_match = re.search(r"(\d{2,4})年?财年", normalized)
    if fiscal_match:
        year = int(fiscal_match.group(1))
        if year < 100:
            year += 2000
        approximate = _at_day_end(published_at, year, 12, 31)
        return ResolvedPredictionTime(
            expression,
            None,
            _bucket(published_at, approximate),
            "fiscal_period",
            0.95,
            "awaiting_period_date",
            f"识别到 FY{year}，需由公司财务日历确定正式期间结束日",
        )

    date_match = re.search(
        r"(?P<year>20\d{2})[年/\-.](?P<month>\d{1,2})(?:[月/\-.](?P<day>\d{1,2})日?)?",
        normalized,
    )
    if date_match:
        year = int(date_match.group("year"))
        month = int(date_match.group("month"))
        day_text = date_match.group("day")
        target = (
            _at_day_end(published_at, year, month, int(day_text))
            if day_text
            else _end_of_month(published_at, year, month)
        )
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_date",
            confidence=1.0,
            rationale="由原文明示日期确定验证截止时间",
        )

    year_end = re.search(r"(20\d{2})年?(?:年底|年末|年内)", normalized)
    if year_end:
        target = _at_day_end(published_at, int(year_end.group(1)), 12, 31)
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_date",
            confidence=1.0,
            rationale="由原文明示年份末确定验证截止时间",
        )
    if any(term in normalized for term in ("今年年底", "今年年末", "年内", "年底", "yearend")):
        target = _at_day_end(published_at, published_at.year, 12, 31)
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_date",
            confidence=0.95,
            rationale="按推文发布年份的年末确定截止时间",
        )
    if any(term in normalized for term in ("明年", "nextyear")):
        target = _at_day_end(published_at, published_at.year + 1, 12, 31)
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_period",
            confidence=0.9,
            rationale="按原文下一自然年期末确定截止时间",
        )

    duration_match = re.search(
        r"(?:未来|接下来|今后|随后|in|next)?([0-9一二两三四五六七八九十]+)个?(天|日|周|星期|个月|月|季度|年)(?:内|以内|后)?",
        normalized,
    )
    if duration_match:
        amount = _number(duration_match.group(1))
        unit = duration_match.group(2)
        if amount and amount > 0:
            if unit in {"天", "日"}:
                target = published_at + timedelta(days=amount)
            elif unit in {"周", "星期"}:
                target = published_at + timedelta(weeks=amount)
            elif unit in {"个月", "月"}:
                target = _add_months(published_at, amount)
            elif unit == "季度":
                target = _add_months(published_at, amount * 3)
            else:
                target = _add_months(published_at, amount * 12)
            return _resolved(
                expression,
                published_at,
                target,
                source="explicit_duration",
                confidence=0.98,
                rationale="由原文明示持续时间计算验证截止时间",
            )

    english_duration = re.search(
        r"(?:in|next)?(\d+)(day|week|month|quarter|year)s?",
        normalized,
        re.IGNORECASE,
    )
    if english_duration:
        amount = int(english_duration.group(1))
        unit = english_duration.group(2).lower()
        if unit == "day":
            target = published_at + timedelta(days=amount)
        elif unit == "week":
            target = published_at + timedelta(weeks=amount)
        elif unit == "month":
            target = _add_months(published_at, amount)
        elif unit == "quarter":
            target = _add_months(published_at, amount * 3)
        else:
            target = _add_months(published_at, amount * 12)
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_duration",
            confidence=0.98,
            rationale="由原文明示持续时间计算验证截止时间",
        )

    if "半年" in normalized:
        return _resolved(
            expression,
            published_at,
            _add_months(published_at, 6),
            source="explicit_duration",
            confidence=0.98,
            rationale="按半年期限计算验证截止时间",
        )
    if "下周" in normalized or "nextweek" in normalized:
        days_to_next_sunday = 13 - published_at.weekday()
        target = _at_day_end(
            published_at,
            *(published_at + timedelta(days=days_to_next_sunday)).date().timetuple()[:3],
        )
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_period",
            confidence=0.9,
            rationale="按下一个自然周末确定截止时间",
        )
    if "下个月" in normalized or "nextmonth" in normalized:
        next_month = _add_months(published_at, 1)
        target = _end_of_month(published_at, next_month.year, next_month.month)
        return _resolved(
            expression,
            published_at,
            target,
            source="explicit_period",
            confidence=0.9,
            rationale="按下一个自然月末确定截止时间",
        )

    event_terms = (
        "财报",
        "业绩发布",
        "ipo",
        "上市时",
        "获批",
        "审批",
        "发布会",
        "earnings",
        "fomc",
    )
    if expression and any(term in normalized for term in event_terms):
        return ResolvedPredictionTime(
            expression,
            None,
            claim_horizon if claim_horizon in {"short", "medium", "long"} else "unknown",
            "event_anchor",
            0.85,
            "awaiting_event_date",
            "已识别事件锚点，需由事件日历补全正式日期",
        )

    qualitative = claim_horizon
    if qualitative not in {"short", "medium", "long"}:
        if "短期" in normalized or "shortterm" in normalized:
            qualitative = "short"
        elif "中期" in normalized or "mediumterm" in normalized:
            qualitative = "medium"
        elif "长期" in normalized or "longterm" in normalized:
            qualitative = "long"
    if qualitative in {"short", "medium", "long"}:
        target = _qualitative_default(published_at, qualitative, market)
        convention = (
            {"short": 30, "medium": 90, "long": 365}[qualitative]
            if market == "CRYPTO"
            else {"short": 20, "medium": 63, "long": 252}[qualitative]
        )
        unit = "自然日" if market == "CRYPTO" else "交易日"
        return ResolvedPredictionTime(
            expression,
            target,
            qualitative,
            "qualitative_label",
            0.7,
            "resolved_by_convention",
            f"原文只说明{qualitative}，按产品标准 {convention} 个{unit}归一化",
        )

    return ResolvedPredictionTime(
        expression,
        None,
        "unknown",
        "missing",
        0.0,
        "missing",
        "原文没有可审计的时间依据",
    )
