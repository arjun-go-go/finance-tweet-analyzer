from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.instrument_claim import InstrumentClaim
from app.models.intelligence_correction import IntelligenceCorrection
from app.models.intelligence_event import IntelligenceEvent, IntelligenceTopic
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.models.tracked_ticker import TrackedTicker
from app.models.tweet import Tweet
from app.models.tweet_media_analysis import TweetMediaAnalysis
from app.models.tweet_media_asset import TweetMediaAsset
from app.models.user_blogger_follow import UserBloggerFollow
from app.services.instrument_claim_service import serialize_instrument_claim


WINDOW_HOURS = {"24h": 24, "3d": 72, "7d": 168}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _evidence_dict(tweet: Tweet) -> dict:
    return {
        "source_type": "tweet",
        "source_id": str(tweet.id),
        "author": tweet.author_handle,
        "published_at": tweet.published_at,
        "excerpt": tweet.content[:500],
        "source_url": f"https://x.com/{tweet.author_handle.lstrip('@')}/status/{tweet.tweet_id}",
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
    evidence_rows: list[dict],
    *,
    followed_handles: set[str],
    tracked_tickers: set[str],
    window_hours: int,
) -> dict | None:
    if not evidence_rows:
        return None
    evidence_rows.sort(key=lambda row: row["published_at"], reverse=True)
    evidence_rows = list(
        {
            str(row["source_id"]): row
            for row in reversed(evidence_rows)
        }.values()
    )
    evidence_rows.sort(key=lambda row: row["published_at"], reverse=True)
    authors = {str(row["author"]).lower() for row in evidence_rows}
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
    age_hours = max(
        0.0,
        (datetime.now(timezone.utc) - _as_utc(topic.last_seen_at)).total_seconds()
        / 3600,
    )
    time_bucket = (
        "今日" if age_hours <= 24 else "近 3 日" if age_hours <= 72 else "近 7 日"
    )
    evidence = evidence_rows[:5]
    return {
        "id": str(topic.id),
        "kind": topic.kind,
        "title": topic.title,
        "summary": topic.summary,
        "direction": topic.direction,
        "horizon": topic.horizon,
        "tickers": topic.tickers or [],
        "author": evidence_rows[0]["author"],
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
        "feed_bucket": (
            "personalized"
            if personalized_match
            else ("market_risk" if topic.kind == "risk" else "discovery")
        ),
        "corroboration_count": topic.source_count,
        "evidence": evidence[0],
        "supporting_evidence": evidence,
        "_personalized": personalized_match,
        "_primary_ticker": topic.primary_ticker,
    }


def _tweet_relationship(tweet: Tweet, primary: Tweet, event_tweet_ids: set[UUID]) -> str:
    if tweet.id == primary.id:
        return "primary"
    if tweet.tweet_id == primary.in_reply_to_tweet_id:
        return "parent"
    if tweet.tweet_id == primary.quoted_tweet_id:
        return "quoted"
    if tweet.tweet_id == primary.reposted_tweet_id:
        return "reposted"
    if tweet.in_reply_to_tweet_id == primary.tweet_id:
        return "reply"
    if tweet.id in event_tweet_ids:
        return "supporting"
    return "thread"


def _tweet_detail(tweet: Tweet, *, relationship: str) -> dict:
    return {
        "id": str(tweet.id),
        "tweet_id": tweet.tweet_id,
        "author_handle": tweet.author_handle,
        "author_name": tweet.author_name or "",
        "content": tweet.content,
        "published_at": tweet.published_at,
        "relationship": relationship,
        "tweet_type": tweet.tweet_type or "original",
        "conversation_tweet_id": tweet.conversation_tweet_id,
        "in_reply_to_tweet_id": tweet.in_reply_to_tweet_id,
        "quoted_tweet_id": tweet.quoted_tweet_id,
        "reposted_tweet_id": tweet.reposted_tweet_id,
        "referenced_tweets": tweet.referenced_tweets or [],
        "source_url": (
            f"https://x.com/{tweet.author_handle.lstrip('@')}/status/{tweet.tweet_id}"
        ),
    }


def _analysis_detail(analysis: AnalysisResult) -> dict:
    result = analysis.result or {}
    keys = (
        "tweet_summary",
        "reasoning",
        "is_sponsored",
        "commercial_disclosure",
        "media_summary",
        "media_confidence",
        "text_image_consistency",
    )
    return {
        **{key: result.get(key) for key in keys},
        "confidence": float(result.get("confidence") or analysis.confidence or 0),
    }


