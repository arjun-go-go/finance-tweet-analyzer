"""Service layer for ticker tracking subscriptions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.tracked_ticker import TrackedTicker
from app.models.intelligence_event import IntelligenceEvent, IntelligenceTopic
from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.models.user_blogger_follow import UserBloggerFollow
from app.services.instrument_resolver import (
    is_downstream_verified_ticker,
    resolve_analysis_tickers,
)


class TrackingQuotaExceeded(Exception):
    pass


class DuplicateSubscription(Exception):
    def __init__(self, existing: TrackedTicker):
        self.existing = existing


class InvalidTrackingInstrument(Exception):
    pass


def validate_tracking_instrument(ticker: str) -> dict:
    normalized = ticker.strip().lstrip("$").upper()
    analyses = [{"tickers": [{
        "symbol": normalized,
        "original_name": normalized,
        "asset_type": "unknown",
        "market_hint": "unknown",
    }]}]
    instrument = resolve_analysis_tickers(analyses)[0]["tickers"][0]
    accepted = is_downstream_verified_ticker(instrument)
    return {
        "accepted": accepted,
        "reason": (
            "已通过公开证券、商品或交易所数据源校验"
            if accepted else "无法通过公开数据源确认该标的，请检查代码"
        ),
        "instrument": instrument,
    }


def subscribe(db: Session, user_id: UUID, ticker: str) -> TrackedTicker:
    validation = validate_tracking_instrument(ticker)
    if not validation["accepted"]:
        raise InvalidTrackingInstrument(validation["reason"])
    instrument = validation["instrument"]
    ticker = str(instrument["symbol"]).upper()
    count = db.execute(
        select(func.count())
        .where(TrackedTicker.user_id == user_id, TrackedTicker.status != "deleted")
    ).scalar_one()
    if count >= settings.max_tracked_tickers_per_user:
        raise TrackingQuotaExceeded(
            f"Maximum {settings.max_tracked_tickers_per_user} subscriptions allowed"
        )

    existing = db.execute(
        select(TrackedTicker).where(
            TrackedTicker.user_id == user_id,
            TrackedTicker.ticker == ticker.upper(),
            TrackedTicker.status != "deleted",
        )
    ).scalar_one_or_none()
    if existing:
        raise DuplicateSubscription(existing)

    record = TrackedTicker(
        user_id=user_id,
        ticker=ticker.upper(),
        config={
            "instrument": instrument,
            "alerts": {
                "risk": True,
                "direction_reversal": True,
                "new_prediction": True,
            },
        },
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_subscriptions(db: Session, user_id: UUID) -> list[TrackedTicker]:
    return list(
        db.execute(
            select(TrackedTicker)
            .where(TrackedTicker.user_id == user_id, TrackedTicker.status != "deleted")
            .order_by(TrackedTicker.created_at.desc())
        ).scalars().all()
    )


def update_subscription(
    db: Session, user_id: UUID, tracking_id: UUID, *, status: str | None = None
) -> TrackedTicker | None:
    record = db.execute(
        select(TrackedTicker).where(
            TrackedTicker.id == tracking_id,
            TrackedTicker.user_id == user_id,
            TrackedTicker.status != "deleted",
        )
    ).scalar_one_or_none()
    if not record:
        return None

    if status:
        record.status = status

    db.commit()
    db.refresh(record)
    return record


def unsubscribe(db: Session, user_id: UUID, tracking_id: UUID) -> bool:
    record = db.execute(
        select(TrackedTicker).where(
            TrackedTicker.id == tracking_id,
            TrackedTicker.user_id == user_id,
            TrackedTicker.status != "deleted",
        )
    ).scalar_one_or_none()
    if not record:
        return False
    record.status = "deleted"
    db.commit()
    return True


def serialize_tracking(record: TrackedTicker, monitor: dict | None = None) -> dict:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "ticker": record.ticker,
        "status": record.status,
        "config": record.config or {},
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "instrument": (record.config or {}).get("instrument"),
        "monitor": monitor or {},
    }


def tracking_monitoring(db: Session, records: list[TrackedTicker]) -> tuple[dict[UUID, dict], dict]:
    """Aggregate current intelligence and predictions for Watchlist cards."""
    if not records:
        return {}, {"intelligence_24h": 0, "attention": 0}
    now = datetime.now(timezone.utc)
    tickers = {record.ticker for record in records}
    user_id = records[0].user_id
    followed_handles = list(
        db.execute(
            select(Blogger.handle)
            .join(UserBloggerFollow, UserBloggerFollow.blogger_id == Blogger.id)
            .where(UserBloggerFollow.user_id == user_id)
        ).scalars()
    )
    events = []
    if followed_handles:
        events = list(
            db.execute(
                select(IntelligenceEvent)
                .join(
                    AnalysisResult,
                    AnalysisResult.id == IntelligenceEvent.analysis_result_id,
                )
                .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
                .where(
                    IntelligenceEvent.status == "active",
                    IntelligenceEvent.primary_ticker.in_(tickers),
                    IntelligenceEvent.published_at >= now - timedelta(days=7),
                    func.lower(Tweet.author_handle).in_(
                        [handle.lower() for handle in followed_handles]
                    ),
                )
            ).scalars()
        )
    topic_ids = {event.topic_id for event in events if event.topic_id}
    topics = list(
        db.execute(
            select(IntelligenceTopic).where(IntelligenceTopic.id.in_(topic_ids))
        ).scalars()
    ) if topic_ids else []
    predictions = []
    if followed_handles:
        predictions = list(
            db.execute(
                select(Prediction).where(
                    Prediction.ticker.in_(tickers),
                    func.lower(Prediction.blogger_handle).in_(
                        [handle.lower() for handle in followed_handles]
                    ),
                )
            ).scalars()
        )
    output: dict[UUID, dict] = {}
    total_24h = 0
    attention = 0
    for record in records:
        ticker_topics = [topic for topic in topics if topic.primary_ticker == record.ticker]
        ticker_events = [event for event in events if event.primary_ticker == record.ticker]
        recent = [event for event in ticker_events if event.published_at >= now - timedelta(hours=24)]
        previous = [event for event in ticker_events if now - timedelta(hours=48) <= event.published_at < now - timedelta(hours=24)]
        bullish = sum(1 for event in recent if event.direction == "bullish")
        bearish = sum(1 for event in recent if event.direction == "bearish")
        directional_count = bullish + bearish
        if directional_count == 0:
            direction = "neutral"
        elif bullish > bearish:
            direction = "bullish"
        elif bearish > bullish:
            direction = "bearish"
        else:
            direction = "mixed"
        current_score = bullish - bearish
        previous_score = sum(1 if event.direction == "bullish" else -1 if event.direction == "bearish" else 0 for event in previous)
        trend = "up" if current_score > previous_score else "down" if current_score < previous_score else "flat"
        ticker_predictions = [prediction for prediction in predictions if prediction.ticker == record.ticker]
        active_predictions = [prediction for prediction in ticker_predictions if prediction.verdict is None]
        new_predictions = [prediction for prediction in ticker_predictions if prediction.created_at >= now - timedelta(hours=24)]
        latest_topic = max(ticker_topics, key=lambda value: value.last_seen_at, default=None)
        latest_event = max(ticker_events, key=lambda value: value.published_at, default=None)
        latest_prediction = max(ticker_predictions, key=lambda value: value.published_at, default=None)
        alerts: list[dict] = []
        recent_topic_ids = {event.topic_id for event in recent if event.topic_id}
        if any(topic.lifecycle == "reversed" and topic.id in recent_topic_ids for topic in ticker_topics):
            alerts.append({"type": "direction_reversal", "level": "high", "message": "观点方向出现反转"})
        high_risks = sum(1 for event in recent if event.risk_level in {"high", "critical"})
        if high_risks:
            alerts.append({"type": "risk", "level": "high", "message": f"出现 {high_risks} 条高风险情报"})
        if new_predictions:
            alerts.append({"type": "new_prediction", "level": "info", "message": f"新增 {len(new_predictions)} 条方向性预测"})
        total_24h += len(recent)
        attention += 1 if alerts else 0
        output[record.id] = {
            "intelligence_24h": len(recent),
            "direction": direction,
            "direction_trend": trend,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "directional_claim_count": directional_count,
            "direction_basis": "followed_author_claims_24h",
            "has_disagreement": bullish > 0 and bearish > 0,
            "active_predictions": len(active_predictions),
            "latest_prediction_sentiment": latest_prediction.sentiment if latest_prediction else None,
            "risk_count": high_risks,
            "latest_title": latest_topic.title if latest_topic else latest_event.title if latest_event else None,
            "latest_seen_at": latest_event.published_at if latest_event else None,
            "alerts": alerts,
        }
    return output, {"intelligence_24h": total_24h, "attention": attention}
