"""Auditable instrument and market-data verification for predictions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from loguru import logger
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.resilience import resilient_tool
from app.models.analysis import AnalysisResult
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.models.tweet import Tweet
from app.services.credibility import recompute_blogger
from app.services.instrument_resolver import is_downstream_verified_ticker


MARKET_TIMEZONES = {
    "CN": ZoneInfo("Asia/Shanghai"),
    "HK": ZoneInfo("Asia/Hong_Kong"),
    "US": ZoneInfo("America/New_York"),
}
MARKET_CLOSE_TIMES = {"CN": time(15, 0), "HK": time(16, 0), "US": time(16, 0)}
MARKET_OPEN_TIMES = {"CN": time(9, 30), "HK": time(9, 30), "US": time(9, 30)}
HORIZON_THRESHOLDS = {
    "short": lambda: settings.auto_verification_short_return_threshold,
    "medium": lambda: settings.auto_verification_medium_return_threshold,
    "long": lambda: settings.auto_verification_long_return_threshold,
    "unknown": lambda: settings.auto_verification_medium_return_threshold,
}
GOLD_HORIZON_THRESHOLDS = {
    "short": lambda: settings.gold_verification_short_return_threshold,
    "medium": lambda: settings.gold_verification_medium_return_threshold,
    "long": lambda: settings.gold_verification_long_return_threshold,
    "unknown": lambda: settings.gold_verification_medium_return_threshold,
}
AUTO_VERIFICATION_RULE_VERSION = "market_auto_v1"


@dataclass(frozen=True)
class PricePoint:
    observed_at: str
    price: float


@dataclass(frozen=True)
class PriceWindow:
    source: str
    symbol: str
    start: PricePoint
    end: PricePoint


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _frame_records(frame: Any) -> list[dict]:
    if frame is None or getattr(frame, "empty", True):
        return []
    return frame.to_dict("records")


@resilient_tool(
    retries=1,
    circuit_name="market_price_cn",
    fallback_message="A-share historical prices unavailable",
)
def _load_cn_prices(symbol: str, start_date: date, end_date: date) -> list[dict]:
    import akshare as ak

    frame = ak.stock_zh_a_hist(
        symbol=symbol.split(".")[0],
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust="qfq",
        timeout=settings.instrument_api_timeout_seconds,
    )
    return _frame_records(frame)


@resilient_tool(
    retries=1,
    circuit_name="market_price_hk",
    fallback_message="Hong Kong historical prices unavailable",
)
def _load_hk_prices(symbol: str, start_date: date, end_date: date) -> list[dict]:
    import akshare as ak

    frame = ak.stock_hk_hist(
        symbol=symbol.split(".")[0].zfill(5),
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust="qfq",
    )
    return _frame_records(frame)


@resilient_tool(
    retries=1,
    circuit_name="market_price_us",
    fallback_message="US historical prices unavailable",
)
def _load_us_prices(symbol: str) -> list[dict]:
    import akshare as ak

    frame = ak.stock_us_daily(symbol=symbol, adjust="qfq")
    return _frame_records(frame)


@resilient_tool(
    retries=2,
    circuit_name="market_price_binance",
    fallback_message="Binance historical prices unavailable",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _load_binance_edge_bar(
    pair: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list:
    params: dict[str, Any] = {"symbol": pair, "interval": "1h", "limit": 1}
    if start_ms is not None:
        params["startTime"] = start_ms
    if end_ms is not None:
        params["endTime"] = end_ms
    with httpx.Client(timeout=settings.instrument_api_timeout_seconds) as client:
        response = client.get(settings.binance_klines_url, params=params)
        response.raise_for_status()
        return response.json()


@resilient_tool(
    retries=2,
    circuit_name="market_price_eia_wti",
    fallback_message="EIA WTI daily prices unavailable",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _load_eia_wti_prices(start_date: date, end_date: date) -> list[dict]:
    if not settings.eia_api_key:
        raise ValueError("EIA_API_KEY is required for WTI market verification")
    url = f"{settings.eia_base_url.rstrip('/')}/petroleum/pri/spt/data/"
    params = {
        "api_key": settings.eia_api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": "RWTC",
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }
    with httpx.Client(timeout=settings.instrument_api_timeout_seconds) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    return list((payload.get("response") or {}).get("data") or [])


def _record_date(row: dict) -> date:
    raw = row.get("日期", row.get("date"))
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return datetime.fromisoformat(str(raw)).date()


def _completed_market_date(market: str, as_of: datetime) -> date:
    tz = MARKET_TIMEZONES[market]
    local = _as_utc(as_of).astimezone(tz)
    if local.time() < MARKET_CLOSE_TIMES[market]:
        return local.date() - timedelta(days=1)
    return local.date()


def _stock_price_window(
    symbol: str,
    market: str,
    published_at: datetime,
    end_at: datetime,
) -> PriceWindow:
    tz = MARKET_TIMEZONES[market]
    published_local = _as_utc(published_at).astimezone(tz)
    first_possible_date = (
        published_local.date()
        if published_local.time() < MARKET_OPEN_TIMES[market]
        else published_local.date() + timedelta(days=1)
    )
    last_completed_date = _completed_market_date(market, end_at)
    if last_completed_date < first_possible_date:
        raise ValueError("No completed trading session exists after publication")

    query_start = first_possible_date - timedelta(days=3)
    query_end = last_completed_date + timedelta(days=1)
    if market == "CN":
        rows = _load_cn_prices(symbol, query_start, query_end)
        source = "AKShare/Eastmoney A-share"
    elif market == "HK":
        rows = _load_hk_prices(symbol, query_start, query_end)
        source = "AKShare/Eastmoney Hong Kong"
    elif market == "US":
        rows = _load_us_prices(symbol)
        source = "AKShare US daily"
    else:
        raise ValueError(f"Unsupported stock market: {market}")
    if isinstance(rows, str):
        raise RuntimeError(rows)

    eligible = [
        row for row in rows
        if first_possible_date <= _record_date(row) <= last_completed_date
    ]
    if not eligible:
        raise ValueError("No usable completed market bars in verification window")
    eligible.sort(key=_record_date)
    start_row, end_row = eligible[0], eligible[-1]
    start_price = float(start_row.get("开盘", start_row.get("open")))
    end_price = float(end_row.get("收盘", end_row.get("close")))
    return PriceWindow(
        source=source,
        symbol=symbol,
        start=PricePoint(_record_date(start_row).isoformat(), start_price),
        end=PricePoint(_record_date(end_row).isoformat(), end_price),
    )


def _crypto_pair(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol.endswith(("USDT", "USDC", "FDUSD")) and len(symbol) > 4:
        return symbol
    return f"{symbol}USDT"


def _crypto_price_window(symbol: str, published_at: datetime, end_at: datetime) -> PriceWindow:
    start_utc = _as_utc(published_at)
    start_hour = start_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    end_utc = _as_utc(end_at).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    if end_utc < start_hour:
        raise ValueError("No completed crypto bar exists after publication")
    pair = _crypto_pair(symbol)
    start_rows = _load_binance_edge_bar(pair, start_ms=int(start_hour.timestamp() * 1000))
    end_rows = _load_binance_edge_bar(pair, end_ms=int((end_utc + timedelta(hours=1)).timestamp() * 1000) - 1)
    if isinstance(start_rows, str):
        raise RuntimeError(start_rows)
    if isinstance(end_rows, str):
        raise RuntimeError(end_rows)
    if not start_rows or not end_rows:
        raise ValueError(f"No Binance hourly bars for {pair}")
    start_row, end_row = start_rows[0], end_rows[-1]
    return PriceWindow(
        source="Binance public klines",
        symbol=pair,
        start=PricePoint(
            datetime.fromtimestamp(start_row[0] / 1000, timezone.utc).isoformat(),
            float(start_row[1]),
        ),
        end=PricePoint(
            datetime.fromtimestamp(end_row[6] / 1000, timezone.utc).isoformat(),
            float(end_row[4]),
        ),
    )


def _gold_price_window(published_at: datetime, end_at: datetime) -> PriceWindow:
    start_utc = _as_utc(published_at)
    start_hour = start_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    end_utc = _as_utc(end_at).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    if end_utc < start_hour:
        raise ValueError("No completed PAXG/USDT bar exists after publication")
    pair = "PAXGUSDT"
    start_rows = _load_binance_edge_bar(pair, start_ms=int(start_hour.timestamp() * 1000))
    end_rows = _load_binance_edge_bar(
        pair,
        end_ms=int((end_utc + timedelta(hours=1)).timestamp() * 1000) - 1,
    )
    if isinstance(start_rows, str):
        raise RuntimeError(start_rows)
    if isinstance(end_rows, str):
        raise RuntimeError(end_rows)
    if not start_rows or not end_rows:
        raise ValueError("No Binance hourly bars for PAXGUSDT")
    start_row, end_row = start_rows[0], end_rows[-1]
    return PriceWindow(
        source="Binance PAXG/USDT gold price proxy",
        symbol=pair,
        start=PricePoint(
            datetime.fromtimestamp(start_row[0] / 1000, timezone.utc).isoformat(),
            float(start_row[1]),
        ),
        end=PricePoint(
            datetime.fromtimestamp(end_row[6] / 1000, timezone.utc).isoformat(),
            float(end_row[4]),
        ),
    )


def _commodity_price_window(
    symbol: str,
    published_at: datetime,
    end_at: datetime,
) -> PriceWindow:
    if symbol.upper() != "WTI":
        raise ValueError(f"Unsupported commodity reference series: {symbol}")
    first_date = _as_utc(published_at).date()
    last_date = _as_utc(end_at).date()
    if last_date < first_date:
        raise ValueError("No WTI observation window exists after publication")
    rows = _load_eia_wti_prices(
        first_date - timedelta(days=3),
        last_date + timedelta(days=1),
    )
    if isinstance(rows, str):
        raise RuntimeError(rows)
    eligible = []
    for row in rows:
        try:
            observed = datetime.fromisoformat(str(row.get("period"))).date()
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if first_date <= observed <= last_date:
            eligible.append((observed, value))
    if not eligible:
        raise ValueError("No EIA WTI daily observations in verification window")
    eligible.sort(key=lambda item: item[0])
    start, end = eligible[0], eligible[-1]
    return PriceWindow(
        source="U.S. EIA WTI spot daily PET.RWTC.D",
        symbol="WTI",
        start=PricePoint(start[0].isoformat(), start[1]),
        end=PricePoint(end[0].isoformat(), end[1]),
    )


def _matching_ticker(analysis: AnalysisResult | None, symbol: str) -> dict | None:
    if not analysis or not analysis.result:
        return None
    for item in analysis.result.get("tickers") or []:
        if isinstance(item, dict) and str(item.get("symbol") or "").upper() == symbol.upper():
            return item
    return None


def _prediction_ticker(
    analysis: AnalysisResult | None,
    prediction: Prediction,
) -> dict | None:
    if prediction.instrument_snapshot:
        return prediction.instrument_snapshot
    return _matching_ticker(analysis, prediction.ticker)


def _identity_gate(ticker: dict, tweet_content: str) -> tuple[bool, str]:
    symbol = str(ticker.get("symbol") or "").upper()
    base_symbol = symbol.split(".")[0]
    exact_pattern = rf"(?<![A-Z0-9])\$?{re.escape(base_symbol)}(?![A-Z0-9])"
    if re.search(exact_pattern, tweet_content.upper()):
        return True, "原文直接出现标准代码"

    original = str(ticker.get("original_name") or "").strip().lower()
    resolved = str(ticker.get("resolved_name") or "").strip().lower()
    if resolved and original and (original in resolved or resolved in original):
        return True, "原文名称与行情标的正式名称一致"

    conflict_terms = {
        "commodity_alias_as_equity": ("原油", "油价", "crude oil", "wti", "布伦特"),
        "private_company_alias": ("openai", "anthropic"),
    }
    # Conflict rules are scoped to this ticker's extracted name. A tweet can
    # legitimately discuss SpaceX and NVDA together; the other entity must not
    # invalidate an explicitly extracted NVDA ticker.
    combined = original
    if ticker.get("asset_type") == "equity" and any(
        term in combined for term in conflict_terms["commodity_alias_as_equity"]
    ):
        return False, "原文语义指向商品，但代码被解析为同名股票"
    if ticker.get("asset_type") == "equity" and "spacex" in combined and symbol != "SPCX":
        return False, "原文指向 SpaceX，公开交易代码应核验为 SPCX"
    if ticker.get("asset_type") == "equity" and any(
        term in combined for term in conflict_terms["private_company_alias"]
    ):
        return False, "原文语义指向未上市公司，不能用相关上市公司行情代替"
    if symbol == "COIN" and any(term in combined for term in ("circle", "usdc")):
        return False, "原文语义指向 Circle/USDC，不能用 Coinbase 行情代替"

    if ticker.get("validation_sources"):
        return True, "标准代码已由公开数据源核验，未发现明确语义冲突"
    return False, "代码由别名或语义推断，尚未证明与行情标的是同一资产"


def _verdict(
    sentiment: str,
    raw_return: float,
    horizon: str,
    *,
    is_gold: bool = False,
) -> tuple[str, float, float]:
    thresholds = GOLD_HORIZON_THRESHOLDS if is_gold else HORIZON_THRESHOLDS
    threshold = thresholds.get(horizon, thresholds["unknown"])()
    directional_return = raw_return if sentiment == "bullish" else -raw_return
    if directional_return >= threshold:
        return "correct", 1.0, threshold
    if directional_return > 0:
        return "partial", 0.5, threshold
    return "incorrect", 0.0, threshold


def preview_prediction_identity(
    db: Session,
    prediction: Prediction,
) -> dict | None:
    """Return a manual-review result when a prediction cannot map to one asset."""
    analysis = db.get(AnalysisResult, prediction.analysis_id)
    tweet = db.get(Tweet, prediction.tweet_id)
    ticker = _prediction_ticker(analysis, prediction)
    base = {
        "prediction_id": str(prediction.id),
        "ticker": prediction.ticker,
        "sentiment": prediction.sentiment,
        "horizon": prediction.investment_horizon,
        "published_at": prediction.published_at.isoformat(),
        "verifiable_at": prediction.verifiable_at.isoformat(),
        "is_due": _as_utc(prediction.verifiable_at) <= datetime.now(timezone.utc),
        "write_back_allowed": False,
    }
    identity = {
        "symbol": str((ticker or {}).get("symbol") or prediction.ticker).upper(),
        "original_name": (ticker or {}).get("original_name"),
        "resolved_name": (ticker or {}).get("resolved_name"),
        "market": (ticker or {}).get("market"),
        "validation_status": (ticker or {}).get("validation_status"),
        "validation_sources": (ticker or {}).get("validation_sources") or [],
    }
    if prediction.sentiment not in {"bullish", "bearish"}:
        return {
            **base,
            "status": "excluded_non_directional",
            "review_type": "non_directional",
            "reason": "中性观点不构成可计分预测，系统自动排除",
            "identity": identity,
        }
    is_manual_instrument = bool(
        prediction.instrument_snapshot
        and prediction.instrument_snapshot.get("validation_status")
        == "manual_corrected"
    )
    if not ticker or (not is_downstream_verified_ticker(ticker) and not is_manual_instrument):
        return {
            **base,
            "status": "manual_review",
            "review_type": "instrument_identity",
            "reason": "标的未通过下游核验门槛",
            "identity": identity,
        }
    identity_ok, identity_reason = _identity_gate(ticker, tweet.content if tweet else "")
    if not identity_ok:
        return {
            **base,
            "status": "manual_review",
            "review_type": "instrument_identity",
            "reason": identity_reason,
            "identity": identity,
        }
    return None


def _identity_tracking_result(
    prediction: Prediction,
    ticker: dict,
) -> dict:
    """Record that identity passed once so future batches do not rescan it."""
    return {
        "prediction_id": str(prediction.id),
        "ticker": prediction.ticker,
        "sentiment": prediction.sentiment,
        "horizon": prediction.investment_horizon,
        "published_at": prediction.published_at.isoformat(),
        "verifiable_at": prediction.verifiable_at.isoformat(),
        "is_due": _as_utc(prediction.verifiable_at) <= datetime.now(timezone.utc),
        "write_back_allowed": False,
        "status": "tracking",
        "review_type": "instrument_identity",
        "reason": "标的身份已核验，等待行情验证时间",
        "identity": {
            "symbol": str(ticker.get("symbol") or prediction.ticker).upper(),
            "original_name": ticker.get("original_name"),
            "resolved_name": ticker.get("resolved_name"),
            "market": ticker.get("market"),
            "validation_status": ticker.get("validation_status"),
            "validation_sources": ticker.get("validation_sources") or [],
        },
    }


def preview_prediction_verification(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    """Build a read-only, auditable market verification result."""
    as_of = _as_utc(as_of or datetime.now(timezone.utc))
    analysis = db.get(AnalysisResult, prediction.analysis_id)
    tweet = db.get(Tweet, prediction.tweet_id)
    ticker = _prediction_ticker(analysis, prediction)
    base = {
        "prediction_id": str(prediction.id),
        "ticker": prediction.ticker,
        "sentiment": prediction.sentiment,
        "horizon": prediction.investment_horizon,
        "published_at": prediction.published_at.isoformat(),
        "verifiable_at": prediction.verifiable_at.isoformat(),
        "as_of": as_of.isoformat(),
        "is_due": _as_utc(prediction.verifiable_at) <= as_of,
        "write_back_allowed": False,
    }
    if prediction.verdict is not None:
        return {**base, "status": "already_verified", "reason": "已有正式验证结果"}
    identity_result = preview_prediction_identity(db, prediction)
    if identity_result:
        return {**base, **identity_result, "as_of": as_of.isoformat()}
    identity_ok, identity_reason = _identity_gate(ticker, tweet.content if tweet else "")

    market = str(ticker.get("market") or "").upper()
    base["market"] = market
    end_at = min(as_of, _as_utc(prediction.verifiable_at))
    try:
        if market == "CRYPTO" or str(ticker.get("asset_type") or "").startswith("crypto"):
            window = _crypto_price_window(prediction.ticker, prediction.published_at, end_at)
        elif market == "COMMODITY" or ticker.get("asset_type") == "commodity":
            if prediction.ticker.upper() == "XAU":
                window = _gold_price_window(prediction.published_at, end_at)
                base["price_proxy"] = {
                    "business_symbol": "XAU",
                    "provider_symbol": "PAXGUSDT",
                    "disclosure": "黄金价格采用 PAXG/USDT 作为现货黄金代理，不代表 LBMA 官方定盘价",
                }
            else:
                window = _commodity_price_window(
                    prediction.ticker, prediction.published_at, end_at
                )
        else:
            window = _stock_price_window(prediction.ticker, market, prediction.published_at, end_at)
    except Exception as exc:
        logger.warning("Market verification preview failed for {}: {}", prediction.id, exc)
        return {
            **base,
            "status": "market_data_unavailable",
            "review_type": "market_data",
            "identity": {
                "symbol": str(ticker.get("symbol") or prediction.ticker).upper(),
                "original_name": ticker.get("original_name"),
                "resolved_name": ticker.get("resolved_name"),
                "market": ticker.get("market"),
                "validation_status": ticker.get("validation_status"),
                "validation_sources": ticker.get("validation_sources") or [],
            },
            "reason": str(exc),
        }

    raw_return = window.end.price / window.start.price - 1
    verdict, score, threshold = _verdict(
        prediction.sentiment,
        raw_return,
        prediction.investment_horizon,
        is_gold=prediction.ticker.upper() == "XAU",
    )
    return {
        **base,
        "status": "ready" if base["is_due"] else "tracking",
        "identity_reason": identity_reason,
        "price_window": asdict(window),
        "raw_return": round(raw_return, 6),
        "directional_return": round(raw_return if prediction.sentiment == "bullish" else -raw_return, 6),
        "threshold": threshold,
        "preview_verdict": verdict,
        "preview_score": score,
        "reason": (
            "已到验证时间，可进入正式写回"
            if base["is_due"]
            else "尚未到验证时间，仅显示期间表现"
        ),
    }


def _audit_from_result(
    prediction: Prediction,
    result: dict,
) -> PredictionMarketVerification:
    window = result.get("price_window") or {}
    identity = result.get("identity") or {}
    validation_sources = identity.get("validation_sources") or []
    start = window.get("start") or {}
    end = window.get("end") or {}
    status = str(result.get("status") or "market_data_unavailable")
    review_type = result.get("review_type")
    rule_version = (
        "system_non_directional_v1"
        if status == "excluded_non_directional"
        else "instrument_identity_v1"
        if review_type == "instrument_identity"
        else AUTO_VERIFICATION_RULE_VERSION
    )
    return PredictionMarketVerification(
        prediction_id=prediction.id,
        status=status,
        provider=window.get("source") or (validation_sources[0] if validation_sources else None),
        provider_symbol=window.get("symbol") or identity.get("symbol") or prediction.ticker,
        market=result.get("market") or identity.get("market"),
        start_observed_at=start.get("observed_at"),
        start_price=start.get("price"),
        end_observed_at=end.get("observed_at"),
        end_price=end.get("price"),
        raw_return=result.get("raw_return"),
        directional_return=result.get("directional_return"),
        threshold=result.get("threshold"),
        proposed_verdict=result.get("preview_verdict"),
        proposed_score=result.get("preview_score"),
        rule_version=rule_version,
        evidence=result,
        applied=bool(result.get("applied", False)),
        applied_at=result.get("applied_at"),
        error_message=(
            str(result.get("reason"))
            if status in {"manual_review", "market_data_unavailable"}
            else None
        ),
    )


def verify_due_prediction(
    db: Session,
    prediction: Prediction,
    *,
    as_of: datetime | None = None,
) -> dict:
    """Verify one due prediction and atomically persist its evidence and verdict."""
    now = _as_utc(as_of or datetime.now(timezone.utc))
    if prediction.verdict is not None:
        return {"prediction_id": str(prediction.id), "status": "already_verified"}
    if _as_utc(prediction.verifiable_at) > now:
        return {"prediction_id": str(prediction.id), "status": "not_due"}

    result = preview_prediction_verification(db, prediction, as_of=now)
    audit = _audit_from_result(prediction, result)
    db.add(audit)

    if result.get("status") != "ready":
        db.flush()
        return result

    prediction.verdict = str(result["preview_verdict"])
    prediction.score = float(result["preview_score"])
    prediction.verified_at = now
    prediction.verified_by = AUTO_VERIFICATION_RULE_VERSION
    prediction.note = (
        f"{audit.provider} {audit.provider_symbol}: "
        f"{audit.start_price} -> {audit.end_price}; "
        f"directional_return={float(audit.directional_return or 0):.2%}; "
        f"threshold={float(audit.threshold or 0):.2%}"
    )
    audit.applied = True
    audit.applied_at = now
    recompute_blogger(db, prediction.blogger_handle)
    db.flush()
    return {**result, "write_back_allowed": True, "applied": True}


def run_due_market_verifications(
    db: Session,
    *,
    batch_size: int | None = None,
    as_of: datetime | None = None,
) -> dict:
    """Lock and verify one batch of predictions whose horizon has elapsed."""
    if not settings.auto_verification_enabled:
        return {"status": "disabled", "processed": 0, "applied": 0}

    now = _as_utc(as_of or datetime.now(timezone.utc))
    limit = batch_size or settings.auto_verification_batch_size
    retry_cutoff = now - timedelta(hours=settings.auto_verification_retry_hours)
    review_candidates = db.execute(
        select(Prediction)
        .where(
            Prediction.verdict.is_(None),
            or_(
                ~Prediction.sentiment.in_(("bullish", "bearish")),
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                ),
            ),
        )
        .order_by(Prediction.published_at.asc())
        .limit(limit)
    ).scalars().all()
    manual_review_queued = 0
    non_directional_excluded = 0
    affected_bloggers: set[str] = set()
    for candidate in review_candidates:
        identity_result = preview_prediction_identity(db, candidate)
        if identity_result is None:
            analysis = db.get(AnalysisResult, candidate.analysis_id)
            ticker = _prediction_ticker(analysis, candidate)
            if ticker and _as_utc(candidate.verifiable_at) > now:
                db.add(_audit_from_result(candidate, _identity_tracking_result(candidate, ticker)))
            continue

        audit = _audit_from_result(candidate, identity_result)
        if identity_result.get("status") == "excluded_non_directional":
            now_applied = now
            candidate.verdict = "excluded"
            candidate.score = None
            candidate.verified_at = now_applied
            candidate.verified_by = "system_non_directional_v1"
            candidate.note = str(identity_result.get("reason") or "中性观点不构成可计分预测")
            audit.applied = True
            audit.applied_at = now_applied
            affected_bloggers.add(candidate.blogger_handle)
            non_directional_excluded += 1
        else:
            manual_review_queued += 1
        db.add(audit)

    for handle in affected_bloggers:
        recompute_blogger(db, handle)
    db.flush()

    predictions = db.execute(
        select(Prediction)
        .where(
            Prediction.verdict.is_(None),
            Prediction.verifiable_at <= now,
            or_(
                Prediction.instrument_snapshot.is_not(None),
                ~exists().where(
                    PredictionMarketVerification.prediction_id == Prediction.id,
                    PredictionMarketVerification.status == "manual_review",
                ),
            ),
            ~exists().where(
                PredictionMarketVerification.prediction_id == Prediction.id,
                PredictionMarketVerification.status == "market_data_unavailable",
                PredictionMarketVerification.created_at >= retry_cutoff,
            ),
        )
        .order_by(Prediction.verifiable_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).scalars().all()

    stats = {
        "status": "completed",
        "processed": 0,
        "applied": 0,
        "manual_review": 0,
        "market_data_unavailable": 0,
        "manual_review_queued": manual_review_queued,
        "non_directional_excluded": non_directional_excluded,
    }
    for prediction in predictions:
        result = verify_due_prediction(db, prediction, as_of=now)
        stats["processed"] += 1
        status = str(result.get("status") or "")
        if result.get("applied"):
            stats["applied"] += 1
        elif status in stats:
            stats[status] += 1

    db.commit()
    logger.info("Automatic market verification batch: {}", stats)
    return stats