def _verification_detail(
    verification: PredictionMarketVerification | None,
) -> dict | None:
    if verification is None:
        return None
    evidence = verification.evidence or {}
    return {
        "id": str(verification.id),
        "verification_type": verification.verification_type,
        "status": verification.status,
        "provider": verification.provider,
        "provider_symbol": verification.provider_symbol,
        "market": verification.market,
        "start_observed_at": verification.start_observed_at,
        "start_price": verification.start_price,
        "end_observed_at": verification.end_observed_at,
        "end_price": verification.end_price,
        "directional_return": verification.directional_return,
        "threshold": verification.threshold,
        "proposed_verdict": verification.proposed_verdict,
        "reason": evidence.get("reason") or verification.error_message,
        "identity": evidence.get("identity"),
        "identity_reason": evidence.get("identity_reason"),
        "rule_version": verification.rule_version,
        "observation": verification.observation or {},
        "applied": verification.applied,
        "created_at": verification.created_at,
    }


def _prediction_detail(
    prediction: Prediction,
    verification: PredictionMarketVerification | None,
) -> dict:
    return {
        "id": str(prediction.id),
        "claim_id": str(prediction.claim_id) if prediction.claim_id else None,
        "ticker": prediction.ticker,
        "sentiment": prediction.sentiment,
        "prediction_type": prediction.prediction_type,
        "target_spec": prediction.target_spec or {},
        "temporal_expression": prediction.temporal_expression,
        "investment_horizon": prediction.investment_horizon,
        "horizon_source": prediction.horizon_source,
        "time_confidence": prediction.time_confidence,
        "published_at": prediction.published_at,
        "verifiable_at": prediction.verifiable_at,
        "verifier_type": prediction.verifier_type,
        "scoring_eligible": prediction.scoring_eligible,
        "verification_policy_version": prediction.verification_policy_version,
        "verdict": prediction.verdict,
        "score": prediction.score,
        "verified_at": prediction.verified_at,
        "verified_by": prediction.verified_by,
        "note": prediction.note,
        "instrument_snapshot": prediction.instrument_snapshot,
        "creation_rule_version": prediction.creation_rule_version,
        "creation_evidence": prediction.creation_evidence,
        "market_verification": _verification_detail(verification),
    }


