"""Cross-model review for high-value tweet analyses.

Qwen Plus remains the primary extractor.  Luna independently re-extracts only
important or ambiguous tweets, and Qwen Max is invoked only when the two models
disagree on fields that affect product semantics or downstream statistics.
"""
from __future__ import annotations

import asyncio
import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.agents.analysis_agent import analyze_tweet_with_llm
from app.agents.llm import get_report_llm, get_review_llm
from app.core.config import settings
from app.prompts import get_chat_prompt
from app.schemas.signal import TweetAnalysis


_REVIEW_CONTEXT = (
    "这是独立复核：只根据当前推文、图片证据和 Twitter 关系上下文提取，"
    "不得使用历史画像补全本条推文未表达的事实、方向或预测。"
)
_PRESERVED_SYSTEM_FIELDS = (
    "routing_degraded",
    "routing_degraded_reason",
    "risk_context",
    "risk_context_level",
    "risk_context_summary",
    "media_summary",
    "text_image_consistency",
    "media_confidence",
)


def _to_lc_messages(msg_dicts: list[dict]) -> list:
    role_map = {"system": SystemMessage, "human": HumanMessage}
    return [role_map[item["role"]](content=item["content"]) for item in msg_dicts]


def _clean_text(value: object) -> str:
    return str(value or "").strip().upper()


def _claim_signature(claim: dict) -> tuple:
    instrument = claim.get("instrument") or {}
    forecast = claim.get("forecast") or {}
    return (
        _clean_text(instrument.get("symbol") or instrument.get("original_name")),
        str(claim.get("direction") or "none"),
        str(claim.get("horizon") or "unknown"),
        str(claim.get("claim_type") or "reference"),
        str(claim.get("opinion_source") or "unclear"),
        str(claim.get("sponsor_relation") or "none"),
        str(forecast.get("prediction_type") or "none"),
        str(forecast.get("forecast_source") or "unclear"),
        bool(forecast.get("author_adopted")),
        _clean_text(forecast.get("temporal_expression")),
        _clean_text(forecast.get("target_metric")),
        str(forecast.get("target_operator") or "unknown"),
        _clean_text(forecast.get("target_value")),
        _clean_text(forecast.get("target_unit")),
    )


def _market_view_signature(view: dict) -> tuple:
    return (
        str(view.get("market") or "GLOBAL"),
        str(view.get("impact") or "unclear"),
        str(view.get("opinion_source") or "unclear"),
    )


def _commercial_signature(analysis: dict) -> bool:
    disclosure = analysis.get("commercial_disclosure") or {}
    return bool(
        analysis.get("is_sponsored")
        or disclosure.get("has_commercial_content")
    )


def critical_conflicts(primary: dict, review: dict) -> list[str]:
    """Return semantic fields whose disagreement requires Max arbitration."""
    conflicts: list[str] = []
    if bool(primary.get("is_investment_relevant")) != bool(
        review.get("is_investment_relevant")
    ):
        conflicts.append("investment_relevance")

    primary_claims = sorted(
        _claim_signature(item)
        for item in primary.get("claims") or []
        if isinstance(item, dict)
    )
    review_claims = sorted(
        _claim_signature(item)
        for item in review.get("claims") or []
        if isinstance(item, dict)
    )
    if primary_claims != review_claims:
        conflicts.append("instrument_claims")

    primary_views = sorted(
        _market_view_signature(item)
        for item in primary.get("market_views") or []
        if isinstance(item, dict)
    )
    review_views = sorted(
        _market_view_signature(item)
        for item in review.get("market_views") or []
        if isinstance(item, dict)
    )
    if primary_views != review_views:
        conflicts.append("market_views")

    if _commercial_signature(primary) != _commercial_signature(review):
        conflicts.append("commercial_attribution")
    return conflicts


def review_reasons(tweet: dict, analysis: dict, classification: dict) -> list[str]:
    """Select only analyses where a second model materially improves confidence."""
    if classification.get("category") == "non_financial":
        return []

    reasons: list[str] = []
    claims = [item for item in analysis.get("claims") or [] if isinstance(item, dict)]
    market_views = [
        item for item in analysis.get("market_views") or [] if isinstance(item, dict)
    ]
    if float(analysis.get("confidence") or 0.0) < settings.model_review_confidence_threshold:
        reasons.append("low_confidence")
    if not claims and not market_views:
        reasons.append("financial_but_empty")
    if any(
        item.get("opinion_source") == "author"
        and item.get("direction") in {"bullish", "bearish"}
        for item in claims
    ):
        reasons.append("directional_author_claim")
    if any(item.get("claim_type") in {"recommendation", "prediction"} for item in claims):
        reasons.append("scoreable_claim")
    if any(
        item.get("opinion_source") in {"quoted", "third_party", "unclear"}
        or item.get("sponsor_relation") in {"direct", "unclear"}
        for item in claims
    ):
        reasons.append("attribution_complexity")
    if market_views:
        reasons.append("market_view")
    if tweet.get("media_context"):
        reasons.append("media_evidence")
    conversation = tweet.get("conversation_context") or {}
    if conversation.get("references") or conversation.get("author_thread"):
        reasons.append("conversation_attribution")
    return list(dict.fromkeys(reasons))


