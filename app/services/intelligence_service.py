from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blogger import Blogger
from app.models.intelligence_event import IntelligenceEvent, IntelligenceEvidence, IntelligenceTopic
from app.models.tracked_ticker import TrackedTicker
from app.models.user_blogger_follow import UserBloggerFollow


WINDOW_HOURS = {"24h": 24, "3d": 72, "7d": 168}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _evidence_dict(evidence: IntelligenceEvidence) -> dict:
    return {
        "source_type": evidence.source_type,
        "source_id": evidence.source_id,
        "author": evidence.author,
        "published_at": evidence.published_at,
        "excerpt": evidence.excerpt,
        "source_url": evidence.source_url,
    }


def _score_topic(
    topic: IntelligenceTopic,
    *,
    author_followed: bool,
    ticker_matched: bool,
    window_hours: int,
) -> dict[str, int]:
    confidence_value = max(0.0, min(1.0, topic.confidence))
    age_hours = max(0.0, (datetime.now(timezone.utc) - _as_utc(topic.last_seen_at)).total_seconds() / 3600)
    relevance = (18 if author_followed else 0) + (12 if ticker_matched else 0)
    freshness = round(20 * max(0.0, 1 - age_hours / window_hours))
    confidence = round(confidence_value * 15)
    credibility = round(max(0.0, min(100.0, topic.source_credibility)) / 100 * 15)
    severity_score = {"critical": 10, "high": 8, "medium": 5, "low": 2}.get(topic.risk_level, 0)
    risk = max(severity_score, min(10, len(topic.risk_factors or []) * 3))
    corroboration = min(10, max(0, topic.source_count - 1) * 5)
    quality_penalty = (-4 if not topic.tickers else 0) + (-5 if confidence_value < 0.35 else 0)
    total = max(0, min(100, relevance + freshness + confidence + credibility + risk + corroboration + quality_penalty))
    return {
        "relevance": relevance,
        "freshness": freshness,
        "confidence": confidence,
        "credibility": credibility,
        "risk": risk,
        "corroboration": corroboration,
        "quality_penalty": quality_penalty,
        "total": total,
    }


def _topic_to_item(
    topic: IntelligenceTopic,
    evidence_rows: list[IntelligenceEvidence],
    *,
    followed_handles: set[str],
    tracked_tickers: set[str],
    window_hours: int,
) -> dict | None:
    if not evidence_rows:
        return None
    evidence_rows.sort(key=lambda row: row.published_at, reverse=True)
    authors = {row.author.lower() for row in evidence_rows}
    author_followed = bool(authors & followed_handles)
    matched_tickers = sorted(set(topic.tickers or []) & tracked_tickers)
    ticker_matched = bool(matched_tickers)
    personalized_match = author_followed or ticker_matched
    match_reasons: list[str] = []
    if author_followed:
        match_reasons.append("关注博主")
    if ticker_matched:
        match_reasons.append("关注标的 " + ", ".join(matched_tickers))
    if not match_reasons:
        match_reasons.append("市场风险" if topic.kind == "risk" else "市场发现")

    score = _score_topic(
        topic,
        author_followed=author_followed,
        ticker_matched=ticker_matched,
        window_hours=window_hours,
    )
    labels = {
        "relevance": "与你的关注范围相关",
        "freshness": "最近出现新证据",
        "confidence": "模型判断置信度较高",
        "credibility": "信息源历史可信度较高",
        "risk": "包含重要风险线索",
        "corroboration": "存在独立来源交叉印证",
    }
    ranked = sorted(
        ((key, value) for key, value in score.items() if key in labels and value > 0),
        key=lambda pair: pair[1],
        reverse=True,
    )
    age_hours = max(0.0, (datetime.now(timezone.utc) - _as_utc(topic.last_seen_at)).total_seconds() / 3600)
    time_bucket = "今日" if age_hours <= 24 else "近 3 日" if age_hours <= 72 else "近 7 日"
    evidence = [_evidence_dict(row) for row in evidence_rows[:5]]
    return {
        "id": str(topic.id),
        "kind": topic.kind,
        "title": topic.title,
        "summary": topic.summary,
        "direction": topic.direction,
        "tickers": topic.tickers or [],
        "author": evidence_rows[0].author,
        "confidence": topic.confidence,
        "source_credibility": topic.source_credibility,
        "importance_score": score["total"],
        "score_breakdown": score,
        "score_explanation": [labels[key] for key, _ in ranked[:3]],
        "risk_factors": topic.risk_factors or [],
        "key_points": topic.key_points or [],
        "published_at": topic.last_seen_at,
        "first_seen_at": topic.first_seen_at,
        "last_seen_at": topic.last_seen_at,
        "time_bucket": time_bucket,
        "lifecycle": topic.lifecycle,
        "event_count": topic.event_count,
        "match_reasons": match_reasons,
        "feed_bucket": "personalized" if personalized_match else ("market_risk" if topic.kind == "risk" else "discovery"),
        "corroboration_count": topic.source_count,
        "evidence": evidence[0],
        "supporting_evidence": evidence,
        "_personalized": personalized_match,
        "_primary_ticker": topic.primary_ticker,
    }


