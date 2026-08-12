"""Deterministic validation and normalization for LLM-extracted instruments."""

from __future__ import annotations

import re
import threading
import time
import json
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from loguru import logger

from app.core.config import settings
from app.core.resilience import resilient_tool
from app.models.instrument_correction_rule import InstrumentCorrectionRule


_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,23}$")
_A_SHARE_RE = re.compile(r"^(\d{6})(?:\.(SH|SZ|BJ))?$")
_HK_SHARE_RE = re.compile(r"^(\d{4,5})(?:\.HK)?$")
_CRYPTO_QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "BTC", "ETH")
_COMMON_CRYPTO_ASSETS = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT",
    "LINK", "LTC", "BCH", "TRX", "TON", "SUI", "APT", "ARB", "OP",
}
_SUPPORTED_EQUITY_MARKETS = {"CN", "HK", "US"}
_GOLD_ALIASES = {"XAU", "XAUUSD", "GOLD"}
_WTI_ALIASES = {"WTI", "USOIL"}
_SEC_VERIFIED_COMPANY_ALIASES = {"spacex": "SPCX"}


def is_downstream_verified_ticker(item: Any) -> bool:
    """Return whether a resolved ticker is safe for structured downstream use."""
    if not (
        isinstance(item, dict)
        and bool(str(item.get("symbol") or "").strip())
        and item.get("validation_status") == "verified"
        and item.get("tradable") is True
    ):
        return False
    symbol = str(item.get("symbol") or "").upper()
    market = str(item.get("market") or "").upper()
    asset_type = str(item.get("asset_type") or "").lower()
    return (
        (asset_type == "equity" and market in _SUPPORTED_EQUITY_MARKETS)
        or (asset_type.startswith("crypto") and market == "CRYPTO")
        or (asset_type == "commodity" and market == "COMMODITY" and symbol in {"WTI", "XAU"})
    )


def verified_ticker_symbols(result: dict) -> list[str]:
    """Return unique, verified and tradable symbols from an analysis result."""
    symbols: list[str] = []
    for item in result.get("tickers") or []:
        if not is_downstream_verified_ticker(item):
            continue
        symbol = str(item["symbol"]).upper().strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _apply_legacy_hints(item: dict) -> None:
    """Infer only high-confidence hints missing from historical LLM output."""
    symbol = str(item.get("symbol") or "").strip().lstrip("$").upper()
    item["symbol"] = symbol
    asset_hint = str(item.get("asset_type") or "unknown").lower()
    market_hint = str(item.get("market_hint") or "unknown").upper()
    original_name = str(item.get("original_name") or "").lower()
    for alias, listed_symbol in _SEC_VERIFIED_COMPANY_ALIASES.items():
        if alias in original_name and symbol != listed_symbol:
            listed = _sec_match(listed_symbol)
            if listed:
                item["original_extracted_symbol"] = symbol
                item["symbol"] = listed_symbol
                item["asset_type"] = "equity"
                item["market_hint"] = "US"
                item["alias_resolution"] = "sec_verified_company_alias"
                return
    if symbol in _GOLD_ALIASES:
        item["symbol"] = "XAU"
        item["asset_type"] = "commodity"
        item["market_hint"] = "COMMODITY"
        return
    if symbol in _WTI_ALIASES or (
        symbol == "CL"
        and any(term in original_name for term in ("原油", "油价", "crude oil", "wti", "美油"))
    ):
        item["symbol"] = "WTI"
        item["asset_type"] = "commodity"
        item["market_hint"] = "COMMODITY"
        return
    if asset_hint != "unknown" or market_hint != "UNKNOWN":
        return

    if _A_SHARE_RE.fullmatch(symbol):
        item["asset_type"] = "equity"
        item["market_hint"] = "CN"
    elif _HK_SHARE_RE.fullmatch(symbol):
        item["asset_type"] = "equity"
        item["market_hint"] = "HK"
    elif symbol in _COMMON_CRYPTO_ASSETS or any(
        len(symbol) > len(quote) and symbol.endswith(quote)
        for quote in _CRYPTO_QUOTES
    ):
        item["asset_type"] = "crypto"
        item["market_hint"] = "CRYPTO"


def _cached(key: str, loader: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] < settings.instrument_catalog_cache_seconds:
            return cached[1]
    value = loader()
    with _CACHE_LOCK:
        _CACHE[key] = (now, value)
    return value