def _routing_metadata(
    *,
    status: str,
    reasons: list[str],
    conflicts: list[str] | None = None,
    final_model: str | None = None,
) -> dict:
    return {
        "primary_model": settings.signal_model,
        "review_model": settings.review_model if status != "not_required" else None,
        "arbiter_model": (
            settings.report_model
            if status in {"arbitrated", "arbitration_failed"}
            else None
        ),
        "final_model": final_model or settings.signal_model,
        "review_status": status,
        "review_reasons": reasons,
        "critical_conflicts": conflicts or [],
    }


async def _arbitrate_one(
    structured_llm,
    tweet: dict,
    primary: dict,
    review: dict,
    conflicts: list[str],
) -> dict | None:
    start = time.perf_counter()
    try:
        messages = _to_lc_messages(
            get_chat_prompt(
                "model_review/arbitrate",
                author_handle=tweet.get("author_handle", ""),
                content=tweet.get("content", ""),
                media_context=json.dumps(
                    tweet.get("media_context") or {}, ensure_ascii=False, default=str
                ),
                conversation_context=json.dumps(
                    tweet.get("conversation_context") or {}, ensure_ascii=False, default=str
                ),
                conflicts=json.dumps(conflicts, ensure_ascii=False),
                primary_result=json.dumps(primary, ensure_ascii=False, default=str),
                review_result=json.dumps(review, ensure_ascii=False, default=str),
            )
        )
        result = await asyncio.wait_for(
            structured_llm.ainvoke(messages),
            timeout=settings.report_llm_timeout_seconds,
        )
        if result is None:
            raise ValueError("arbiter returned no result")
        logger.debug(
            "[Arbiter] tweet={} latency={}ms conflicts={}",
            str(tweet.get("id") or "")[:8],
            int((time.perf_counter() - start) * 1000),
            conflicts,
        )
        return result.model_dump()
    except Exception as exc:
        logger.warning(
            "Model arbiter failed for tweet {} ({}ms): {}",
            tweet.get("id"),
            int((time.perf_counter() - start) * 1000),
            exc,
        )
        return None


async def _run_model_review(state: dict) -> dict:
    analyses = [dict(item) for item in state.get("analyses") or []]
    tweet_map = {str(item.get("id")): item for item in state.get("tweets") or []}
    classifications = {
        str(item.get("tweet_id")): item
        for item in (state.get("classification") or {}).get("classifications") or []
    }

    candidates: list[tuple[int, dict, list[str]]] = []
    for index, analysis in enumerate(analyses):
        tweet_id = str(analysis.get("tweet_id") or "")
        tweet = tweet_map.get(tweet_id)
        reasons = review_reasons(
            tweet or {}, analysis, classifications.get(tweet_id, {})
        ) if tweet else []
        analysis["model_routing"] = _routing_metadata(
            status="pending" if reasons else "not_required",
            reasons=reasons,
        )
        if tweet and reasons:
            candidates.append((index, tweet, reasons))

    if not candidates:
        return {"analyses": analyses, "phase": "reviewed"}

    review_llm = get_review_llm().with_structured_output(TweetAnalysis)
    review_results = await asyncio.gather(
        *(
            analyze_tweet_with_llm(
                review_llm,
                tweet,
                _REVIEW_CONTEXT,
                stage="IndependentReview",
            )
            for _, tweet, _ in candidates
        )
    )

    arbitration_inputs: list[tuple[int, dict, dict, list[str], list[str]]] = []
    for (index, tweet, reasons), review in zip(candidates, review_results, strict=True):
        primary = analyses[index]
        if review is None:
            primary["model_routing"] = _routing_metadata(
                status="review_failed",
                reasons=reasons,
            )
            continue
        conflicts = critical_conflicts(primary, review)
        if not conflicts:
            primary["model_routing"] = _routing_metadata(
                status="agreed",
                reasons=reasons,
            )
            continue
        arbitration_inputs.append((index, tweet, review, reasons, conflicts))

    if arbitration_inputs:
        arbiter_llm = get_report_llm().with_structured_output(TweetAnalysis)
        arbitration_results = await asyncio.gather(
            *(
                _arbitrate_one(
                    arbiter_llm,
                    tweet,
                    analyses[index],
                    review,
                    conflicts,
                )
                for index, tweet, review, _, conflicts in arbitration_inputs
            )
        )
        for (index, tweet, _, reasons, conflicts), final in zip(
            arbitration_inputs, arbitration_results, strict=True
        ):
            primary = analyses[index]
            if final is None:
                primary["model_routing"] = _routing_metadata(
                    status="arbitration_failed",
                    reasons=reasons,
                    conflicts=conflicts,
                )
                continue
            final["tweet_id"] = tweet["id"]
            final["author_handle"] = tweet["author_handle"]
            for field in _PRESERVED_SYSTEM_FIELDS:
                if field in primary:
                    final[field] = primary[field]
            final["model_routing"] = _routing_metadata(
                status="arbitrated",
                reasons=reasons,
                conflicts=conflicts,
                final_model=settings.report_model,
            )
            analyses[index] = final

    logger.info(
        "[ModelReview] total={} reviewed={} arbitrated={}",
        len(analyses),
        len(candidates),
        len(arbitration_inputs),
    )
    return {"analyses": analyses, "phase": "reviewed"}


def model_review_agent_node(state: dict) -> dict:
    """LangGraph sync entrypoint with the same event-loop bridge as analysis."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run_model_review(state)).result()
    return asyncio.run(_run_model_review(state))
