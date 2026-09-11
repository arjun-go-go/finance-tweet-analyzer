from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.instrument_claim import InstrumentClaim
from app.services.instrument_resolver import is_downstream_verified_ticker
from app.services.prediction_time_resolver import resolve_prediction_time


AUTHOR_STANCE_CLAIM_TYPES = ("recommendation", "prediction", "opinion")
AUTHOR_STANCE_DIRECTIONS = ("bullish", "bearish", "neutral")
SPONSOR_RELATIONS = ("none", "unrelated", "direct", "unclear")

_AUTHOR_ADOPTION_RE = re.compile(
    r"(?:我|本人|个人)(?:明确)?(?:"
    r"预计|预测|目标(?:是|为)|(?:认为|判断)(?:将|会|能|可|可以|有望)|"
    r"(?:同意|认可)(?:这个|该|上述)?(?:预测|目标|指引))"
    r"|(?:我的|本人给出的)(?:预测|判断|目标)"
)
_MARKET_FORECAST_RE = re.compile(r"市场(?:一致)?(?:认为|预期|预计|预测|共识)")
_COMPANY_FORECAST_RE = re.compile(
    r"(?:公司|官方|管理层|董事会|财报|业绩会|电话会)(?:给出|称|表示|预计|预测|指引|目标)"
    r"|(?:公司|官方|管理层)(?:收入|营收|利润|增长|毛利率|产量)?指引"
)
_NAMED_FORECAST_RE = re.compile(
    r"(?<![A-Za-z0-9_\u4e00-\u9fff])@?"
    r"(?P<name>[A-Za-z][A-Za-z0-9_.\- ]{0,24}|[\u4e00-\u9fff]{2,8})"
    r"(?:说|称|表示|认为|预计|预测|给出(?:目标|指引)?)"
)
_NON_THIRD_PARTY_SOURCE_NAMES = {
    "我",
    "本人",
    "个人",
    "作者",
    "博主",
    "当前博主",
    "市场",
    "公司",
    "官方",
    "管理层",
    "财报",
    "业绩会",
    "电话会",
}
_FORECAST_SOURCE_LABELS = {
    "quoted": "引用账号",
    "third_party": "第三方",
    "market_consensus": "市场一致预期",
    "company_guidance": "公司 / 管理层指引",
    "unclear": "未确认来源",
}
_DIRECTION_LABELS = {
    "bullish": "看多",
    "bearish": "看空",
    "neutral": "中性",
    "none": "无方向",
}


def _forecast_target_context(source_text: str, forecast: dict) -> str:
    """Return text windows around the forecast's explicit numeric targets."""
    tokens = re.findall(r"\d+(?:\.\d+)?", str(forecast.get("target_value") or ""))
    windows: list[str] = []
    for token in dict.fromkeys(tokens):
        for match in re.finditer(re.escape(token), source_text):
            windows.append(
                source_text[max(0, match.start() - 80):match.end() + 80]
            )
    return "\n".join(windows) if windows else source_text


def _forecast_target_positions(text: str, forecast: dict) -> list[int]:
    tokens = re.findall(r"\d+(?:\.\d+)?", str(forecast.get("target_value") or ""))
    return [
        match.start()
        for token in dict.fromkeys(tokens)
        for match in re.finditer(re.escape(token), text)
    ]


def _source_cue_score(match: re.Match, target_positions: list[int]) -> int:
    """Prefer the closest cue before a target; cues after it are weak evidence."""
    if not target_positions:
        return match.start()
    return min(
        (
            target_position - match.end()
            if match.end() <= target_position
            else 10_000 + match.start() - target_position
        )
        for target_position in target_positions
    )


def _detect_forecast_source(text: str, forecast: dict) -> tuple[str, str] | None:
    target_positions = _forecast_target_positions(text, forecast)
    candidates: list[tuple[int, int, str, str]] = []

    for match in _NAMED_FORECAST_RE.finditer(text):
        name = match.group("name").strip()
        if name in _NON_THIRD_PARTY_SOURCE_NAMES:
            continue
        if name == "老黄":
            name = "黄仁勋"
        candidates.append(
            (_source_cue_score(match, target_positions), 0, "third_party", name)
        )
    for match in _COMPANY_FORECAST_RE.finditer(text):
        candidates.append(
            (
                _source_cue_score(match, target_positions),
                1,
                "company_guidance",
                "公司 / 管理层",
            )
        )
    for match in _MARKET_FORECAST_RE.finditer(text):
        candidates.append(
            (
                _source_cue_score(match, target_positions),
                2,
                "market_consensus",
                "市场一致预期",
            )
        )
    for match in _AUTHOR_ADOPTION_RE.finditer(text):
        candidates.append(
            (_source_cue_score(match, target_positions), 3, "author", "当前博主")
        )

    if not candidates:
        return None
    _, _, source_type, source_name = min(candidates)
    return source_type, source_name