@resilient_tool(
    retries=1,
    circuit_name="akshare_instrument_lookup",
    fallback_message="AKShare instrument lookup unavailable",
)
def _load_akshare_catalog(market: str) -> dict[str, dict]:
    import akshare as ak

    if market == "CN_SH_MAIN":
        frame = ak.stock_info_sh_name_code(symbol="主板A股")
        code_column, name_column = "证券代码", "证券简称"
    elif market == "CN_SH_STAR":
        frame = ak.stock_info_sh_name_code(symbol="科创板")
        code_column, name_column = "证券代码", "证券简称"
    elif market == "CN_SZ":
        frame = ak.stock_info_sz_name_code(symbol="A股列表")
        code_column, name_column = "A股代码", "A股简称"
    elif market == "CN_BJ":
        frame = ak.stock_info_bj_name_code()
        code_column, name_column = "证券代码", "证券简称"
    else:
        raise ValueError(f"Unsupported AKShare market: {market}")

    result: dict[str, dict] = {}
    for _, row in frame.iterrows():
        code = str(row[code_column]).zfill(6)
        result[code] = {
            "symbol": code,
            "name": str(row[name_column]),
            "market": "CN",
        }
    return result


@resilient_tool(
    retries=1,
    circuit_name="akshare_hk_instrument_lookup",
    fallback_message="AKShare HK instrument lookup unavailable",
)
def _load_akshare_hk_instrument(symbol: str) -> dict:
    import akshare as ak

    frame = ak.stock_hk_security_profile_em(symbol=symbol)
    if frame is None or frame.empty:
        return {}
    row = frame.iloc[0]
    return {
        "symbol": symbol,
        "name": str(row.get("证券简称") or symbol),
        "market": "HK",
        "exchange": str(row.get("交易所") or ""),
        "isin": str(row.get("ISIN（国际证券识别编码）") or ""),
    }


