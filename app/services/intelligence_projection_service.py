from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.intelligence_event import IntelligenceEvent, IntelligenceTopic
from app.models.tweet import Tweet
from app.services.instrument_resolver import verified_ticker_symbols


PROJECTION_VERSION = "v3"
TOPIC_WINDOW_DAYS = 7
TOPIC_SIMILARITY_THRESHOLD = 0.58


def _ticker_symbols(result: dict) -> list[str]:
    return verified_ticker_symbols(result)


def evaluate_intelligence_eligibility(result: dict, *, tweet_type: str) -> tuple[bool, str]:
    """决定一条推文分析是否值得进入今日情报。"""
    if not result.get("is_investment_relevant", result.get("is_investment_related", False)):
        return False, "not_investment_relevant"
    if result.get("is_sponsored"):
        return False, "sponsored_content"

    statement_type = str(result.get("statement_type") or "non_investment").lower()
    if statement_type == "non_investment":
        return False, "non_investment_statement"

    opinion_source = str(result.get("opinion_source") or "unclear").lower()
    author_statements = {"recommendation", "prediction", "risk_warning", "opinion"}
    if statement_type in author_statements and opinion_source != "author":
        return False, "opinion_not_from_author"
    if tweet_type == "retweet" and opinion_source != "author" and statement_type not in {"news_relay", "fact"}:
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
    if topic.primary_ticker != event.primary_ticker or topic.kind != event.kind:
        return False
    left = _normalized_text(topic.summary)
    right = _normalized_text(event.summary)
    return bool(left and right and SequenceMatcher(None, left, right).ratio() >= TOPIC_SIMILARITY_THRESHOLD)


