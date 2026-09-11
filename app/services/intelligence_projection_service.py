from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.instrument_claim import InstrumentClaim
from app.models.intelligence_event import IntelligenceEvent, IntelligenceTopic
from app.models.tweet import Tweet


PROJECTION_VERSION = "claim_v5"
TOPIC_WINDOW_DAYS = 7
TOPIC_SIMILARITY_THRESHOLD = 0.58


def evaluate_intelligence_eligibility(
    result: dict,
    *,
    tweet_type: str,
) -> tuple[bool, str]:
    """Evaluate only tweet-container conditions; claim conditions are separate."""
    if not result.get(
        "is_investment_relevant",
        result.get("is_investment_related", False),
    ):
        return False, "not_investment_relevant"
    return True, "eligible"


def evaluate_claim_intelligence_eligibility(
    claim: InstrumentClaim,
    *,
    tweet_type: str,
) -> tuple[bool, str]:
    if not claim.downstream_eligible:
        return False, "instrument_not_verified"
    sponsor_relation = getattr(claim, "sponsor_relation", "none")
    if sponsor_relation == "direct":
        return False, "sponsor_related"
    if sponsor_relation == "unclear":
        return False, "sponsor_relation_unclear"
    if claim.claim_type == "reference":
        return False, "reference_only"
    if not (claim.thesis or claim.evidence or claim.media_evidence):
        return False, "claim_evidence_missing"
    author_claim_types = {
        "recommendation",
        "prediction",
        "opinion",
        "risk_warning",
    }
    if claim.claim_type in author_claim_types and claim.opinion_source != "author":
        return False, "opinion_not_from_author"
    if (
        tweet_type == "retweet"
        and claim.opinion_source != "author"
        and claim.claim_type not in {"news", "fact", "recap"}
    ):
        return False, "pure_retweet"
    return True, "eligible"


def _unique_strings(values: list, *, limit: int = 5) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())[:260]


def _topic_matches(topic: IntelligenceTopic, event: IntelligenceEvent) -> bool:
    if (
        topic.primary_ticker != event.primary_ticker
        or topic.kind != event.kind
        or topic.horizon != event.horizon
    ):
        return False
    if event.kind == "opinion":
        return True
    left = _normalized_text(topic.summary)
    right = _normalized_text(event.summary)
    return bool(
        left
        and right
        and SequenceMatcher(None, left, right).ratio()
        >= TOPIC_SIMILARITY_THRESHOLD
    )


def _refresh_topic(db: Session, topic: IntelligenceTopic) -> None:
    events = list(
        db.execute(
            select(IntelligenceEvent)
            .where(
                IntelligenceEvent.topic_id == topic.id,
                IntelligenceEvent.status == "active",
            )
            .order_by(IntelligenceEvent.published_at.asc())
        ).scalars()
    )
    if not events:
        db.delete(topic)
        return

    author_rows = db.execute(
        select(IntelligenceEvent.id, func.lower(Tweet.author_handle))
        .join(
            AnalysisResult,
            AnalysisResult.id == IntelligenceEvent.analysis_result_id,
        )
        .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
        .where(IntelligenceEvent.id.in_([event.id for event in events]))
    ).all()
    author_by_event = {event_id: author for event_id, author in author_rows}
    authors = set(author_by_event.values())
    latest = events[-1]
    latest_author = author_by_event.get(latest.id, "")
    prior_same_author = [
        event.direction
        for event in events[:-1]
        if author_by_event.get(event.id) == latest_author
        and event.direction in {"bullish", "bearish"}
    ]
    author_reversal = (
        latest.direction in {"bullish", "bearish"}
        and bool(prior_same_author)
        and prior_same_author[-1] != latest.direction
    )
    bullish_authors = {
        author_by_event.get(event.id)
        for event in events
        if event.direction == "bullish"
    } - {None}
    bearish_authors = {
        author_by_event.get(event.id)
        for event in events
        if event.direction == "bearish"
    } - {None}
    cross_author_disagreement = bool(
        bullish_authors
        and bearish_authors
        and len(bullish_authors | bearish_authors) > 1
    )

    if author_reversal:
        lifecycle = "reversed"
        aggregate_direction = latest.direction
    elif cross_author_disagreement:
        lifecycle = "disputed"
        aggregate_direction = "mixed"
    elif len(authors) >= 3:
        lifecycle = "confirmed"
        aggregate_direction = latest.direction
    elif len(events) > 1:
        lifecycle = "developing"
        aggregate_direction = latest.direction
    else:
        lifecycle = "new"
        aggregate_direction = latest.direction

    topic.kind = latest.kind
    if lifecycle == "reversed":
        topic.title = f"{latest.primary_ticker} · @{latest_author} 观点方向反转"
    elif lifecycle == "disputed":
        topic.title = f"{latest.primary_ticker} 不同博主观点存在分歧"
    else:
        topic.title = latest.title
    topic.summary = latest.summary
    topic.direction = aggregate_direction
    topic.horizon = latest.horizon
    topic.primary_ticker = latest.primary_ticker
    topic.tickers = [latest.primary_ticker]
    topic.confidence = sum(event.confidence for event in events) / len(events)
    topic.source_credibility = sum(
        event.source_credibility for event in events
    ) / len(events)
    topic.risk_level = max(
        (event.risk_level for event in events),
        key=lambda value: {
            "": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }.get(value, 0),
    )
    topic.risk_factors = _unique_strings(
        [value for event in events for value in (event.risk_factors or [])]
    )
    topic.key_points = _unique_strings(
        [value for event in events for value in (event.key_points or [])]
    )
    topic.lifecycle = lifecycle
    topic.event_count = len(events)
    topic.source_count = max(1, len(authors))
    topic.first_seen_at = events[0].published_at
    topic.last_seen_at = latest.published_at
    topic.status = "active"