def _select_with_quotas(candidates: list[dict], *, limit: int, personalized: bool) -> list[dict]:
    selected: list[dict] = []
    author_counts: dict[str, int] = {}
    ticker_counts: dict[str, int] = {}

    def take(pool: list[dict], count: int, *, author_cap: int = 3, ticker_cap: int = 4) -> None:
        for item in pool:
            if len(selected) >= limit or count <= 0 or item in selected:
                continue
            author = item["author"].lower()
            ticker = item["_primary_ticker"]
            if author_counts.get(author, 0) >= author_cap or ticker_counts.get(ticker, 0) >= ticker_cap:
                continue
            selected.append(item)
            author_counts[author] = author_counts.get(author, 0) + 1
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
            count -= 1

    personalized_pool = [item for item in candidates if item["_personalized"]]
    risk_pool = [item for item in candidates if not item["_personalized"] and item["kind"] == "risk"]
    discovery_pool = [item for item in candidates if not item["_personalized"] and item["kind"] != "risk"]
    if personalized:
        personal_quota = math.ceil(limit * 0.7)
        risk_quota = math.ceil(limit * 0.2)
        take(personalized_pool, personal_quota)
        take(risk_pool, risk_quota)
        take(discovery_pool, limit - personal_quota - risk_quota)
    else:
        take(risk_pool, math.ceil(limit * 0.3))
        take(discovery_pool, limit)
    take(candidates, limit)
    if len(selected) < limit:
        take(candidates, limit, author_cap=6, ticker_cap=8)
    return selected


def build_user_intelligence_feed(
    db: Session,
    user_id: UUID,
    *,
    limit: int = 20,
    window: str = "24h",
    kind: str = "all",
) -> tuple[list[dict], dict]:
    window_hours = WINDOW_HOURS.get(window, 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    followed_handles = {
        handle.lower()
        for handle in db.execute(
            select(Blogger.handle)
            .join(UserBloggerFollow, UserBloggerFollow.blogger_id == Blogger.id)
            .where(UserBloggerFollow.user_id == user_id)
        ).scalars()
    }
    tracked_tickers = {
        ticker.upper()
        for ticker in db.execute(
            select(TrackedTicker.ticker).where(TrackedTicker.user_id == user_id, TrackedTicker.status == "active")
        ).scalars()
    }
    topic_query = select(IntelligenceTopic).where(
        IntelligenceTopic.status == "active",
        IntelligenceTopic.last_seen_at >= cutoff,
    )
    if kind != "all":
        topic_query = topic_query.where(IntelligenceTopic.kind == kind)
    topics = list(db.execute(topic_query.order_by(IntelligenceTopic.last_seen_at.desc())).scalars())
    topic_ids = [topic.id for topic in topics]
    evidence_map: dict[UUID, list[IntelligenceEvidence]] = {topic_id: [] for topic_id in topic_ids}
    if topic_ids:
        rows = db.execute(
            select(IntelligenceEvent.topic_id, IntelligenceEvidence)
            .join(IntelligenceEvidence, IntelligenceEvidence.event_id == IntelligenceEvent.id)
            .where(IntelligenceEvent.topic_id.in_(topic_ids))
            .order_by(IntelligenceEvidence.published_at.desc())
        ).all()
        for topic_id, evidence in rows:
            evidence_map[topic_id].append(evidence)

    candidates = [
        item
        for topic in topics
        if (item := _topic_to_item(
            topic,
            evidence_map.get(topic.id, []),
            followed_handles=followed_handles,
            tracked_tickers=tracked_tickers,
            window_hours=window_hours,
        ))
    ]
    candidates.sort(key=lambda item: (item["importance_score"], item["published_at"]), reverse=True)
    personalized = bool(followed_handles or tracked_tickers)
    selected = _select_with_quotas(candidates, limit=limit, personalized=personalized)
    fallback = personalized and any(not item["_personalized"] for item in selected)
    personalized_candidates = sum(1 for item in candidates if item["_personalized"])
    market_candidates = len(candidates) - personalized_candidates
    for item in selected:
        item.pop("_personalized", None)
        item.pop("_primary_ticker", None)
    return selected, {
        "followed_bloggers": len(followed_handles),
        "tracked_tickers": len(tracked_tickers),
        "personalized": personalized,
        "fallback_to_market": fallback,
        "candidate_total": len(candidates),
        "personalized_candidates": personalized_candidates,
        "market_candidates": market_candidates,
        "window": window,
        "kind": kind,
        "generated_at": datetime.now(timezone.utc),
    }