def build_user_intelligence_detail(
    db: Session,
    user_id: UUID,
    topic_id: UUID | str,
) -> dict | None:
    """Assemble one evidence-first topic detail without invoking an LLM."""
    topic = db.get(IntelligenceTopic, UUID(str(topic_id)))
    if topic is None:
        return None

    event_rows = db.execute(
        select(IntelligenceEvent, AnalysisResult, Tweet)
        .join(AnalysisResult, AnalysisResult.id == IntelligenceEvent.analysis_result_id)
        .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
        .where(IntelligenceEvent.topic_id == topic.id)
        .order_by(IntelligenceEvent.published_at.desc())
    ).all()
    if not event_rows:
        return None

    evidence_rows = [_evidence_dict(tweet) for _event, _analysis, tweet in event_rows]
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
            select(TrackedTicker.ticker).where(
                TrackedTicker.user_id == user_id,
                TrackedTicker.status == "active",
            )
        ).scalars()
    }
    item = _topic_to_item(
        topic,
        evidence_rows,
        followed_handles=followed_handles,
        tracked_tickers=tracked_tickers,
        window_hours=168,
    )
    if item is None:
        return None
    item.pop("_personalized", None)
    item.pop("_primary_ticker", None)

    primary_event, primary_analysis, primary_tweet = event_rows[0]
    event_claim_ids = {
        event.claim_id
        for event, _analysis, _tweet in event_rows
        if event.claim_id is not None
    }
    claim_rows = list(
        db.execute(
            select(InstrumentClaim).where(
                InstrumentClaim.id.in_(event_claim_ids)
            ).order_by(InstrumentClaim.claim_index)
        ).scalars()
    ) if event_claim_ids else []
    claim_map = {claim.id: claim for claim in claim_rows}
    primary_claim = claim_map.get(primary_event.claim_id)
    event_tweet_ids = {tweet.id for _event, _analysis, tweet in event_rows}
    conversation_keys = {
        value
        for _event, _analysis, tweet in event_rows
        for value in (tweet.conversation_tweet_id, tweet.tweet_id)
        if value
    }
    referenced_ids = {
        value
        for value in (
            primary_tweet.in_reply_to_tweet_id,
            primary_tweet.quoted_tweet_id,
            primary_tweet.reposted_tweet_id,
        )
        if value
    }
    thread_rows = list(
        db.execute(
            select(Tweet)
            .where(
                or_(
                    Tweet.id.in_(event_tweet_ids),
                    Tweet.conversation_tweet_id.in_(conversation_keys),
                    Tweet.tweet_id.in_(conversation_keys | referenced_ids),
                )
            )
            .order_by(Tweet.published_at.asc())
        ).scalars()
    )

    media_analysis_rows = list(
        db.execute(
            select(TweetMediaAnalysis).where(
                TweetMediaAnalysis.tweet_id.in_(event_tweet_ids)
            )
        ).scalars()
    )
    media_analysis_map = {row.tweet_id: row for row in media_analysis_rows}
    media_assets = list(
        db.execute(
            select(TweetMediaAsset)
            .where(TweetMediaAsset.tweet_id.in_(event_tweet_ids))
            .order_by(TweetMediaAsset.tweet_id, TweetMediaAsset.created_at.asc())
        ).scalars()
    )
    asset_indexes: dict[UUID, int] = {}
    media: list[dict] = []
    for asset in media_assets:
        image_index = asset_indexes.get(asset.tweet_id, 0)
        asset_indexes[asset.tweet_id] = image_index + 1
        media_analysis = media_analysis_map.get(asset.tweet_id)
        image_results = (
            (media_analysis.result or {}).get("images") or []
            if media_analysis is not None
            else []
        )
        media.append(
            {
                "id": str(asset.id),
                "tweet_id": str(asset.tweet_id),
                "width": asset.width,
                "height": asset.height,
                "content_type": asset.content_type,
                "status": asset.status,
                "error_detail": asset.error_detail,
                "analysis_status": media_analysis.status if media_analysis else None,
                "analysis": (
                    image_results[image_index]
                    if image_index < len(image_results)
                    else None
                ),
            }
        )

    predictions = list(
        db.execute(
            select(Prediction)
            .where(Prediction.claim_id.in_(event_claim_ids))
            .order_by(Prediction.published_at.desc())
        ).scalars()
    ) if event_claim_ids else []
    prediction_ids = [prediction.id for prediction in predictions]
    latest_verifications: dict[UUID, PredictionMarketVerification] = {}
    if prediction_ids:
        verification_rows = db.execute(
            select(PredictionMarketVerification)
            .where(PredictionMarketVerification.prediction_id.in_(prediction_ids))
            .order_by(
                PredictionMarketVerification.prediction_id,
                PredictionMarketVerification.created_at.desc(),
            )
        ).scalars()
        for verification in verification_rows:
            latest_verifications.setdefault(verification.prediction_id, verification)

    return {
        "item": item,
        "tweet": _tweet_detail(primary_tweet, relationship="primary"),
        "thread": [
            _tweet_detail(
                tweet,
                relationship=_tweet_relationship(
                    tweet, primary_tweet, event_tweet_ids
                ),
            )
            for tweet in thread_rows
        ],
        "media": media,
        "analysis": _analysis_detail(primary_analysis),
        "claim": (
            serialize_instrument_claim(primary_claim)
            if primary_claim is not None
            else None
        ),
        "claims": [
            serialize_instrument_claim(claim)
            for claim in claim_rows
        ],
        "instruments": (
            [primary_claim.instrument_snapshot]
            if primary_claim is not None
            else []
        ),
        "predictions": [
            _prediction_detail(
                prediction, latest_verifications.get(prediction.id)
            )
            for prediction in predictions
        ],
        "audit": [
            {
                "event_id": str(event.id),
                "analysis_id": str(analysis.id),
                "claim_id": str(event.claim_id) if event.claim_id else None,
                "tweet_id": str(tweet.id),
                "model_used": analysis.model_used,
                "pipeline_version": analysis.pipeline_version,
                "projection_version": event.projection_version,
                "analysis_created_at": analysis.created_at,
                "projected_at": event.created_at,
                "status": event.status,
            }
            for event, analysis, tweet in event_rows
        ],
    }


