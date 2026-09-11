"""Authoritative financial-statement verification for fundamental forecasts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.resilience import resilient_tool
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.services.credibility import recompute_blogger
from app.services.market_verification_service import preview_prediction_identity
from app.services.prediction_contract_math import (
    parse_numeric_target,
    scale_observed_value,
    score_numeric_target,
)


RULE_VERSION = "fundamental_metric_v1"
SUPPORTED_METRICS = {
    "revenue",
    "revenue_growth_rate",
    "net_income",
    "net_income_growth_rate",
    "eps",
    "gross_margin",
}
_METRIC_ALIASES = {
    "total_revenue": "revenue",
    "operating_revenue": "revenue",
    "revenue_growth": "revenue_growth_rate",
    "revenue_yoy": "revenue_growth_rate",
    "sales_growth": "revenue_growth_rate",
    "net_profit": "net_income",
    "profit": "net_income",
    "net_profit_growth": "net_income_growth_rate",
    "net_income_growth": "net_income_growth_rate",
    "earnings_per_share": "eps",
    "diluted_eps": "eps",
    "gross_profit_margin": "gross_margin",
}


def canonical_fundamental_metric(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return _METRIC_ALIASES.get(normalized, normalized)


def _fiscal_year(expression: str) -> int | None:
    match = re.search(r"fy\s*(20\d{2}|\d{2})", expression, re.IGNORECASE)
    if not match:
        match = re.search(r"(20\d{2}|\d{2})年?(?:财年|年度|年报)", expression)
    if not match:
        return None
    year = int(match.group(1))
    return year + 2000 if year < 100 else year


@resilient_tool(
    retries=2,
    circuit_name="fundamental_sec_companyfacts",
    fallback_message="SEC company facts unavailable",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _load_sec_companyfacts(cik: str) -> dict:
    normalized = str(cik or "").strip().zfill(10)
    if not normalized.strip("0"):
        raise ValueError("SEC CIK is required")
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalized}.json"
    headers = {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
    with httpx.Client(timeout=settings.instrument_api_timeout_seconds) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


@resilient_tool(
    retries=1,
    circuit_name="fundamental_akshare_cn",
    fallback_message="A-share financial statements unavailable",
)
def _load_cn_financials(symbol: str) -> list[dict]:
    import akshare as ak

    frame = ak.stock_financial_analysis_indicator_em(
        symbol=symbol,
        indicator="按报告期",
    )
    return [] if frame is None or frame.empty else frame.to_dict("records")


@resilient_tool(
    retries=1,
    circuit_name="fundamental_akshare_hk",
    fallback_message="Hong Kong financial statements unavailable",
)
def _load_hk_financials(symbol: str) -> list[dict]:
    import akshare as ak

    code = symbol.split(".")[0].zfill(5)
    frame = ak.stock_financial_hk_analysis_indicator_em(
        symbol=code,
        indicator="年度",
    )
    return [] if frame is None or frame.empty else frame.to_dict("records")


def _sec_fact_rows(
    payload: dict,
    tags: tuple[str, ...],
    year: int,
) -> tuple[list[dict], str, str] | None:
    facts = (payload.get("facts") or {}).get("us-gaap") or {}
    fallback = None
    for tag in tags:
        node = facts.get(tag) or {}
        for unit, rows in (node.get("units") or {}).items():
            annual = []
            for row in rows:
                if row.get("form") not in {"10-K", "20-F", "40-F"} or row.get("fp") != "FY":
                    continue
                try:
                    end = datetime.fromisoformat(str(row.get("end"))).date()
                    start = datetime.fromisoformat(str(row.get("start"))).date() if row.get("start") else None
                    value = float(row.get("val"))
                except (TypeError, ValueError):
                    continue
                if start and (end - start).days < 250:
                    continue
                annual.append({**row, "_end": end, "_value": value})
            if annual:
                by_end: dict[Any, dict] = {}
                for row in annual:
                    existing = by_end.get(row["_end"])
                    if existing is None or str(row.get("filed") or "") > str(existing.get("filed") or ""):
                        by_end[row["_end"]] = row
                resolved = sorted(by_end.values(), key=lambda row: row["_end"]), unit, tag
                if any(row["_end"].year == year for row in resolved[0]):
                    return resolved
                fallback = fallback or resolved
    return fallback


def _sec_year_value(rows: list[dict], year: int) -> dict | None:
    candidates = [row for row in rows if row["_end"].year == year]
    return max(candidates, key=lambda row: row["_end"]) if candidates else None


def _sec_observation(payload: dict, metric: str, year: int) -> dict | None:
    tag_map = {
        "revenue": (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ),
        "net_income": ("NetIncomeLoss", "ProfitLoss"),
        "eps": ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
        "gross_profit": ("GrossProfit",),
    }

    base_metric = (
        "revenue" if metric == "revenue_growth_rate"
        else "net_income" if metric == "net_income_growth_rate"
        else metric
    )
    if metric == "gross_margin":
        revenue = _sec_fact_rows(payload, tag_map["revenue"], year)
        gross_profit = _sec_fact_rows(payload, tag_map["gross_profit"], year)
        if not revenue or not gross_profit:
            return None
        revenue_row = _sec_year_value(revenue[0], year)
        gross_row = _sec_year_value(gross_profit[0], year)
        if not revenue_row or not gross_row or revenue_row["_value"] == 0:
            return None
        return {
            "value": gross_row["_value"] / revenue_row["_value"] * 100,
            "unit": "%",
            "period": str(gross_row["_end"]),
            "filed_at": gross_row.get("filed"),
            "provider": "SEC EDGAR Company Facts",
            "provider_metric": f"{gross_profit[2]}/{revenue[2]}",
        }

    resolved = _sec_fact_rows(payload, tag_map[base_metric], year)
    if not resolved:
        return None
    rows, unit, tag = resolved
    current = _sec_year_value(rows, year)
    if not current:
        return None
    if metric in {"revenue_growth_rate", "net_income_growth_rate"}:
        previous = _sec_year_value(rows, year - 1)
        if not previous or previous["_value"] == 0:
            return None
        value = (current["_value"] / previous["_value"] - 1) * 100
        unit = "%"
    else:
        value = current["_value"]
    return {
        "value": value,
        "unit": unit,
        "period": str(current["_end"]),
        "filed_at": current.get("filed"),
        "provider": "SEC EDGAR Company Facts",
        "provider_metric": tag,
    }


def _cn_observation(rows: list[dict], metric: str, year: int) -> dict | None:
    annual = [
        row for row in rows
        if str(row.get("REPORT_YEAR") or "") == str(year)
        and ("年报" in str(row.get("REPORT_TYPE") or "") or str(row.get("REPORT_DATE") or "")[5:10] == "12-31")
    ]
    if not annual:
        return None
    row = max(annual, key=lambda item: str(item.get("REPORT_DATE") or ""))
    fields = {
        "revenue": ("TOTALOPERATEREVE", "CNY"),
        "revenue_growth_rate": ("TOTALOPERATEREVETZ", "%"),
        "net_income": ("PARENTNETPROFIT", "CNY"),
        "net_income_growth_rate": ("PARENTNETPROFITTZ", "%"),
        "eps": ("EPSJB", "CNY/share"),
        "gross_margin": ("XSMLL", "%"),
    }
    field, unit = fields[metric]
    if row.get(field) is None:
        return None
    return {
        "value": float(row[field]),
        "unit": unit,
        "period": str(row.get("REPORT_DATE") or ""),
        "filed_at": str(row.get("NOTICE_DATE") or ""),
        "provider": "AKShare / Eastmoney A-share financial indicators",
        "provider_metric": field,
    }


def _hk_observation(rows: list[dict], metric: str, year: int) -> dict | None:
    candidates = [row for row in rows if str(row.get("REPORT_DATE") or "").startswith(str(year))]
    if not candidates:
        return None
    row = max(candidates, key=lambda item: str(item.get("REPORT_DATE") or ""))
    fields = {
        "revenue": ("OPERATE_INCOME", str(row.get("CURRENCY") or "HKD")),
        "revenue_growth_rate": ("OPERATE_INCOME_YOY", "%"),
        "net_income": ("HOLDER_PROFIT", str(row.get("CURRENCY") or "HKD")),
        "net_income_growth_rate": ("HOLDER_PROFIT_YOY", "%"),
        "eps": ("BASIC_EPS", f"{row.get('CURRENCY') or 'HKD'}/share"),
        "gross_margin": ("GROSS_PROFIT_RATIO", "%"),
    }
    field, unit = fields[metric]
    if row.get(field) is None:
        return None
    return {
        "value": float(row[field]),
        "unit": unit,
        "period": str(row.get("REPORT_DATE") or ""),
        "filed_at": None,
        "provider": "AKShare / Eastmoney Hong Kong financial indicators",
        "provider_metric": field,
    }


def _currency_from_target(unit: str) -> str | None:
    normalized = str(unit or "").upper()
    if "美元" in unit or "USD" in normalized or "$" in normalized:
        return "USD"
    if "港元" in unit or "港币" in unit or "HKD" in normalized:
        return "HKD"
    if "人民币" in unit or "CNY" in normalized or "RMB" in normalized:
        return "CNY"
    return None


def load_fundamental_observation(prediction: Prediction) -> tuple[dict | None, dict]:
    target = dict(prediction.target_spec or {})
    metric = canonical_fundamental_metric(str(target.get("target_metric") or ""))
    year = _fiscal_year(prediction.temporal_expression or "")
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"暂不支持基本面指标: {metric or 'missing'}")
    if year is None:
        raise ValueError("基本面预测缺少可识别的财年")
    ticker = dict(prediction.instrument_snapshot or {})
    market = str(ticker.get("market") or "").upper()
    symbol = str(ticker.get("symbol") or prediction.ticker).upper()
    if market == "US":
        cik = str((ticker.get("external_ids") or {}).get("cik") or "")
        payload = _load_sec_companyfacts(cik)
        if isinstance(payload, str):
            raise RuntimeError(payload)
        observation = _sec_observation(payload, metric, year)
    elif market == "CN":
        rows = _load_cn_financials(symbol)
        if isinstance(rows, str):
            raise RuntimeError(rows)
        observation = _cn_observation(rows, metric, year)
    elif market == "HK":
        rows = _load_hk_financials(symbol)
        if isinstance(rows, str):
            raise RuntimeError(rows)
        observation = _hk_observation(rows, metric, year)
    else:
        raise ValueError(f"{market or 'unknown'} 市场暂无基本面财报验证器")
    return observation, {"metric": metric, "fiscal_year": year, "market": market, "symbol": symbol}


def preview_fundamental_verification(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    now = as_of or datetime.now(timezone.utc)
    base = {
        "prediction_id": str(prediction.id),
        "prediction_type": prediction.prediction_type,
        "verifier_type": prediction.verifier_type,
        "ticker": prediction.ticker,
        "as_of": now.isoformat(),
        "write_back_allowed": False,
    }
    if prediction.verifier_type != "fundamental_metric" or not prediction.scoring_eligible:
        return {**base, "status": "unsupported", "reason": "不是已启用的基本面预测契约"}
    if prediction.verdict is not None:
        return {**base, "status": "already_verified", "reason": "已有正式验证结果"}
    identity_result = preview_prediction_identity(
        db,
        prediction,
        require_direction=False,
    )
    if identity_result:
        return {**base, **identity_result, "as_of": now.isoformat()}
    target_spec = dict(prediction.target_spec or {})
    try:
        observation, context = load_fundamental_observation(prediction)
    except ValueError as exc:
        return {**base, "status": "manual_review", "review_type": "target_contract", "reason": str(exc), "target_spec": target_spec}
    except Exception as exc:
        logger.warning("Fundamental verification failed for {}: {}", prediction.id, exc)
        return {**base, "status": "market_data_unavailable", "review_type": "fundamental_data", "reason": str(exc), "target_spec": target_spec}
    if observation is None:
        return {
            **base,
            "status": "tracking",
            "reason": f"等待 {context['fiscal_year']} 财年正式报告指标",
            "target_spec": target_spec,
            "context": context,
        }
    filed_at = str(observation.get("filed_at") or "")
    if filed_at:
        try:
            filed_on = datetime.fromisoformat(filed_at.replace("Z", "+00:00")).date()
        except ValueError:
            filed_on = None
        if filed_on and filed_on > now.date():
            return {
                **base,
                "status": "tracking",
                "reason": f"等待 {filed_on.isoformat()} 正式披露后再验证",
                "target_spec": target_spec,
                "context": context,
            }

    try:
        target = parse_numeric_target(
            str(target_spec.get("target_value") or ""),
            str(target_spec.get("target_unit") or ""),
        )
    except ValueError as exc:
        return {**base, "status": "manual_review", "review_type": "target_contract", "reason": str(exc), "target_spec": target_spec}
    expected_currency = _currency_from_target(str(target_spec.get("target_unit") or ""))
    observed_currency = str(observation.get("unit") or "").split("/")[0].upper()
    if expected_currency and expected_currency != observed_currency:
        return {
            **base,
            "status": "manual_review",
            "review_type": "unit_mismatch",
            "reason": f"目标单位 {expected_currency} 与财报单位 {observed_currency} 不一致，禁止自动换汇计分",
            "target_spec": target_spec,
            "observation": observation,
        }
    actual = scale_observed_value(float(observation["value"]), target)
    operator = str(target_spec.get("target_operator") or "unknown")
    try:
        verdict, score, comparison = score_numeric_target(actual, target, operator)
    except ValueError as exc:
        return {**base, "status": "manual_review", "review_type": "target_contract", "reason": str(exc), "target_spec": target_spec, "observation": observation}
    return {
        **base,
        "status": "ready",
        "market": context["market"],
        "provider_symbol": context["symbol"],
        "provider": observation["provider"],
        "target_spec": target_spec,
        "parsed_target": target.evidence(),
        "observation": {**observation, "scaled_value": actual, **context},
        "comparison": comparison,
        "preview_verdict": verdict,
        "preview_score": score,
        "reason": "已使用目标财年正式披露指标完成验证",
    }


def _audit(prediction: Prediction, result: dict) -> PredictionMarketVerification:
    observation = result.get("observation") or {}
    return PredictionMarketVerification(
        prediction_id=prediction.id,
        verification_type="fundamental_metric",
        status=str(result.get("status") or "market_data_unavailable"),
        provider=result.get("provider") or observation.get("provider"),
        provider_symbol=result.get("provider_symbol") or observation.get("symbol") or prediction.ticker,
        market=result.get("market") or observation.get("market"),
        end_observed_at=observation.get("period"),
        proposed_verdict=result.get("preview_verdict"),
        proposed_score=result.get("preview_score"),
        rule_version=RULE_VERSION,
        evidence=result,
        observation=observation,
        error_message=(str(result.get("reason")) if result.get("status") in {"manual_review", "market_data_unavailable"} else None),
    )


def verify_fundamental_prediction(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    now = as_of or datetime.now(timezone.utc)
    result = preview_fundamental_verification(db, prediction, as_of=now)
    audit = _audit(prediction, result)
    db.add(audit)
    if result.get("status") != "ready":
        db.flush()
        return result
    prediction.verdict = str(result["preview_verdict"])
    prediction.score = float(result["preview_score"])
    prediction.verified_at = now
    prediction.verified_by = RULE_VERSION
    observation = result.get("observation") or {}
    prediction.note = (
        f"{result.get('provider')} {observation.get('provider_metric')}: "
        f"actual={observation.get('scaled_value')} {observation.get('unit')}"
    )
    audit.applied = True
    audit.applied_at = now
    recompute_blogger(db, prediction.blogger_handle)
    db.flush()
    return {**result, "write_back_allowed": True, "applied": True}


def run_due_fundamental_verifications(
    db: Session,
    *,
    batch_size: int | None = None,
    as_of: datetime | None = None,
) -> dict:
    if not settings.auto_verification_enabled:
        return {"status": "disabled", "processed": 0, "applied": 0}
    now = as_of or datetime.now(timezone.utc)
    retry_cutoff = now - timedelta(hours=settings.auto_verification_retry_hours)
    rows = db.execute(
        select(Prediction)
        .where(
            Prediction.verdict.is_(None),
            Prediction.scoring_eligible.is_(True),
            Prediction.verifier_type == "fundamental_metric",
            or_(Prediction.verifiable_at.is_(None), Prediction.verifiable_at <= now),
            or_(
                Prediction.instrument_snapshot.has_key("manual_correction_reason"),
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                    PredictionMarketVerification.status == "manual_review",
                ),
            ),
            ~exists().where(
                PredictionMarketVerification.prediction_id == Prediction.id,
                PredictionMarketVerification.status.in_(("tracking", "market_data_unavailable")),
                PredictionMarketVerification.created_at >= retry_cutoff,
            ),
        )
        .order_by(Prediction.published_at.asc())
        .limit(batch_size or settings.auto_verification_batch_size)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    stats = {"status": "completed", "processed": 0, "applied": 0, "tracking": 0, "manual_review": 0, "market_data_unavailable": 0}
    for prediction in rows:
        result = verify_fundamental_prediction(db, prediction, as_of=now)
        stats["processed"] += 1
        if result.get("applied"):
            stats["applied"] += 1
        elif result.get("status") in stats:
            stats[str(result["status"])] += 1
    db.commit()
    return stats