def normalize_forecast_attribution(
    analysis: dict,
    source_text: str,
    published_at: datetime | None = None,
) -> dict:
    """Resolve numeric forecast ownership from source text, not model tone.

    A blogger may express an investment stance while citing a market, company, or
    executive target.  Those are separate facts: the stance can remain the
    author's, but the cited target is not scoreable as the author's prediction
    without an explicit adoption phrase.
    """
    payload = dict(analysis)
    normalized_claims: list[dict] = []
    for raw_claim in payload.get("claims") or []:
        if not isinstance(raw_claim, dict):
            continue
        claim = dict(raw_claim)
        forecast = dict(claim.get("forecast") or {})
        if str(forecast.get("prediction_type") or "none") == "none":
            normalized_claims.append(claim)
            continue

        evidence_text = "\n".join(
            str(item)
            for item in [
                *(claim.get("evidence") or []),
                *(claim.get("media_evidence") or []),
            ]
            if item
        )
        attribution_text = _forecast_target_context(
            "\n".join(part for part in (source_text, evidence_text) if part),
            forecast,
        )
        explicitly_adopted = bool(_AUTHOR_ADOPTION_RE.search(attribution_text))
        source_type = str(forecast.get("forecast_source") or "unclear")
        source_name = str(forecast.get("source_name") or "").strip()

        detected_source = _detect_forecast_source(attribution_text, forecast)
        if detected_source:
            source_type, source_name = detected_source
        elif explicitly_adopted and claim.get("opinion_source") == "author":
            source_type = "author"
            source_name = "当前博主"
        elif source_type == "unclear" and claim.get("opinion_source") == "author":
            source_type = "author"
            source_name = source_name or "当前博主"

        forecast["forecast_source"] = source_type
        forecast["source_name"] = source_name
        forecast["author_adopted"] = explicitly_adopted
        claim["forecast"] = forecast
        if published_at is not None:
            resolved_time = resolve_prediction_time(claim, published_at)
            claim["horizon"] = resolved_time.horizon

        if (
            claim.get("opinion_source") == "author"
            and claim.get("claim_type") == "prediction"
            and source_type != "author"
            and not explicitly_adopted
        ):
            claim["claim_type"] = "opinion"
            instrument = claim.get("instrument") or {}
            instrument_name = str(
                instrument.get("original_name")
                or instrument.get("resolved_name")
                or instrument.get("symbol")
                or "该标的"
            )
            target = " ".join(
                part
                for part in (
                    str(forecast.get("temporal_expression") or "").strip(),
                    str(forecast.get("target_metric") or "").strip(),
                    (
                        f"{forecast.get('target_value')}{forecast.get('target_unit') or ''}"
                        if forecast.get("target_value")
                        else ""
                    ),
                )
                if part
            )
            origin = source_name or _FORECAST_SOURCE_LABELS.get(source_type, source_type)
            direction = _DIRECTION_LABELS.get(str(claim.get("direction") or "none"), "研判")
            claim["thesis"] = (
                f"博主围绕{instrument_name}表达{direction}研判；"
                f"其中{target or '该预测目标'}来自{origin}，"
                "博主未明确将该目标采纳为个人预测。"
            )

        normalized_claims.append(claim)

    payload["claims"] = normalized_claims
    return payload


def is_author_stance_claim(claim: InstrumentClaim) -> bool:
    """Return whether a claim represents the blogger's comparable stance."""
    return (
        claim.opinion_source == "author"
        and claim.claim_type in AUTHOR_STANCE_CLAIM_TYPES
        and claim.direction in AUTHOR_STANCE_DIRECTIONS
    )


def normalize_sponsor_relation(value: object, *, has_commercial_content: bool) -> str:
    """Normalize claim-level commercial attribution.

    ``is_sponsored`` historically meant that the tweet contained any ad text.
    It must not imply that every claim was paid for.  Missing attribution on a
    commercial tweet therefore remains ``unclear`` until it is re-analysed.
    """
    if not has_commercial_content:
        return "none"
    normalized = str(value or "").strip().lower()
    if normalized not in SPONSOR_RELATIONS or normalized == "none":
        return "unclear"
    return normalized


def evaluate_claim_performance_eligibility(
    *,
    downstream_eligible: bool,
    opinion_source: str,
    claim_type: str,
    direction: str,
    sponsor_relation: str,
) -> tuple[bool, str | None]:
    """Return whether one claim may enter blogger performance and consensus."""
    if not downstream_eligible:
        return False, "instrument_not_verified"
    if opinion_source != "author":
        return False, "opinion_not_author"
    if claim_type not in AUTHOR_STANCE_CLAIM_TYPES:
        return False, "claim_type_not_stance"
    if direction not in AUTHOR_STANCE_DIRECTIONS:
        return False, "direction_not_comparable"
    if sponsor_relation == "direct":
        return False, "sponsor_related"
    if sponsor_relation == "unclear":
        return False, "sponsor_relation_unclear"
    return True, None