@resilient_tool(
    retries=2,
    circuit_name="openfigi_mapping",
    fallback_message="OpenFIGI mapping unavailable",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _map_openfigi(symbols: list[str]) -> dict[str, dict]:
    headers = {"Content-Type": "application/json"}
    if settings.openfigi_api_key:
        headers["X-OPENFIGI-APIKEY"] = settings.openfigi_api_key
    chunk_size = 100 if settings.openfigi_api_key else 10
    payload: list[dict] = []
    with httpx.Client(timeout=settings.instrument_api_timeout_seconds) as client:
        for offset in range(0, len(symbols), chunk_size):
            jobs = [
                {"idType": "TICKER", "idValue": symbol, "marketSecDes": "Equity"}
                for symbol in symbols[offset:offset + chunk_size]
            ]
            response = client.post(
                f"{settings.openfigi_base_url.rstrip('/')}/mapping",
                headers=headers,
                json=jobs,
            )
            response.raise_for_status()
            payload.extend(response.json())

    mapped: dict[str, dict] = {}
    for symbol, item in zip(symbols, payload, strict=False):
        candidates = item.get("data") or []
        if not candidates:
            continue
        candidate = next(
            (row for row in candidates if row.get("marketSector") == "Equity"),
            candidates[0],
        )
        mapped[symbol] = candidate
    return mapped


@resilient_tool(
    retries=2,
    circuit_name="sec_company_tickers",
    fallback_message="SEC EDGAR company catalog unavailable",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _load_sec_catalog() -> dict[str, dict]:
    headers = {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
    with httpx.Client(timeout=settings.instrument_api_timeout_seconds) as client:
        response = client.get(settings.sec_company_tickers_url, headers=headers)
        response.raise_for_status()
        payload = response.json()

    fields = payload.get("fields") or []
    rows = payload.get("data") or []
    result: dict[str, dict] = {}
    for values in rows:
        row = dict(zip(fields, values, strict=False))
        symbol = str(row.get("ticker") or "").upper()
        if symbol:
            result[symbol] = row
    return result


@resilient_tool(
    retries=2,
    circuit_name="binance_exchange_info",
    fallback_message="Binance exchangeInfo unavailable",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _load_binance_catalog() -> dict[str, Any]:
    with httpx.Client(timeout=settings.instrument_api_timeout_seconds) as client:
        response = client.get(settings.binance_exchange_info_url)
        response.raise_for_status()
        payload = response.json()

    pairs: dict[str, dict] = {}
    assets: set[str] = set()
    for row in payload.get("symbols") or []:
        if row.get("status") != "TRADING":
            continue
        symbol = str(row.get("symbol") or "").upper()
        base = str(row.get("baseAsset") or "").upper()
        quote = str(row.get("quoteAsset") or "").upper()
        if symbol:
            pairs[symbol] = row
        if base:
            assets.add(base)
        if quote:
            assets.add(quote)
    return {"pairs": pairs, "assets": assets}


def _catalog(name: str, loader: Callable[[], Any]) -> Any | None:
    value = _cached(name, loader)
    if isinstance(value, str):
        logger.warning("Instrument provider {} unavailable: {}", name, value)
        return None
    return value


def _akshare_match(symbol: str) -> dict | None:
    if not settings.akshare_validation_enabled:
        return None

    a_match = _A_SHARE_RE.fullmatch(symbol)
    if a_match:
        code = a_match.group(1)
        if code.startswith(("688", "689")):
            catalog_name = "CN_SH_STAR"
        elif code.startswith(("5", "6", "9")):
            catalog_name = "CN_SH_MAIN"
        elif code.startswith(("4", "8")):
            catalog_name = "CN_BJ"
        else:
            catalog_name = "CN_SZ"
        catalog = _catalog(
            f"akshare_{catalog_name.lower()}",
            lambda: _load_akshare_catalog(catalog_name),
        )
        instrument = catalog.get(code) if catalog else None
        if instrument:
            suffix = a_match.group(2)
            if not suffix:
                suffix = (
                    "SH" if code.startswith(("5", "6", "9"))
                    else "BJ" if code.startswith(("4", "8"))
                    else "SZ"
                )
            return {
                "symbol": f"{code}.{suffix}",
                "market": "CN",
                "name": instrument["name"],
                "source": "akshare",
            }

    hk_match = _HK_SHARE_RE.fullmatch(symbol)
    if hk_match:
        code = hk_match.group(1).zfill(5)
        instrument = _catalog(
            f"akshare_hk_{code}",
            lambda: _load_akshare_hk_instrument(code),
        )
        if instrument:
            match = {
                "symbol": f"{code}.HK",
                "market": "HK",
                "name": instrument["name"],
                "source": "akshare",
            }
            if instrument.get("exchange"):
                match["exchange"] = instrument["exchange"]
            if instrument.get("isin"):
                match["external_ids"] = {"isin": instrument["isin"]}
            return match

    return None


def _binance_match(symbol: str) -> dict | None:
    if not settings.binance_validation_enabled:
        return None
    catalog = _catalog("binance", _load_binance_catalog)
    if catalog is None:
        return None
    if symbol in catalog["pairs"]:
        row = catalog["pairs"][symbol]
        return {
            "symbol": symbol,
            "market": "CRYPTO",
            "name": f"{row['baseAsset']}/{row['quoteAsset']}",
            "source": "binance",
            "asset_type": "crypto_pair",
        }
    if symbol in catalog["assets"]:
        return {
            "symbol": symbol,
            "market": "CRYPTO",
            "name": symbol,
            "source": "binance",
            "asset_type": "crypto_asset",
        }
    return None


def _sec_match(symbol: str) -> dict | None:
    if not settings.sec_edgar_validation_enabled:
        return None
    catalog = _catalog("sec_company_tickers", _load_sec_catalog)
    if catalog is None:
        return None
    row = catalog.get(symbol)
    if not row:
        return None
    return {
        "symbol": symbol,
        "market": "US",
        "name": row.get("name") or "",
        "source": "sec_edgar",
        "external_ids": {"cik": str(row.get("cik") or "")},
        "exchange": row.get("exchange") or "",
    }


def _openfigi_matches(symbols: list[str]) -> dict[str, dict]:
    if not settings.openfigi_validation_enabled or not symbols:
        return {}
    value = _map_openfigi(symbols)
    return value if isinstance(value, dict) else {}


def _commodity_match(symbol: str) -> dict | None:
    if symbol == "WTI":
        return {
            "symbol": "WTI",
            "market": "COMMODITY",
            "name": "WTI Crude Oil Spot Price",
            "source": "eia_pet_rwtc_d",
            "asset_type": "commodity",
            "listing_status": "reference_series",
            "external_ids": {"eia_series_id": settings.eia_wti_series_id},
        }
    if symbol == "XAU" and _binance_match("PAXGUSDT"):
        return {
            "symbol": "XAU",
            "market": "COMMODITY",
            "name": "Gold spot price (PAXG/USDT proxy)",
            "source": "binance_paxg_proxy",
            "asset_type": "commodity",
            "listing_status": "proxy_reference",
            "external_ids": {"price_proxy_symbol": "PAXGUSDT"},
            "price_proxy_symbol": "PAXGUSDT",
            "price_proxy_disclosure": "黄金价格采用 PAXG/USDT 作为现货黄金代理，不代表 LBMA 官方定盘价",
        }
    return None


def _apply_human_correction_rules(analyses: list[dict], db: Any) -> None:
    if db is None:
        return
    symbols = {
        str(item.get("symbol") or "").strip().lstrip("$").upper()
        for analysis in analyses
        for item in (analysis.get("tickers") or [])
        if isinstance(item, dict)
    }
    if not symbols:
        return
    rules = db.query(InstrumentCorrectionRule).filter(
        InstrumentCorrectionRule.active.is_(True),
        InstrumentCorrectionRule.source_symbol.in_(symbols),
    ).all()
    by_symbol: dict[str, list[InstrumentCorrectionRule]] = {}
    for rule in rules:
        by_symbol.setdefault(rule.source_symbol.upper(), []).append(rule)

    for analysis in analyses:
        context = json.dumps(analysis, ensure_ascii=False).lower()
        for item in analysis.get("tickers") or []:
            if not isinstance(item, dict):
                continue
            source_symbol = str(item.get("symbol") or "").upper()
            for rule in by_symbol.get(source_symbol, []):
                terms = [str(term).strip().lower() for term in (rule.context_terms or []) if str(term).strip()]
                if terms and not any(term in context for term in terms):
                    continue
                corrected = dict(rule.corrected_instrument or {})
                if not corrected.get("symbol"):
                    continue
                original_name = item.get("original_name")
                item.update(corrected)
                item["original_name"] = original_name or corrected.get("resolved_name", "")
                item["original_extracted_symbol"] = source_symbol
                item["correction_rule_id"] = str(rule.id)
                item["validation_sources"] = list(dict.fromkeys([
                    *(corrected.get("validation_sources") or []),
                    "human_correction_rule",
                ]))
                break


def resolve_analysis_tickers(analyses: list[dict], db: Any = None) -> list[dict]:
    """Validate extracted candidates and enrich them without blocking analysis."""
    if not settings.instrument_validation_enabled:
        return analyses

    candidate_items = [
        item
        for analysis in analyses
        for item in (analysis.get("tickers") or [])
        if isinstance(item, dict)
    ]
    for item in candidate_items:
        _apply_legacy_hints(item)
    candidates = {
        str(item.get("symbol") or "").strip().lstrip("$").upper()
        for item in candidate_items
    }
    non_equity_symbols = {
        str(item.get("symbol") or "").strip().lstrip("$").upper()
        for item in candidate_items
        if item.get("asset_type") not in (None, "unknown", "equity")
        or item.get("market_hint") == "CRYPTO"
    }
    figi_symbols = sorted(
        symbol
        for item in candidate_items
        for symbol in [str(item.get("symbol") or "").strip().lstrip("$").upper()]
        if _SYMBOL_RE.fullmatch(symbol)
        and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol)
        and symbol not in non_equity_symbols
        and (
            item.get("asset_type") == "equity"
            or item.get("market_hint") in {"US", "GLOBAL"}
        )
    )
    figi_map = _openfigi_matches(figi_symbols)
    validated_at = datetime.now(timezone.utc).isoformat()

    for analysis in analyses:
        rejected: list[dict] = []
        resolved: list[dict] = []
        for ticker in analysis.get("tickers") or []:
            if not isinstance(ticker, dict):
                rejected.append({"raw": ticker, "reason": "not_an_object"})
                continue
            symbol = str(ticker.get("symbol") or "").strip().lstrip("$").upper()
            if not _SYMBOL_RE.fullmatch(symbol):
                rejected.append({"raw": symbol, "reason": "invalid_symbol_format"})
                continue

            asset_hint = ticker.get("asset_type", "unknown")
            market_hint = ticker.get("market_hint", "unknown")
            is_crypto_hint = asset_hint == "crypto" or market_hint == "CRYPTO"
            if is_crypto_hint:
                match = _binance_match(symbol)
            elif asset_hint == "commodity" or market_hint == "COMMODITY":
                match = _commodity_match(symbol)
            elif asset_hint in {"index", "forex"}:
                match = None
            else:
                if market_hint == "US" or re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
                    match = _sec_match(symbol) or _akshare_match(symbol)
                else:
                    match = _akshare_match(symbol) or _sec_match(symbol)
                if match is None and asset_hint == "unknown" and market_hint == "unknown":
                    match = _binance_match(symbol)
            sources: list[str] = []
            external_ids: dict[str, str] = {}
            if match:
                sources.append(match["source"])
                external_ids.update(match.get("external_ids") or {})

            sec = None
            if not is_crypto_hint and (market_hint == "US" or (match and match.get("market") == "US")):
                sec = _sec_match(symbol)
                if sec:
                    sources.append("sec_edgar")
                    external_ids.update(sec.get("external_ids") or {})

            figi = None if is_crypto_hint else figi_map.get(symbol)
            if figi:
                sources.append("openfigi")
                if figi.get("figi"):
                    external_ids["figi"] = figi["figi"]

            if match:
                ticker["symbol"] = match["symbol"]
                ticker["market"] = match["market"]
                ticker["asset_type"] = match.get("asset_type", "equity")
                ticker["resolved_name"] = match.get("name", "")
                ticker["listing_status"] = "listed"
                ticker["tradable"] = True
                if not ticker.get("original_name"):
                    ticker["original_name"] = match.get("name", "")
                if match.get("exchange"):
                    ticker["exchange"] = match["exchange"]
                if match.get("listing_status"):
                    ticker["listing_status"] = match["listing_status"]
                if match.get("price_proxy_symbol"):
                    ticker["price_proxy_symbol"] = match["price_proxy_symbol"]
                    ticker["price_proxy_disclosure"] = match["price_proxy_disclosure"]
            elif figi:
                ticker["symbol"] = str(figi.get("ticker") or symbol).upper()
                ticker["market"] = figi.get("exchCode") or "GLOBAL"
                ticker["asset_type"] = "equity"
                ticker["resolved_name"] = figi.get("name") or ""
                ticker["listing_status"] = "listed"
                ticker["tradable"] = True
                if not ticker.get("original_name"):
                    ticker["original_name"] = figi.get("name") or ""
            else:
                ticker["market"] = market_hint if market_hint != "unknown" else "UNKNOWN"
                ticker["asset_type"] = asset_hint
                ticker["listing_status"] = "unverified"
                ticker["tradable"] = False

            ticker["validation_status"] = "verified" if sources else "unverified"
            ticker["validation_sources"] = list(dict.fromkeys(sources))
            ticker["external_ids"] = external_ids
            ticker["validated_at"] = validated_at
            resolved.append(ticker)

        analysis["tickers"] = resolved
        if rejected:
            analysis["rejected_tickers"] = rejected
    _apply_human_correction_rules(analyses, db)
    return analyses


def validate_instrument_candidate(
    *,
    symbol: str,
    name: str,
    asset_type: str,
    market: str,
) -> dict:
    """Validate one administrator-supplied correction before it is stored."""
    normalized = symbol.strip().lstrip("$").upper()
    if not _SYMBOL_RE.fullmatch(normalized):
        return {"accepted": False, "reason": "标的代码格式无效"}

    if asset_type == "commodity" and market == "COMMODITY":
        if normalized in _GOLD_ALIASES:
            normalized = "XAU"
        elif normalized in _WTI_ALIASES:
            normalized = "WTI"
        if normalized not in {"WTI", "XAU"}:
            return {
                "accepted": False,
                "reason": "当前商品行情只支持 WTI 原油和 XAU 黄金",
            }
        match = _commodity_match(normalized)
        if not match:
            return {"accepted": False, "reason": "黄金代理行情 PAXGUSDT 当前不可用"}
        is_gold = normalized == "XAU"
        return {
            "accepted": True,
            "reason": (
                "已映射到 Binance PAXGUSDT 黄金代理行情"
                if is_gold
                else "已映射到 EIA WTI 日度现货价格序列 PET.RWTC.D"
            ),
            "instrument": {
                **match,
                "original_name": name.strip(),
                "resolved_name": match["name"],
                "validation_status": "verified",
                "tradable": True,
                "validation_sources": [match["source"]],
                "validated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    if market == "OTHER" or asset_type == "other":
        return {
            "accepted": True,
            "reason": "已记录为人工确认的非上市/非行情标的，不参与自动收益验证",
            "instrument": {
                "symbol": normalized,
                "original_name": name.strip(),
                "resolved_name": name.strip(),
                "asset_type": asset_type,
                "market": market,
                "validation_status": "manual_corrected",
                "tradable": False,
                "listing_status": "unlisted_or_unknown",
                "validation_sources": ["manual_correction"],
                "validated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    analyses = [{
        "tickers": [{
            "symbol": normalized,
            "original_name": name.strip(),
            "asset_type": asset_type,
            "market_hint": market,
        }]
    }]
    resolved = resolve_analysis_tickers(analyses)[0]["tickers"][0]
    accepted = is_downstream_verified_ticker(resolved)
    return {
        "accepted": accepted,
        "reason": (
            "已通过公开证券/交易所数据源校验"
            if accepted
            else "公开证券/交易所数据源未能确认该标的"
        ),
        "instrument": resolved,
    }
