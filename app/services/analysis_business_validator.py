"""Deterministic business validation for model-produced tweet analyses.

Models extract semantic candidates.  This module decides whether those
candidates satisfy the product contract before they can reach canonical claims,
consensus aggregation, predictions, or search indexes.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
from typing import Any

from loguru import logger


BUSINESS_VALIDATION_VERSION = "v1"

_SUPPORTED_MARKETS = {"CN", "HK", "US", "COMMODITY", "CRYPTO"}
_STANCE_CLAIM_TYPES = {"recommendation", "prediction", "opinion"}
_NON_STANCE_CLAIM_TYPES = {"fact", "news", "recap", "reference", "risk_warning"}
_DIRECTIONAL = {"bullish", "bearish", "neutral"}

_BENCHMARKS: dict[str, dict[str, Any]] = {
    "SOX": {
        "market": "US",
        "name": "PHLX Semiconductor Sector Index",
        "context_terms": (
            "费城半导体",
            "半导体",
            "芯片",
            "PHLX",
            "SEMICONDUCTOR",
            "MU",
            "NVDA",
            "AMD",
            "INTC",
            "TSM",
            "AVGO",
        ),
    },
    "SPX": {"market": "US", "name": "S&P 500 Index"},
    "SP500": {"market": "US", "name": "S&P 500 Index"},
    "NDX": {"market": "US", "name": "Nasdaq-100 Index"},
    "DJI": {"market": "US", "name": "Dow Jones Industrial Average"},
    "VIX": {"market": "US", "name": "CBOE Volatility Index"},
    "US10Y": {"market": "US", "name": "US 10-Year Treasury Yield"},
    "HSI": {"market": "HK", "name": "Hang Seng Index"},
    "HSCEI": {"market": "HK", "name": "Hang Seng China Enterprises Index"},
}

_MARKET_PSEUDO_INSTRUMENTS: dict[str, dict[str, str]] = {
    "US_EQUITIES": {"market": "US", "name": "美国股票市场"},
    "STORAGE_SECTOR": {"market": "US", "name": "存储芯片行业"},
    "SEMI": {"market": "US", "name": "半导体行业"},
}

_INDEX_NAME_RE = re.compile(
    r"(?:指数|INDEX|PHLX|S&P\s*500|NASDAQ\s*[- ]?100|DOW\s+JONES|HANG\s+SENG)",
    re.IGNORECASE,
)
_EQUITY_OVERRIDE_RE = re.compile(
    r"(?:\.AX\b|\bASX\b|SENTINEL\s+EXPLORATION)",
    re.IGNORECASE,
)
_BULLISH_STANCE_RE = re.compile(
    r"(?:看多|看好|做多|买入|增持|加仓|抄底|推荐持有|坚定持有|"
    r"逐步建仓|配置建仓|上车机会|加点)"
    r"|(?<![A-Z0-9_])(?:BULLISH|BUY)(?![A-Z0-9_])",
    re.IGNORECASE,
)
_BEARISH_STANCE_RE = re.compile(
    r"(?:看空|看衰|不看好|做空|卖出|减持|减仓|清仓|回避)"
    r"|(?<![A-Z0-9_])(?:BEARISH|SELL)(?![A-Z0-9_])",
    re.IGNORECASE,
)
_NEUTRAL_STANCE_RE = re.compile(
    r"(?:中性|观望|暂无方向|没有方向|不判断方向|多空平衡|方向不明)",
    re.IGNORECASE,
)
_FORWARD_MARKER = r"(?:将|会|预计|预期|估计|可能|有望|未来|后续|接下来|继续|目标)"
_BULLISH_MOVE = r"(?:上涨|上行|走高|反弹|突破|创新高|增长|提升|改善|上调|超预期)"
_BEARISH_MOVE = r"(?:下跌|下行|走低|回落|回调|调整|跌破|创新低|下降|下滑|恶化|下调|不及预期)"
_BULLISH_FORWARD_RE = re.compile(
    rf"(?:{_FORWARD_MARKER}.{{0,18}}{_BULLISH_MOVE}|{_BULLISH_MOVE}.{{0,10}}(?:概率|空间|趋势))",
    re.IGNORECASE,
)
_BEARISH_FORWARD_RE = re.compile(
    rf"(?:{_FORWARD_MARKER}.{{0,18}}{_BEARISH_MOVE}|{_BEARISH_MOVE}.{{0,10}}(?:概率|空间|趋势))",
    re.IGNORECASE,
)
_BULLISH_FUNDAMENTAL_RE = re.compile(
    r"(?:边际向好|基本面.{0,8}(?:强劲|改善)|业绩.{0,8}(?:不错|超预期)|"
    r"更有说服力|购买力.{0,8}改善|担忧.{0,8}(?:解除|证伪)|"
    r"(?:错误|错配).{0,8}(?:解除|证伪|是错的)|增长质量.{0,8}(?:提高|改善))",
    re.IGNORECASE,
)
_BEARISH_FUNDAMENTAL_RE = re.compile(
    r"(?:边际(?:恶化|转差)|基本面.{0,8}(?:恶化|转弱)|业绩.{0,8}(?:不及预期|爆雷)|"
    r"需求.{0,8}(?:疲弱|下滑|崩塌)|风险.{0,8}(?:显著增加|失控))",
    re.IGNORECASE,
)
_VALUATION_CONSTRAINT_RE = re.compile(
    r"(?:PE|P/E|市盈率|估值|VALUATION|MULTIPLE).{0,24}"
    r"(?:难以?扩张|不能扩张|不会扩张|不合理|承压|压缩|收缩|偏高|过高)"
    r"|(?:难以?扩张|不能扩张|不会扩张|不合理|承压|压缩|收缩|偏高|过高)"
    r".{0,24}(?:PE|P/E|市盈率|估值|VALUATION|MULTIPLE)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")

_EXCHANGE_MARKETS = {
    "US": "US",
    "UN": "US",
    "UW": "US",
    "UQ": "US",
    "UA": "US",
    "UP": "US",
    "XNYS": "US",
    "XNAS": "US",
    "ARCX": "US",
    "BATS": "US",
    "XASE": "US",
    "OTC": "US",
    "HK": "HK",
    "XHKG": "HK",
    "SH": "CN",
    "SS": "CN",
    "XSHG": "CN",
    "SZ": "CN",
    "XSHE": "CN",
    "AU": "AU",
    "ASX": "AU",
    "XASX": "AU",
    "LN": "UK",
    "XLON": "UK",
    "JP": "JP",
    "XTKS": "JP",
    "GR": "DE",
    "XETR": "DE",
    "FP": "FR",
    "XPAR": "FR",
    "SW": "CH",
    "XSWX": "CH",
}

_RISK_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_RISK_LEVEL_BY_ORDER = {4: "critical", 3: "high", 2: "medium", 1: "low"}
_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(?:INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|LIMITED|LTD|PLC|HOLDINGS?)\b",
    re.IGNORECASE,
)


def _new_audit() -> dict:
    return {
        "version": BUSINESS_VALIDATION_VERSION,
        "status": "accepted",
        "corrections": [],
    }


def _audit(analysis: dict) -> dict:
    value = analysis.get("business_validation")
    if not isinstance(value, dict):
        value = _new_audit()
        analysis["business_validation"] = value
    value.setdefault("version", BUSINESS_VALIDATION_VERSION)
    value.setdefault("status", "accepted")
    value.setdefault("corrections", [])
    return value


def _record_correction(
    analysis: dict,
    *,
    code: str,
    target: str,
    action: str,
    reason: str,
) -> None:
    audit = _audit(analysis)
    correction = {
        "code": code,
        "target": target,
        "action": action,
        "reason": reason,
    }
    if correction not in audit["corrections"]:
        audit["corrections"].append(correction)
    audit["status"] = "corrected"


def _finalize_audit(analysis: dict) -> None:
    audit = _audit(analysis)
    audit["correction_count"] = len(audit.get("corrections") or [])
    if not audit["correction_count"]:
        audit["status"] = "accepted"


def _symbol(instrument: dict) -> str:
    return str(
        instrument.get("symbol") or instrument.get("original_name") or ""
    ).strip().lstrip("$").upper()


def _contains_alias(text: str, alias: str) -> bool:
    candidate = str(alias or "").strip()
    if not candidate:
        return False
    if re.fullmatch(r"[A-Za-z0-9.\-]+", candidate):
        return bool(
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])",
                text,
                re.IGNORECASE,
            )
        )
    return candidate.lower() in text.lower()


def _instrument_aliases(instrument: dict) -> list[str]:
    aliases = [
        str(instrument.get("symbol") or "").strip().lstrip("$"),
        str(instrument.get("original_name") or "").strip().lstrip("$"),
    ]
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _target_fragments(claim: dict, source_text: str) -> list[str]:
    instrument = claim.get("instrument") or {}
    aliases = _instrument_aliases(instrument)
    evidence = [
        str(item).strip()
        for item in [
            *(claim.get("evidence") or []),
            *(claim.get("media_evidence") or []),
        ]
        if str(item).strip()
    ]
    sentences = [
        part.strip() for part in _SENTENCE_SPLIT_RE.split(source_text) if part.strip()
    ]
    source_windows: list[str] = []
    for index, sentence in enumerate(sentences):
        if not any(_contains_alias(sentence, alias) for alias in aliases):
            continue
        source_windows.extend(sentences[index:index + 3])

    # Evidence already belongs to this atomic claim. Source text still requires
    # an explicit instrument anchor before adjacent sentences are considered.
    return list(dict.fromkeys([*evidence, *source_windows]))


def _forecast_supports_direction(claim: dict, direction: str) -> bool:
    forecast = claim.get("forecast") or {}
    prediction_type = str(forecast.get("prediction_type") or "none")
    operator = str(forecast.get("target_operator") or "unknown")
    if prediction_type not in {"price_direction", "price_target", "fundamental_metric"}:
        return False
    if direction == "bullish" and operator not in {"up", "gte"}:
        return False
    if direction == "bearish" and operator not in {"down", "lte"}:
        return False
    if claim.get("opinion_source") == "author":
        return (
            forecast.get("forecast_source") == "author"
            and forecast.get("author_adopted") is True
        )
    return True


def _direction_has_target_evidence(
    claim: dict,
    direction: str,
    source_text: str,
) -> bool:
    if _forecast_supports_direction(claim, direction):
        return True
    text = "\n".join(_target_fragments(claim, source_text))
    if not text:
        return False
    if direction == "bullish":
        return bool(
            _BULLISH_STANCE_RE.search(text)
            or _BULLISH_FORWARD_RE.search(text)
            or _BULLISH_FUNDAMENTAL_RE.search(text)
        )
    if direction == "bearish":
        return bool(
            _BEARISH_STANCE_RE.search(text)
            or _BEARISH_FORWARD_RE.search(text)
            or _BEARISH_FUNDAMENTAL_RE.search(text)
        )
    if direction == "neutral":
        return bool(_NEUTRAL_STANCE_RE.search(text))
    return True


def _normalize_claim_directions(
    analysis: dict,
    source_text: str,
) -> None:
    for claim in analysis.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        instrument = claim.get("instrument") or {}
        target = _symbol(instrument) or "UNKNOWN"
        claim_type = str(claim.get("claim_type") or "reference")
        direction = str(claim.get("direction") or "none")
        if claim_type in _NON_STANCE_CLAIM_TYPES:
            if direction != "none":
                claim["direction"] = "none"
                _record_correction(
                    analysis,
                    code="non_stance_direction_removed",
                    target=target,
                    action=f"direction:{direction}->none",
                    reason="事实、新闻、引用、复盘和风险提示不能形成投资方向",
                )
            continue
        if claim_type not in _STANCE_CLAIM_TYPES or direction not in _DIRECTIONAL:
            continue
        if _direction_has_target_evidence(claim, direction, source_text):
            continue
        evidence_text = "\n".join(_target_fragments(claim, source_text))
        must_demote = (
            direction == "bearish" and bool(_VALUATION_CONSTRAINT_RE.search(evidence_text))
        ) or (
            claim_type in {"recommendation", "prediction"}
            and str((claim.get("forecast") or {}).get("prediction_type") or "none")
            == "none"
        )
        if not must_demote:
            continue
        claim["direction"] = "none"
        if claim_type in {"recommendation", "prediction"} and str(
            (claim.get("forecast") or {}).get("prediction_type") or "none"
        ) == "none":
            claim["claim_type"] = "opinion"
        _record_correction(
            analysis,
            code="direction_evidence_insufficient",
            target=target,
            action=f"direction:{direction}->none",
            reason="标的证据句中没有明确的方向、买卖建议或作者采纳的预测",
        )


def _benchmark_for_claim(claim: dict, source_text: str) -> dict | None:
    instrument = claim.get("instrument") or {}
    symbol = _symbol(instrument)
    asset_type = str(instrument.get("asset_type") or "unknown").lower()
    market_hint = str(instrument.get("market_hint") or "unknown").upper()
    original_name = str(instrument.get("original_name") or "")

    pseudo = _MARKET_PSEUDO_INSTRUMENTS.get(symbol)
    if pseudo:
        return {"symbol": original_name or symbol, **pseudo}
    if symbol == "SPY" and re.search(r"(?<![A-Za-z0-9])SPY\s*500(?![A-Za-z0-9])", source_text, re.IGNORECASE):
        return {
            "symbol": "SPX",
            "market": "US",
            "name": "S&P 500 Index",
        }

    if asset_type == "index":
        spec = dict(_BENCHMARKS.get(symbol) or {})
        market = str(spec.get("market") or market_hint)
        if market not in _SUPPORTED_MARKETS:
            return None
        return {
            "symbol": symbol,
            "market": market,
            "name": spec.get("name") or original_name or symbol,
        }

    spec = _BENCHMARKS.get(symbol)
    if not spec or _EQUITY_OVERRIDE_RE.search(source_text):
        return None
    context_terms = tuple(spec.get("context_terms") or ())
    has_index_context = bool(_INDEX_NAME_RE.search(original_name) or _INDEX_NAME_RE.search(source_text))
    if context_terms:
        has_index_context = has_index_context or any(
            _contains_alias(source_text, term) for term in context_terms
        )
    if not has_index_context and symbol == "SOX":
        return None
    return {"symbol": symbol, **spec}


def _claim_impact(claim: dict) -> str:
    return {
        "bullish": "positive",
        "bearish": "negative",
        "neutral": "mixed",
    }.get(str(claim.get("direction") or "none"), "unclear")


def _matching_market_view(analysis: dict, claim: dict, market: str) -> dict | None:
    claim_evidence = {
        str(item).strip() for item in claim.get("evidence") or [] if str(item).strip()
    }
    for view in analysis.get("market_views") or []:
        if not isinstance(view, dict) or str(view.get("market") or "") != market:
            continue
        view_evidence = {
            str(item).strip() for item in view.get("evidence") or [] if str(item).strip()
        }
        if claim_evidence & view_evidence or any(
            len(left) >= 8
            and len(right) >= 8
            and (left in right or right in left)
            for left in claim_evidence
            for right in view_evidence
        ):
            return view
    return None


def _move_benchmarks_to_market_views(analysis: dict, source_text: str) -> None:
    claims: list[dict] = []
    market_views = [
        dict(view) for view in analysis.get("market_views") or [] if isinstance(view, dict)
    ]
    analysis["market_views"] = market_views
    existing_benchmarks = {
        (str(view.get("market") or ""), str(view.get("benchmark") or "").upper())
        for view in market_views
    }

    for claim in analysis.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        benchmark = _benchmark_for_claim(claim, source_text)
        if not benchmark:
            claims.append(claim)
            continue

        key = (benchmark["market"], benchmark["symbol"])
        if key not in existing_benchmarks:
            related_view = _matching_market_view(
                analysis, claim, str(benchmark["market"])
            )
            if related_view:
                view = deepcopy(related_view)
                view["benchmark"] = benchmark["symbol"]
                view["thesis"] = str(claim.get("thesis") or view.get("thesis") or "")
                view["evidence"] = list(dict.fromkeys([
                    *(claim.get("evidence") or []),
                    *(view.get("evidence") or []),
                ]))[:3]
                view["confidence"] = min(
                    float(claim.get("confidence") or 0.0),
                    float(view.get("confidence") or 0.0),
                )
            else:
                view = {
                    "market": benchmark["market"],
                    "benchmark": benchmark["symbol"],
                    "impact": _claim_impact(claim),
                    "horizon": str(claim.get("horizon") or "unknown"),
                    "topic": "other",
                    "thesis": str(claim.get("thesis") or ""),
                    "evidence": list(claim.get("evidence") or [])[:3],
                    "opinion_source": str(claim.get("opinion_source") or "unclear"),
                    "confidence": float(claim.get("confidence") or 0.0),
                }
            market_views.append(view)
            existing_benchmarks.add(key)

        _record_correction(
            analysis,
            code="benchmark_moved_to_market_view",
            target=benchmark["symbol"],
            action="claim->market_view",
            reason=f"{benchmark['name']} 是市场基准，不是单一股票标的",
        )

    analysis["claims"] = claims


def _refresh_markets(analysis: dict) -> None:
    markets: list[str] = []
    for claim in analysis.get("claims") or []:
        instrument = claim.get("instrument") or {}
        market = str(instrument.get("market") or instrument.get("market_hint") or "").upper()
        if market in _SUPPORTED_MARKETS and market not in markets:
            markets.append(market)
    for view in analysis.get("market_views") or []:
        market = str(view.get("market") or "").upper()
        if market in _SUPPORTED_MARKETS and market not in markets:
            markets.append(market)
    analysis["markets"] = markets


def normalize_before_resolution(
    analysis: dict,
    *,
    source_text: str,
) -> dict:
    """Normalize model semantics before external instrument resolution."""
    payload = deepcopy(analysis)
    payload["business_validation"] = _new_audit()
    _normalize_claim_directions(payload, source_text)
    _move_benchmarks_to_market_views(payload, source_text)
    _refresh_markets(payload)
    _finalize_audit(payload)
    return payload


def _reject_cross_market_identity(analysis: dict, claim: dict) -> None:
    instrument = claim.get("instrument") or {}
    market_hint = str(instrument.get("market_hint") or "unknown").upper()
    exchange = str(instrument.get("exchange") or "").upper()
    exchange_market = _EXCHANGE_MARKETS.get(exchange)
    if (
        market_hint not in {"CN", "HK", "US"}
        or exchange_market is None
        or exchange_market == market_hint
    ):
        return

    target = _symbol(instrument) or "UNKNOWN"
    rejected_candidate = {
        "resolved_name": str(instrument.get("resolved_name") or ""),
        "exchange": exchange,
        "external_ids": dict(instrument.get("external_ids") or {}),
    }
    instrument["rejected_identity_candidate"] = rejected_candidate
    instrument["resolved_name"] = ""
    instrument["exchange"] = ""
    instrument["external_ids"] = {}
    reason = f"推文市场语境为 {market_hint}，候选证券交易市场为 {exchange_market}"
    verification = dict(instrument.get("verification") or {})
    verification.update({
        "status": "ambiguous",
        "reason_code": "cross_market_symbol_collision",
        "reason": reason,
        "is_verified": False,
        "downstream_eligible": False,
        "tradable": False,
        "listing_status": "identity_candidate",
        "authoritative_source": None,
    })
    instrument["verification"] = verification
    instrument["validation_status"] = "ambiguous"
    instrument["validation_reason_code"] = "cross_market_symbol_collision"
    instrument["validation_reason"] = reason
    instrument["tradable"] = False
    instrument["listing_status"] = "identity_candidate"
    claim["instrument"] = instrument
    claim["downstream_eligible"] = False
    claim["confidence"] = min(float(claim.get("confidence") or 0.0), 0.6)
    _record_correction(
        analysis,
        code="cross_market_identity_rejected",
        target=target,
        action="identity->ambiguous",
        reason=reason,
    )


def _hide_unverified_candidate_name(analysis: dict, claim: dict) -> None:
    instrument = claim.get("instrument") or {}
    verification = instrument.get("verification") or {}
    if (
        verification.get("status") != "ambiguous"
        or verification.get("authoritative_source")
        or not instrument.get("resolved_name")
    ):
        return
    target = _symbol(instrument) or "UNKNOWN"
    instrument["candidate_resolved_name"] = str(instrument.get("resolved_name") or "")
    instrument["resolved_name"] = ""
    claim["instrument"] = instrument
    _record_correction(
        analysis,
        code="unverified_name_kept_as_candidate",
        target=target,
        action="resolved_name->candidate_resolved_name",
        reason="缺少权威数据源确认，候选名称不能作为正式标的身份展示",
    )


def _name_aliases(instrument: dict) -> list[str]:
    symbol = _symbol(instrument)
    names = [
        str(instrument.get("original_name") or ""),
        str(instrument.get("resolved_name") or ""),
        str(instrument.get("candidate_resolved_name") or ""),
    ]
    aliases = [symbol] if symbol else []
    for raw_name in names:
        normalized = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", " ", raw_name).strip().upper()
        if not normalized:
            continue
        aliases.append(normalized)
        without_suffix = _CORPORATE_SUFFIX_RE.sub("", normalized)
        without_suffix = re.sub(r"\s+", " ", without_suffix).strip()
        if without_suffix:
            aliases.append(without_suffix)
            first_word = without_suffix.split(" ", 1)[0]
            if len(first_word) >= 2:
                aliases.append(first_word)
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _canonicalize_risk_symbols(analysis: dict) -> None:
    aliases: dict[str, set[str]] = defaultdict(set)
    for claim in analysis.get("claims") or []:
        instrument = claim.get("instrument") or {}
        symbol = _symbol(instrument)
        if not symbol:
            continue
        for alias in _name_aliases(instrument):
            aliases[alias].add(symbol)

    for risk in analysis.get("risk_context") or []:
        if not isinstance(risk, dict):
            continue
        before = [str(item).strip().upper() for item in risk.get("related_tickers") or [] if item]
        after: list[str] = []
        for item in before:
            matches = aliases.get(item) or set()
            normalized = next(iter(matches)) if len(matches) == 1 else item
            if normalized not in after:
                after.append(normalized)
        risk["related_tickers"] = after
        if before != after:
            _record_correction(
                analysis,
                code="risk_symbol_canonicalized",
                target=",".join(before),
                action=f"related_tickers->{','.join(after)}",
                reason="风险关联对象已统一为当前分析中的标准标的代码",
            )


def _attach_canonical_risks(analysis: dict) -> None:
    risk_context = [
        item for item in analysis.get("risk_context") or [] if isinstance(item, dict)
    ]
    if not risk_context:
        return
    for claim in analysis.get("claims") or []:
        instrument = claim.get("instrument") or {}
        symbol = _symbol(instrument)
        matched: list[dict] = []
        for risk in risk_context:
            related = [str(item).upper() for item in risk.get("related_tickers") or []]
            if symbol in related or not related:
                matched.append({
                    "category": str(risk.get("category") or "market"),
                    "description": str(risk.get("description") or ""),
                    "severity": str(risk.get("severity") or "medium"),
                    "urgency": str(risk.get("urgency") or "near_term"),
                })
        claim["risks"] = matched
        descriptions = [
            *list(claim.get("risk_factors") or []),
            *[item["description"] for item in matched if item["description"]],
        ]
        claim["risk_factors"] = list(dict.fromkeys(descriptions))
        if matched:
            maximum = max(
                _RISK_SEVERITY_ORDER.get(item["severity"], 1) for item in matched
            )
            claim["risk_level"] = _RISK_LEVEL_BY_ORDER.get(maximum, "low")


def validate_after_resolution(
    analysis: dict,
    *,
    source_text: str,
) -> dict:
    """Apply identity and downstream consistency rules after resolution."""
    payload = deepcopy(analysis)
    for claim in payload.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        _reject_cross_market_identity(payload, claim)
        _hide_unverified_candidate_name(payload, claim)
    _canonicalize_risk_symbols(payload)
    _attach_canonical_risks(payload)
    _refresh_markets(payload)
    _finalize_audit(payload)
    corrections = (payload.get("business_validation") or {}).get("corrections") or []
    if corrections:
        logger.info(
            "[BusinessValidation] corrections={} targets={}",
            len(corrections),
            [item.get("target") for item in corrections],
        )
    return payload