def _assign_event_to_topic(
    db: Session,
    event: IntelligenceEvent,
) -> IntelligenceTopic:
    previous_topic = db.get(IntelligenceTopic, event.topic_id) if event.topic_id else None
    topic = (
        previous_topic
        if previous_topic and _topic_matches(previous_topic, event)
        else None
    )
    if topic is None:
        cutoff = event.published_at - timedelta(days=TOPIC_WINDOW_DAYS)
        candidates = list(
            db.execute(
                select(IntelligenceTopic)
                .where(
                    IntelligenceTopic.status == "active",
                    IntelligenceTopic.primary_ticker == event.primary_ticker,
                    IntelligenceTopic.kind == event.kind,
                    IntelligenceTopic.horizon == event.horizon,
                    IntelligenceTopic.last_seen_at >= cutoff,
                )
                .order_by(IntelligenceTopic.last_seen_at.desc())
            ).scalars()
        )
        topic = next(
            (candidate for candidate in candidates if _topic_matches(candidate, event)),
            None,
        )
    if topic is None:
        topic = IntelligenceTopic(
            kind=event.kind,
            title=event.title,
            summary=event.summary,
            direction=event.direction,
            horizon=event.horizon,
            primary_ticker=event.primary_ticker,
            tickers=event.tickers,
            confidence=event.confidence,
            source_credibility=event.source_credibility,
            risk_level=event.risk_level,
            risk_factors=event.risk_factors,
            key_points=event.key_points,
            first_seen_at=event.published_at,
            last_seen_at=event.published_at,
        )
        db.add(topic)
        db.flush()

    event.topic_id = topic.id
    db.flush()
    _refresh_topic(db, topic)
    if previous_topic and previous_topic.id != topic.id:
        _refresh_topic(db, previous_topic)
    return topic


def expire_stale_topics(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=TOPIC_WINDOW_DAYS)
    topics = list(
        db.execute(
            select(IntelligenceTopic).where(
                IntelligenceTopic.status == "active",
                IntelligenceTopic.last_seen_at < cutoff,
            )
        ).scalars()
    )
    for topic in topics:
        topic.lifecycle = "expired"
        topic.status = "expired"
    return len(topics)


def _delete_events(
    db: Session,
    events: list[IntelligenceEvent],
) -> None:
    previous_topics = {
        event.topic_id for event in events if event.topic_id is not None
    }
    for event in events:
        db.delete(event)
    db.flush()
    for topic_id in previous_topics:
        topic = db.get(IntelligenceTopic, topic_id)
        if topic:
            _refresh_topic(db, topic)


def _prune_orphan_topics(db: Session) -> None:
    orphan_topics = list(
        db.execute(
            select(IntelligenceTopic).where(
                ~select(IntelligenceEvent.id)
                .where(IntelligenceEvent.topic_id == IntelligenceTopic.id)
                .exists()
            )
        ).scalars()
    )
    for topic in orphan_topics:
        db.delete(topic)
    if orphan_topics:
        db.flush()