def _refresh_topic(db: Session, topic: IntelligenceTopic) -> None:
    events = list(
        db.execute(
            select(IntelligenceEvent)
            .where(IntelligenceEvent.topic_id == topic.id, IntelligenceEvent.status == "active")
            .order_by(IntelligenceEvent.published_at.asc())
        ).scalars()
    )
    if not events:
        db.delete(topic)
        return

    authors = set(
        db.execute(
            select(func.lower(Tweet.author_handle))
            .join(AnalysisResult, AnalysisResult.tweet_id == Tweet.id)
            .join(IntelligenceEvent, IntelligenceEvent.analysis_result_id == AnalysisResult.id)
            .where(IntelligenceEvent.id.in_([event.id for event in events]))
        ).scalars()
    )
    latest = events[-1]
    previous_directions = [event.direction for event in events[:-1] if event.direction in {"bullish", "bearish"}]
    reversed_direction = (
        latest.direction in {"bullish", "bearish"}
        and bool(previous_directions)
        and previous_directions[-1] != latest.direction
    )
    if reversed_direction:
        lifecycle = "reversed"
    elif len(authors) >= 3:
        lifecycle = "confirmed"
    elif len(events) > 1:
        lifecycle = "developing"
    else:
        lifecycle = "new"

    topic.kind = latest.kind
    topic.title = (
        f"{latest.primary_ticker} 观点方向出现反转"
        if lifecycle == "reversed"
        else latest.title
    )
    topic.summary = latest.summary
    topic.direction = latest.direction
    topic.primary_ticker = latest.primary_ticker
    topic.tickers = _unique_strings([ticker for event in events for ticker in (event.tickers or [])])
    topic.confidence = sum(event.confidence for event in events) / len(events)
    topic.source_credibility = sum(event.source_credibility for event in events) / len(events)
    topic.risk_level = max(
        (event.risk_level for event in events),
        key=lambda value: {"": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(value, 0),
    )
    topic.risk_factors = _unique_strings([value for event in events for value in (event.risk_factors or [])])
    topic.key_points = _unique_strings([value for event in events for value in (event.key_points or [])])
    topic.lifecycle = lifecycle
    topic.event_count = len(events)
    topic.source_count = max(1, len(authors))
    topic.first_seen_at = events[0].published_at
    topic.last_seen_at = latest.published_at
    topic.status = "active"


def _assign_event_to_topic(db: Session, event: IntelligenceEvent) -> IntelligenceTopic:
    previous_topic = db.get(IntelligenceTopic, event.topic_id) if event.topic_id else None
    topic = previous_topic if previous_topic and _topic_matches(previous_topic, event) else None
    if topic is None:
        cutoff = event.published_at - timedelta(days=TOPIC_WINDOW_DAYS)
        candidates = list(
            db.execute(
                select(IntelligenceTopic)
                .where(
                    IntelligenceTopic.status == "active",
                    IntelligenceTopic.primary_ticker == event.primary_ticker,
                    IntelligenceTopic.kind == event.kind,
                    IntelligenceTopic.last_seen_at >= cutoff,
                )
                .order_by(IntelligenceTopic.last_seen_at.desc())
            ).scalars()
        )
        topic = next((candidate for candidate in candidates if _topic_matches(candidate, event)), None)
    if topic is None:
        topic = IntelligenceTopic(
            kind=event.kind,
            title=event.title,
            summary=event.summary,
            direction=event.direction,
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


def project_analysis_to_intelligence_event(
    db: Session,
    analysis_result_id: UUID | str,
    *,
    expire_topics: bool = True,
) -> dict:
    analysis_id = UUID(str(analysis_result_id))
    analysis = db.get(AnalysisResult, analysis_id)
    existing = db.execute(
        select(IntelligenceEvent).where(IntelligenceEvent.analysis_result_id == analysis_id)
    ).scalar_one_or_none()
    if not analysis or analysis.analysis_type != "tweet_analysis" or not analysis.result:
        if existing:
            previous_topic = db.get(IntelligenceTopic, existing.topic_id) if existing.topic_id else None
            db.delete(existing)
            db.flush()
            if previous_topic:
                _refresh_topic(db, previous_topic)
        return {"skipped": True, "reason": "analysis_not_eligible"}

    tweet = db.get(Tweet, analysis.tweet_id)
    result = analysis.result or {}
    eligible, eligibility_reason = evaluate_intelligence_eligibility(
        result,
        tweet_type=str(getattr(tweet, "tweet_type", "original") or "original") if tweet else "original",
    )
    if not tweet or not tweet.content or not eligible:
        if existing:
            previous_topic = db.get(IntelligenceTopic, existing.topic_id) if existing.topic_id else None
            db.delete(existing)
            db.flush()
            if previous_topic:
                _refresh_topic(db, previous_topic)
        return {"skipped": True, "reason": eligibility_reason if tweet else "tweet_not_found"}

    blogger = db.execute(
        select(Blogger).where(func.lower(Blogger.handle) == tweet.author_handle.lower())
    ).scalar_one_or_none()
    tickers = _ticker_symbols(result)
    direction = str(result.get("overall_sentiment") or "neutral").lower()
    if direction not in {"bullish", "bearish", "neutral", "mixed"}:
        direction = "neutral"
    direction_label = {"bullish": "看多", "bearish": "看空", "neutral": "中性", "mixed": "分歧"}[direction]
    risk_factors = _unique_strings(result.get("risk_factors") or [])
    key_points = _unique_strings(result.get("key_points") or [])
    risk_level = str(result.get("risk_level") or "").lower()
    statement_type = str(result.get("statement_type") or "opinion").lower()
    if statement_type == "risk_warning" or risk_level in {"high", "critical"} or len(risk_factors) >= 2:
        kind = "risk"
    elif statement_type in {"news_relay", "recap", "fact"}:
        kind = "news"
    else:
        kind = "opinion"
    primary_ticker = tickers[0] if tickers else "市场"
    if kind == "risk":
        title = f"{primary_ticker} 出现新的风险线索"
    elif kind == "news":
        title = f"{primary_ticker} · @{tweet.author_handle} 转述市场动态"
    else:
        title = f"{primary_ticker} · @{tweet.author_handle} {direction_label}观点"
    summary = str(result.get("thesis") or "").strip()
    if not summary:
        summary = key_points[0] if key_points else str(result.get("risk_summary") or result.get("reasoning") or tweet.content)
    summary = summary[:240]
    confidence = float(result.get("confidence") or analysis.confidence or 0)
    credibility = float(blogger.credibility_score if blogger else 50.0)

    created = existing is None
    event = existing or IntelligenceEvent(analysis_result_id=analysis.id)
    event.kind = kind
    event.title = title
    event.summary = summary
    event.direction = direction
    event.primary_ticker = primary_ticker
    event.tickers = tickers
    event.confidence = confidence
    event.source_credibility = credibility
    event.risk_level = risk_level
    event.risk_factors = risk_factors
    event.key_points = key_points
    event.published_at = tweet.published_at
    event.projection_version = PROJECTION_VERSION
    event.status = "active"
    if created:
        db.add(event)
    db.flush()

    topic = _assign_event_to_topic(db, event)
    from app.services.alert_service import publish_intelligence_alerts

    alerts_created = publish_intelligence_alerts(db, event=event, topic=topic, tweet=tweet)
    if expire_topics:
        expire_stale_topics(db)
    return {
        "skipped": False,
        "created": created,
        "event_id": str(event.id),
        "topic_id": str(topic.id),
        "lifecycle": topic.lifecycle,
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
    stats = {"total": len(analysis_ids), "created": 0, "updated": 0, "skipped": 0, "errors": 0}
    for analysis_id in analysis_ids:
        try:
            result = project_analysis_to_intelligence_event(db, analysis_id, expire_topics=False)
            db.commit()
            if result.get("skipped"):
                stats["skipped"] += 1
            elif result.get("created"):
                stats["created"] += 1
            else:
                stats["updated"] += 1
        except Exception:
            db.rollback()
            stats["errors"] += 1
    stats["expired"] = expire_stale_topics(db)
    db.commit()
    return stats
