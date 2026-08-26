"""Blogger CRUD + aggregation queries."""
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.blogger import Blogger
from app.models.outbox_event import OutboxEvent
from app.models.prediction import Prediction
from app.models.prediction_market_verification import PredictionMarketVerification
from app.models.tweet import Tweet
from app.schemas.blogger import BloggerProfile
from app.services.credibility import SCORED_VERDICTS, score_profile


def get_blogger_processing_counts(
    db: Session, handles: list[str]
) -> dict[str, dict]:
    """Return one compact processing snapshot per Twitter handle."""
    normalized = sorted({handle.lower() for handle in handles if handle})
    if not normalized:
        return {}
    rows = db.execute(
        select(
            func.lower(Tweet.author_handle).label("handle"),
            func.count(Tweet.id).label("collected"),
            func.count(Tweet.id)
            .filter(Tweet.status == "analyzed")
            .label("analyzed"),
            func.count(Tweet.id)
            .filter(Tweet.status == "failed")
            .label("failed"),
            func.max(
                func.coalesce(Tweet.processing_updated_at, Tweet.created_at)
            ).label("last_activity_at"),
        )
        .where(func.lower(Tweet.author_handle).in_(normalized))
        .group_by(func.lower(Tweet.author_handle))
    ).all()
    result: dict[str, dict] = {}
    for handle, collected, analyzed, failed, last_activity_at in rows:
        total = int(collected or 0)
        complete = int(analyzed or 0)
        terminal_failed = int(failed or 0)
        result[str(handle)] = {
            "collected_tweets": total,
            "analyzed_tweets": complete,
            "processing_tweets": max(total - complete - terminal_failed, 0),
            "failed_tweets": terminal_failed,
            "last_activity_at": last_activity_at,
        }
    return result


def blogger_ingestion_summary(blogger: Blogger, counts: dict | None = None) -> dict:
    snapshot = counts or {}
    collected = int(snapshot.get("collected_tweets", 0))
    analyzed = int(snapshot.get("analyzed_tweets", 0))
    processing = int(snapshot.get("processing_tweets", 0))
    failed = int(snapshot.get("failed_tweets", 0))

    if not blogger.fetch_enabled:
        stage = "paused"
    elif blogger.last_fetched_at is None and collected == 0:
        stage = "syncing"
    elif processing > 0:
        stage = "analyzing"
    elif failed > 0:
        stage = "attention"
    else:
        stage = "ready"

    activity_candidates = [
        value
        for value in (blogger.last_fetched_at, snapshot.get("last_activity_at"))
        if value is not None
    ]
    return {
        "fetch_enabled": bool(blogger.fetch_enabled),
        "last_fetched_at": blogger.last_fetched_at,
        "last_activity_at": max(activity_candidates) if activity_candidates else None,
        "collected_tweets": collected,
        "analyzed_tweets": analyzed,
        "processing_tweets": processing,
        "failed_tweets": failed,
        "ingestion_stage": stage,
    }


def get_blogger_ingestion_status(db: Session, blogger: Blogger) -> dict:
    counts = get_blogger_processing_counts(db, [blogger.handle]).get(
        blogger.handle.lower(), {}
    )
    summary = blogger_ingestion_summary(blogger, counts)
    stage = summary["ingestion_stage"]

    if stage == "syncing":
        event = db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == "blogger.fetch_requested",
                OutboxEvent.payload["blogger_handle"].as_string() == blogger.handle,
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        dispatched = event is not None and event.status == "dispatched"
        message = (
            "采集任务已启动，正在获取公开推文与关联图片。"
            if dispatched
            else "资料已保存，正在等待采集任务执行。"
        )
        progress = 35 if dispatched else 15
    elif stage == "analyzing":
        message = (
            f"已采集 {summary['collected_tweets']} 条推文，"
            f"还有 {summary['processing_tweets']} 条正在分析。"
        )
        total = max(summary["collected_tweets"], 1)
        progress = min(95, 40 + round(summary["analyzed_tweets"] / total * 55))
    elif stage == "attention":
        message = f"有 {summary['failed_tweets']} 条推文处理失败，已有内容仍可查看。"
        progress = 100
    elif stage == "paused":
        message = "定时采集已暂停，已经保存的推文和分析结果仍会保留。"
        progress = 100
    elif summary["collected_tweets"] == 0:
        message = "首次同步已完成，暂未发现可采集的公开推文。"
        progress = 100
    else:
        message = (
            f"采集与分析已完成，共提取 {summary['analyzed_tweets']} 条推文。"
        )
        progress = 100

    return {
        "handle": blogger.handle,
        "stage": stage,
        "message": message,
        "progress": progress,
        **{key: value for key, value in summary.items() if key != "ingestion_stage"},
    }