def project_analysis_to_intelligence_event(
    db: Session,
    analysis_result_id: UUID | str,
    *,
    expire_topics: bool = True,
) -> dict:
    analysis_id = UUID(str(analysis_result_id))
    analysis = db.get(AnalysisResult, analysis_id)
    existing_events = list(
        db.execute(
            select(IntelligenceEvent).where(
                IntelligenceEvent.analysis_result_id == analysis_id
            )
        ).scalars()
    )
    _prune_orphan_topics(db)
    if not analysis or analysis.analysis_type != "tweet_analysis" or not analysis.result:
        _delete_events(db, existing_events)
        return {"skipped": True, "reason": "analysis_not_eligible"}

    tweet = db.get(Tweet, analysis.tweet_id)
    result = analysis.result or {}
    tweet_type = str(
        getattr(tweet, "tweet_type", "original") or "original"
    ) if tweet else "original"
    eligible, reason = evaluate_intelligence_eligibility(
        result,
        tweet_type=tweet_type,
    )
    if not tweet or not tweet.content or not eligible:
        _delete_events(db, existing_events)
        return {
            "skipped": True,
            "reason": reason if tweet else "tweet_not_found",
        }

    claims = list(
        db.execute(
            select(InstrumentClaim)
            .where(InstrumentClaim.analysis_result_id == analysis_id)
            .order_by(InstrumentClaim.claim_index)
        ).scalars()
    )
    eligible_claims = [
        claim
        for claim in claims
        if evaluate_claim_intelligence_eligibility(
            claim,
            tweet_type=tweet_type,
        )[0]
    ]
    eligible_ids = {claim.id for claim in eligible_claims}
    stale_events = [
        event for event in existing_events if event.claim_id not in eligible_ids
    ]
    if stale_events:
        _delete_events(db, stale_events)
    existing_by_claim = {
        event.claim_id: event
        for event in existing_events
        if event.claim_id in eligible_ids
    }
    if not eligible_claims:
        return {"skipped": True, "reason": "no_eligible_claim"}

    blogger = db.execute(
        select(Blogger).where(func.lower(Blogger.handle) == tweet.author_handle.lower())
    ).scalar_one_or_none()
    credibility = float(blogger.credibility_score if blogger else 50.0)
    created_count = 0
    updated_count = 0
    alerts_created = 0
    events: list[IntelligenceEvent] = []
    topics: list[IntelligenceTopic] = []
    direction_labels = {
        "bullish": "看多",
        "bearish": "看空",
        "neutral": "中性",
        "none": "无方向",
    }

    for claim in eligible_claims:
        risk_factors = _unique_strings(claim.risk_factors or [])
        key_points = _unique_strings(
            [claim.thesis, *(claim.evidence or []), *(claim.catalysts or [])]
        )
        if (
            claim.claim_type == "risk_warning"
            or claim.risk_level in {"high", "critical"}
            or len(risk_factors) >= 2
        ):
            kind = "risk"
        elif claim.claim_type in {"news", "recap", "fact"}:
            kind = "news"
        else:
            kind = "opinion"
        direction = (
            claim.direction
            if kind == "opinion"
            and claim.opinion_source == "author"
            and claim.claim_type in {"recommendation", "prediction", "opinion"}
            and claim.direction in {"bullish", "bearish", "neutral"}
            else "none"
        )
        symbol = claim.instrument_symbol
        if kind == "risk":
            title = f"{symbol} 出现新的风险线索"
        elif kind == "news":
            title = f"{symbol} · @{tweet.author_handle} 市场动态"
        else:
            title = (
                f"{symbol} · @{tweet.author_handle} "
                f"{direction_labels[direction]}观点"
            )
        summary = str(claim.thesis or "").strip()
        if not summary:
            summary = (
                key_points[0]
                if key_points
                else str(result.get("tweet_summary") or tweet.content)
            )
        summary = summary[:240]

        event = existing_by_claim.get(claim.id)
        if event is None:
            event = IntelligenceEvent(
                analysis_result_id=analysis.id,
                claim_id=claim.id,
            )
            db.add(event)
            created_count += 1
        else:
            updated_count += 1
        event.kind = kind
        event.title = title
        event.summary = summary
        event.direction = direction
        event.horizon = claim.horizon
        event.primary_ticker = symbol
        event.tickers = [symbol]
        event.confidence = claim.confidence
        event.source_credibility = credibility
        event.risk_level = claim.risk_level
        event.risk_factors = risk_factors
        event.key_points = key_points
        event.published_at = tweet.published_at
        event.projection_version = PROJECTION_VERSION
        event.status = "active"
        db.flush()

        topic = _assign_event_to_topic(db, event)
        from app.services.alert_service import publish_intelligence_alerts

        alerts_created += publish_intelligence_alerts(
            db,
            event=event,
            topic=topic,
            tweet=tweet,
        )
        events.append(event)
        topics.append(topic)

    if expire_topics:
        expire_stale_topics(db)
    return {
        "skipped": False,
        "created": created_count > 0,
        "created_count": created_count,
        "updated_count": updated_count,
        "event_id": str(events[0].id),
        "event_ids": [str(event.id) for event in events],
        "topic_id": str(topics[0].id),
        "topic_ids": list(dict.fromkeys(str(topic.id) for topic in topics)),
        "lifecycle": topics[0].lifecycle,
        "alerts_created": alerts_created,
    }


def backfill_intelligence_events(db: Session) -> dict:
    analysis_ids = list(
        db.execute(
            select(AnalysisResult.id)
            .where(AnalysisResult.analysis_type == "tweet_analysis")
            .order_by(AnalysisResult.created_at.asc())
        ).scalars()
    )
    stats = {
        "total": len(analysis_ids),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }
    for analysis_id in analysis_ids:
        try:
            result = project_analysis_to_intelligence_event(
                db,
                analysis_id,
                expire_topics=False,
            )
            db.commit()
            if result.get("skipped"):
                stats["skipped"] += 1
            else:
                stats["created"] += int(result.get("created_count") or 0)
                stats["updated"] += int(result.get("updated_count") or 0)
        except Exception:
            db.rollback()
            stats["errors"] += 1
    stats["expired"] = expire_stale_topics(db)
    db.commit()
    return stats