def submit_intelligence_correction(
    db: Session,
    *,
    user_id: UUID,
    topic_id: UUID | str,
    category: str,
    note: str,
) -> IntelligenceCorrection | None:
    topic = db.get(IntelligenceTopic, UUID(str(topic_id)))
    if topic is None:
        return None
    correction = IntelligenceCorrection(
        topic_id=topic.id,
        user_id=user_id,
        category=category,
        note=note.strip(),
        snapshot={
            "title": topic.title,
            "summary": topic.summary,
            "direction": topic.direction,
            "tickers": topic.tickers or [],
            "lifecycle": topic.lifecycle,
            "topic_updated_at": (
                topic.updated_at.isoformat() if topic.updated_at else None
            ),
        },
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction


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
    evidence_map: dict[UUID, list[dict]] = {topic_id: [] for topic_id in topic_ids}
    if topic_ids:
        rows = db.execute(
            select(IntelligenceEvent.topic_id, Tweet)
            .join(AnalysisResult, AnalysisResult.id == IntelligenceEvent.analysis_result_id)
            .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
            .where(IntelligenceEvent.topic_id.in_(topic_ids))
            .order_by(Tweet.published_at.desc())
        ).all()
        for topic_id, tweet in rows:
            evidence_map[topic_id].append(_evidence_dict(tweet))

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


def build_user_daily_digest(db: Session, user_id: UUID) -> dict:
    """Build an evidence-backed 24-hour Twitter digest for one user's research scope.

    The digest is deliberately deterministic: every highlighted conclusion comes
    from an existing intelligence item and keeps its original tweet evidence.
    """
    items, context = build_user_intelligence_feed(
        db,
        user_id,
        limit=40,
        window="24h",
        kind="all",
    )
    personalized = [item for item in items if item["feed_bucket"] == "personalized"]
    digest_items = personalized or items
    risks = [
        item
        for item in items
        if item["kind"] == "risk" or item["lifecycle"] == "reversed"
    ]
    risks.sort(
        key=lambda item: (
            item["lifecycle"] == "reversed",
            item["importance_score"],
            item["published_at"],
        ),
        reverse=True,
    )

    authors = {
        evidence["author"].lower()
        for item in items
        for evidence in item["supporting_evidence"]
    }
    tickers = {ticker for item in items for ticker in item["tickers"]}
    metrics = {
        "signal_count": len(items),
        "personalized_count": len(personalized),
        "source_count": len(authors),
        "ticker_count": len(tickers),
        "opinion_count": sum(item["kind"] == "opinion" for item in items),
        "news_count": sum(item["kind"] == "news" for item in items),
        "risk_count": sum(item["kind"] == "risk" for item in items),
        "reversal_count": sum(item["lifecycle"] == "reversed" for item in items),
        "corroborated_count": sum(item["corroboration_count"] > 1 for item in items),
    }

    has_scope = bool(context["personalized"])
    if not has_scope:
        status = "scope_empty"
        summary = "你尚未设置关注博主或监控标的，当前日报展示市场补充情报。完善研究范围后会自动切换为个性化日报。"
    elif not items:
        status = "empty"
        summary = "过去 24 小时内，尚未发现通过投资相关性、来源归属和内容质量筛选的新情报。"
    elif not personalized:
        status = "empty"
        summary = "过去 24 小时内没有匹配你关注范围的新情报，以下内容仅作为市场风险补充。"
    else:
        status = "ready"
        clauses = [
            f"过去 24 小时，关注范围内出现 {len(personalized)} 条有效情报",
            f"覆盖 {len(authors)} 个独立来源、{len(tickers)} 个标的",
        ]
        if metrics["risk_count"]:
            clauses.append(f"其中 {metrics['risk_count']} 条风险线索")
        if metrics["reversal_count"]:
            clauses.append(f"{metrics['reversal_count']} 条观点反转")
        summary = "；".join(clauses) + "。"

    generated_at = context["generated_at"]
    return {
        "status": status,
        "title": "Twitter 投资情报日报",
        "executive_summary": summary,
        "generated_at": generated_at,
        "period_start": generated_at - timedelta(hours=24),
        "period_end": generated_at,
        "metrics": metrics,
        "highlights": digest_items[:5],
        "attention": risks[:3],
        "context": context,
        "methodology": "仅汇总已完成结构化分析并保留原始推文证据的内容；不把广告、第三方转述或非投资讨论写入结论。",
    }