def upsert_blogger(db: Session, profile: BloggerProfile) -> Blogger:
    """INSERT ... ON CONFLICT (handle) DO UPDATE; bumps profile_updated_at."""
    payload = {
        "handle": profile.handle,
        "name": profile.name,
        "bio": profile.bio,
        "avatar_url": profile.avatar_url,
        "followers_count": profile.followers_count,
        "market_focus": profile.market_focus,
        "twitter_user_id": profile.twitter_user_id,
        "location": profile.location,
        "tweets_count": profile.tweets_count,
        "following_count": profile.following_count,
        "favorites_count": profile.favorites_count,
        "joined_at": profile.joined_at,
        "verified": profile.verified,
        "protected": profile.protected,
        "profile_url": profile.profile_url,
        "profile_updated_at": datetime.now(timezone.utc),
    }
    stmt = pg_insert(Blogger).values(**payload)
    update_cols = {
        "name": stmt.excluded.name,
        "bio": stmt.excluded.bio,
        "avatar_url": stmt.excluded.avatar_url,
        "followers_count": stmt.excluded.followers_count,
        "market_focus": stmt.excluded.market_focus,
        "twitter_user_id": stmt.excluded.twitter_user_id,
        "location": stmt.excluded.location,
        "tweets_count": stmt.excluded.tweets_count,
        "following_count": stmt.excluded.following_count,
        "favorites_count": stmt.excluded.favorites_count,
        "joined_at": stmt.excluded.joined_at,
        "verified": stmt.excluded.verified,
        "protected": stmt.excluded.protected,
        "profile_url": stmt.excluded.profile_url,
        "profile_updated_at": stmt.excluded.profile_updated_at,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["handle"], set_=update_cols
    )
    db.execute(stmt)
    db.flush()
    return db.execute(
        select(Blogger).where(Blogger.handle == profile.handle)
    ).scalar_one()


def ensure_blogger(db: Session, handle: str, name: str) -> None:
    """Lightweight upsert used during tweet import when no full profile is given."""
    stmt = pg_insert(Blogger).values(handle=handle, name=name)
    stmt = stmt.on_conflict_do_nothing(index_elements=["handle"])
    db.execute(stmt)


def _stats_subquery():
    """Per-blogger aggregate over predictions."""
    verified_filter = Prediction.verdict.in_(SCORED_VERDICTS)
    return (
        select(
            Prediction.blogger_handle.label("handle"),
            func.count()
            .filter(verified_filter)
            .label("verified_count"),
            func.coalesce(
                func.sum(Prediction.score).filter(verified_filter), 0.0
            ).label("correct_sum"),
            func.count()
            .filter(Prediction.verdict.is_(None))
            .label("pending_count"),
        )
        .group_by(Prediction.blogger_handle)
        .subquery()
    )


def list_bloggers_with_stats(db: Session, sort: str = "credibility") -> list[dict]:
    stats = _stats_subquery()
    query = (
        select(
            Blogger,
            func.coalesce(stats.c.verified_count, 0).label("verified_count"),
            func.coalesce(stats.c.correct_sum, 0.0).label("correct_sum"),
            func.coalesce(stats.c.pending_count, 0).label("pending_count"),
        )
        .outerjoin(stats, stats.c.handle == Blogger.handle)
    )
    rows = db.execute(query).all()

    processing_counts = get_blogger_processing_counts(
        db, [blogger.handle for blogger, *_ in rows]
    )
    items = []
    for blogger, verified, correct_sum, pending in rows:
        score = score_profile(float(correct_sum), int(verified))
        hit_rate = float(correct_sum) / verified if verified else None
        items.append({
            "id": str(blogger.id),
            "handle": blogger.handle,
            "name": blogger.name,
            "bio": blogger.bio,
            "avatar_url": blogger.avatar_url,
            "followers_count": blogger.followers_count,
            "market_focus": blogger.market_focus,
            **score,
            "verified_count": int(verified),
            "pending_count": int(pending),
            "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
            "verified": bool(blogger.verified),
            "location": blogger.location,
            **blogger_ingestion_summary(
                blogger, processing_counts.get(blogger.handle.lower())
            ),
        })

    if sort == "verified_count":
        items.sort(key=lambda x: x["verified_count"], reverse=True)
    elif sort == "followers":
        items.sort(key=lambda x: x["followers_count"], reverse=True)
    elif sort == "pending_count":
        items.sort(key=lambda x: x["pending_count"], reverse=True)
    else:
        items.sort(key=lambda x: x["credibility_score"], reverse=True)
    return items