def serialize_instrument_claim(claim: InstrumentClaim) -> dict:
    return {
        "id": str(claim.id),
        "analysis_result_id": str(claim.analysis_result_id),
        "claim_index": claim.claim_index,
        "instrument": claim.instrument_snapshot,
        "direction": claim.direction,
        "horizon": claim.horizon,
        "claim_type": claim.claim_type,
        "opinion_source": claim.opinion_source,
        "thesis": claim.thesis,
        "evidence": claim.evidence or [],
        "media_evidence": claim.media_evidence or [],
        "catalysts": claim.catalysts or [],
        "risk_factors": claim.risk_factors or [],
        "risk_details": claim.risk_details or [],
        "risk_level": claim.risk_level,
        "entry_conditions": claim.entry_conditions or [],
        "invalidation_conditions": claim.invalidation_conditions or [],
        "price_targets": claim.price_targets or [],
        "forecast": claim.forecast_spec or {},
        "confidence": claim.confidence,
        "downstream_eligible": claim.downstream_eligible,
        "sponsor_relation": claim.sponsor_relation,
        "performance_eligible": claim.performance_eligible,
        "performance_exclusion_reason": claim.performance_exclusion_reason,
        "claim_schema_version": claim.claim_schema_version,
    }


def replace_analysis_claims(
    db: Session,
    analysis_result_id: UUID,
    analysis: dict,
) -> list[InstrumentClaim]:
    """Replace all canonical claims for one re-analysis in their source order."""
    db.execute(
        delete(InstrumentClaim).where(
            InstrumentClaim.analysis_result_id == analysis_result_id
        )
    )
    records: list[InstrumentClaim] = []
    for index, payload in enumerate(analysis.get("claims") or []):
        if not isinstance(payload, dict):
            continue
        instrument = payload.get("instrument")
        if not isinstance(instrument, dict):
            continue
        symbol = str(instrument.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        claim_type = str(payload.get("claim_type") or "reference")
        direction = str(payload.get("direction") or "none")
        if claim_type in {"fact", "news", "recap", "reference", "risk_warning"}:
            direction = "none"
        downstream_eligible = is_downstream_verified_ticker(instrument)
        commercial = analysis.get("commercial_disclosure") or {}
        has_commercial_content = bool(
            analysis.get("is_sponsored")
            or (
                isinstance(commercial, dict)
                and commercial.get("has_commercial_content")
            )
        )
        sponsor_relation = normalize_sponsor_relation(
            payload.get("sponsor_relation"),
            has_commercial_content=has_commercial_content,
        )
        performance_eligible, exclusion_reason = evaluate_claim_performance_eligibility(
            downstream_eligible=downstream_eligible,
            opinion_source=str(payload.get("opinion_source") or "unclear"),
            claim_type=claim_type,
            direction=direction,
            sponsor_relation=sponsor_relation,
        )
        record = InstrumentClaim(
            analysis_result_id=analysis_result_id,
            claim_index=index,
            instrument_symbol=symbol,
            instrument_snapshot=instrument,
            direction=direction,
            horizon=str(payload.get("horizon") or "unknown"),
            claim_type=claim_type,
            opinion_source=str(payload.get("opinion_source") or "unclear"),
            thesis=str(payload.get("thesis") or "").strip(),
            evidence=list(payload.get("evidence") or []),
            media_evidence=list(payload.get("media_evidence") or []),
            catalysts=list(payload.get("catalysts") or []),
            risk_factors=list(payload.get("risk_factors") or []),
            risk_details=list(payload.get("risks") or payload.get("risk_details") or []),
            risk_level=str(payload.get("risk_level") or "low"),
            entry_conditions=list(payload.get("entry_conditions") or []),
            invalidation_conditions=list(payload.get("invalidation_conditions") or []),
            price_targets=list(payload.get("price_targets") or []),
            forecast_spec=dict(payload.get("forecast") or {}),
            confidence=float(payload.get("confidence") or 0.0),
            downstream_eligible=downstream_eligible,
            sponsor_relation=sponsor_relation,
            performance_eligible=performance_eligible,
            performance_exclusion_reason=exclusion_reason,
            claim_schema_version="v4",
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def claims_by_analysis_ids(
    db: Session,
    analysis_result_ids: list[UUID],
) -> dict[UUID, list[InstrumentClaim]]:
    if not analysis_result_ids:
        return {}
    rows = db.execute(
        select(InstrumentClaim)
        .where(InstrumentClaim.analysis_result_id.in_(analysis_result_ids))
        .order_by(
            InstrumentClaim.analysis_result_id,
            InstrumentClaim.claim_index,
        )
    ).scalars()
    grouped: dict[UUID, list[InstrumentClaim]] = defaultdict(list)
    for row in rows:
        grouped[row.analysis_result_id].append(row)
    return dict(grouped)


def analysis_payload_with_claims(
    result: dict | None,
    claims: list[InstrumentClaim],
) -> dict:
    payload = dict(result or {})
    payload["claims"] = [serialize_instrument_claim(claim) for claim in claims]
    payload["analysis_schema_version"] = "v4"
    return payload
