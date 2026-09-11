from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult
from app.models.instrument_claim import InstrumentClaim
from app.models.tweet import Tweet


def classify_consensus(
    *,
    bullish: int,
    bearish: int,
    neutral: int,
    independent_bloggers: int,
) -> tuple[str, float | None]:
    """Return a direction label without overstating a small sample."""
    directional = bullish + bearish
    if directional == 0:
        return ("neutral", 50.0) if neutral else ("none", None)
    if bullish == bearish:
        return "mixed", 50.0

    bullish_ratio = bullish / directional
    bearish_ratio = bearish / directional
    if independent_bloggers >= 3 and bullish_ratio >= 0.7:
        consensus = "strong_buy"
    elif bullish > bearish:
        consensus = "buy"
    elif independent_bloggers >= 3 and bearish_ratio >= 0.7:
        consensus = "strong_sell"
    else:
        consensus = "sell"
    score = round(50 + ((bullish - bearish) / directional) * 50, 1)
    return consensus, score


def _reference_reason_keys(claim: InstrumentClaim) -> list[str]:
    """Return every user-facing reason why a claim is reference-only."""
    reasons: list[str] = []
    if claim.sponsor_relation == "direct":
        reasons.append("sponsor_related")
    elif claim.sponsor_relation == "unclear":
        reasons.append("sponsor_relation_unclear")
    if claim.opinion_source == "quoted":
        reasons.append("quoted_opinion")
    elif claim.opinion_source == "third_party":
        reasons.append("third_party_opinion")
    elif claim.opinion_source != "author":
        reasons.append("opinion_source_unclear")
    claim_type_reason = {
        "risk_warning": "risk_warning",
        "fact": "fact_mention",
        "news": "news_mention",
        "recap": "historical_recap",
        "reference": "reference_mention",
    }.get(claim.claim_type)
    if claim_type_reason:
        reasons.append(claim_type_reason)
    if (
        claim.opinion_source == "author"
        and claim.claim_type in {"recommendation", "prediction", "opinion"}
        and claim.direction not in {"bullish", "bearish", "neutral"}
    ):
        reasons.append("direction_not_comparable")
    if not claim.downstream_eligible:
        reasons.append("instrument_not_verified")
    if not reasons:
        reasons.append(claim.performance_exclusion_reason or "not_performance_eligible")
    return list(dict.fromkeys(reasons))


def aggregate_instrument_claims(db: Session) -> list[dict]:
    """Build a directory of every verified instrument and its comparable views.

    ``mention_count`` remains the number of author views eligible for performance
    and consensus.  Other verified claims stay visible through the related fields
    instead of making the instrument disappear from the product.
    """
    rows = db.execute(
        select(InstrumentClaim, Tweet.author_handle)
        .join(
            AnalysisResult,
            AnalysisResult.id == InstrumentClaim.analysis_result_id,
        )
        .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
        .where(
            InstrumentClaim.downstream_eligible.is_(True),
        )
        .order_by(InstrumentClaim.created_at.desc())
    ).all()
    grouped: dict[str, dict] = defaultdict(
        lambda: {
            "bloggers": set(),
            "bullish": 0,
            "bearish": 0,
            "neutral": 0,
            "theses": [],
            "related_bloggers": set(),
            "related_claim_count": 0,
            "reference_only_count": 0,
            "related_theses": [],
            "exclusion_reasons": defaultdict(int),
        }
    )
    for claim, author in rows:
        data = grouped[claim.instrument_symbol]
        data["related_bloggers"].add(author)
        data["related_claim_count"] += 1
        if claim.thesis and claim.thesis not in data["related_theses"]:
            data["related_theses"].append(claim.thesis)
        if not claim.performance_eligible:
            data["reference_only_count"] += 1
            for reason in _reference_reason_keys(claim):
                data["exclusion_reasons"][reason] += 1
            continue
        data["bloggers"].add(author)
        if claim.direction == "bullish":
            data["bullish"] += 1
        elif claim.direction == "bearish":
            data["bearish"] += 1
        elif claim.direction == "neutral":
            data["neutral"] += 1
        if claim.thesis and claim.thesis not in data["theses"]:
            data["theses"].append(claim.thesis)

    output: list[dict] = []
    for symbol, data in grouped.items():
        bullish = data["bullish"]
        bearish = data["bearish"]
        neutral = data["neutral"]
        directional = bullish + bearish
        independent_bloggers = len(data["bloggers"])
        consensus, score = classify_consensus(
            bullish=bullish,
            bearish=bearish,
            neutral=neutral,
            independent_bloggers=independent_bloggers,
        )
        output.append(
            {
                "ticker": symbol,
                "mention_count": bullish + bearish + neutral,
                "bloggers": sorted(data["bloggers"]),
                "independent_blogger_count": independent_bloggers,
                "consensus_sample_status": (
                    "sufficient" if independent_bloggers >= 3 else "limited"
                ),
                "related_bloggers": sorted(data["related_bloggers"]),
                "related_claim_count": data["related_claim_count"],
                "reference_only_count": data["reference_only_count"],
                "has_effective_views": bool(bullish + bearish + neutral),
                "exclusion_reasons": dict(data["exclusion_reasons"]),
                "consensus": consensus,
                "bullish_count": bullish,
                "bearish_count": bearish,
                "neutral_count": neutral,
                "none_count": 0,
                "directional_claim_count": directional,
                "direction_basis": "author_stance_claims",
                "recommendation_score": score,
                "summary": "；".join(
                    (data["theses"] or data["related_theses"])[:3]
                ),
            }
        )
    output.sort(
        key=lambda item: (
            item["has_effective_views"],
            item["mention_count"],
            item["related_claim_count"],
            item["recommendation_score"] or 0,
        ),
        reverse=True,
    )
    return output