def get_blogger_detail(db: Session, handle: str) -> dict | None:
    blogger = db.execute(
        select(Blogger).where(Blogger.handle == handle)
    ).scalar_one_or_none()
    if blogger is None:
        return None

    verified_filter = and_(
        Prediction.blogger_handle == handle,
        Prediction.verdict.in_(SCORED_VERDICTS),
    )
    pending_filter = and_(
        Prediction.blogger_handle == handle,
        Prediction.verdict.is_(None),
    )

    verified_count = db.execute(
        select(func.count()).where(verified_filter)
    ).scalar() or 0
    correct_sum = db.execute(
        select(func.coalesce(func.sum(Prediction.score), 0.0)).where(verified_filter)
    ).scalar() or 0.0
    pending_count = db.execute(
        select(func.count()).where(pending_filter)
    ).scalar() or 0

    by_sentiment_rows = db.execute(
        select(
            Prediction.sentiment,
            func.count().label("n"),
            func.coalesce(func.sum(Prediction.score), 0.0).label("s"),
        )
        .where(verified_filter)
        .group_by(Prediction.sentiment)
    ).all()
    hit_rate_by_sentiment: dict[str, float | None] = {
        "bullish": None,
        "bearish": None,
        "neutral": None,
    }
    for sentiment, n, s in by_sentiment_rows:
        hit_rate_by_sentiment[sentiment] = round(float(s) / n, 4) if n else None

    top_tickers_rows = db.execute(
        select(
            Prediction.ticker,
            func.count().label("verified"),
            func.coalesce(func.sum(Prediction.score), 0.0).label("correct_sum"),
        )
        .where(verified_filter)
        .group_by(Prediction.ticker)
        .having(func.count() >= 1)
        .order_by(
            (func.sum(Prediction.score) / func.count()).desc(),
            func.count().desc(),
        )
        .limit(5)
    ).all()
    top_tickers = [
        {
            "ticker": tk,
            "verified": int(v),
            "hit_rate": round(float(c) / int(v), 4) if v else 0.0,
        }
        for tk, v, c in top_tickers_rows
    ]

    recent = db.execute(
        select(Prediction, Tweet)
        .join(Tweet, Prediction.tweet_id == Tweet.id)
        .where(verified_filter)
        .order_by(Prediction.verified_at.desc())
        .limit(10)
    ).all()
    recent_verified = [_serialize_prediction(p, t) for p, t in recent]

    score = score_profile(float(correct_sum), int(verified_count))
    hit_rate_overall = (
        round(float(correct_sum) / int(verified_count), 4)
        if verified_count
        else None
    )

    return {
        "id": str(blogger.id),
        "handle": blogger.handle,
        "name": blogger.name,
        "bio": blogger.bio,
        "avatar_url": blogger.avatar_url,
        "followers_count": blogger.followers_count,
        "market_focus": blogger.market_focus,
        "profile_updated_at": blogger.profile_updated_at,
        **score,
        "verified_count": int(verified_count),
        "pending_count": int(pending_count),
        "hit_rate_overall": hit_rate_overall,
        "hit_rate_by_sentiment": hit_rate_by_sentiment,
        "top_tickers": top_tickers,
        "recent_verified": recent_verified,
        "twitter_user_id": blogger.twitter_user_id,
        "location": blogger.location,
        "tweets_count": int(blogger.tweets_count or 0),
        "following_count": int(blogger.following_count or 0),
        "favorites_count": int(blogger.favorites_count or 0),
        "joined_at": blogger.joined_at,
        "verified": bool(blogger.verified),
        "protected": bool(blogger.protected),
        "profile_url": blogger.profile_url,
        "fetch_enabled": bool(blogger.fetch_enabled),
        "last_fetched_at": blogger.last_fetched_at,
    }


def list_predictions_by_blogger(
    db: Session,
    handle: str,
    status: str = "all",
    ticker: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    base = select(Prediction, Tweet).join(Tweet, Prediction.tweet_id == Tweet.id).where(
        Prediction.blogger_handle == handle
    )
    if status == "pending":
        base = base.where(Prediction.verdict.is_(None))
    elif status == "verified":
        base = base.where(Prediction.verdict.in_(SCORED_VERDICTS))
    if ticker:
        base = base.where(Prediction.ticker == ticker)

    count_q = (
        select(func.count())
        .select_from(Prediction)
        .where(Prediction.blogger_handle == handle)
    )
    if status == "pending":
        count_q = count_q.where(Prediction.verdict.is_(None))
    elif status == "verified":
        count_q = count_q.where(Prediction.verdict.in_(SCORED_VERDICTS))
    if ticker:
        count_q = count_q.where(Prediction.ticker == ticker)

    total = db.execute(count_q).scalar() or 0

    rows = db.execute(
        base.order_by(Prediction.published_at.desc()).limit(limit).offset(offset)
    ).all()
    prediction_ids = [prediction.id for prediction, _tweet in rows]
    latest_verifications: dict = {}
    if prediction_ids:
        verifications = db.execute(
            select(PredictionMarketVerification)
            .where(PredictionMarketVerification.prediction_id.in_(prediction_ids))
            .order_by(
                PredictionMarketVerification.prediction_id,
                PredictionMarketVerification.created_at.desc(),
            )
        ).scalars().all()
        for verification in verifications:
            latest_verifications.setdefault(verification.prediction_id, verification)

    return {
        "items": [
            _serialize_prediction(p, t, latest_verifications.get(p.id))
            for p, t in rows
        ],
        "total": int(total),
    }


def _serialize_market_verification(
    verification: PredictionMarketVerification | None,
) -> dict | None:
    if verification is None:
        return None
    evidence = verification.evidence or {}
    return {
        "id": str(verification.id),
        "status": verification.status,
        "provider": verification.provider,
        "provider_symbol": verification.provider_symbol,
        "market": verification.market,
        "start_observed_at": verification.start_observed_at,
        "start_price": verification.start_price,
        "end_observed_at": verification.end_observed_at,
        "end_price": verification.end_price,
        "raw_return": verification.raw_return,
        "directional_return": verification.directional_return,
        "threshold": verification.threshold,
        "proposed_verdict": verification.proposed_verdict,
        "proposed_score": verification.proposed_score,
        "rule_version": verification.rule_version,
        "reason": evidence.get("reason") or verification.error_message,
        "review_type": evidence.get("review_type"),
        "identity": evidence.get("identity"),
        "identity_reason": evidence.get("identity_reason"),
        "price_proxy": evidence.get("price_proxy"),
        "correction": evidence.get("correction"),
        "applied": verification.applied,
        "created_at": verification.created_at.isoformat(),
    }


def _serialize_prediction(
    p: Prediction,
    t: Tweet,
    verification: PredictionMarketVerification | None = None,
) -> dict:
    return {
        "id": str(p.id),
        "blogger_handle": p.blogger_handle,
        "ticker": p.ticker,
        "sentiment": p.sentiment,
        "investment_horizon": p.investment_horizon,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "verifiable_at": p.verifiable_at.isoformat() if p.verifiable_at else None,
        "verdict": p.verdict,
        "score": p.score,
        "verified_at": p.verified_at.isoformat() if p.verified_at else None,
        "verified_by": p.verified_by,
        "note": p.note,
        "instrument_snapshot": p.instrument_snapshot,
        "creation_rule_version": p.creation_rule_version,
        "creation_evidence": p.creation_evidence,
        "market_verification": _serialize_market_verification(verification),
        "tweet": {
            "id": str(t.id),
            "content": t.content,
            "published_at": t.published_at.isoformat() if t.published_at else None,
        },
    }
