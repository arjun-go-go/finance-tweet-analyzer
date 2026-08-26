"""Service layer for ticker tracking subscriptions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tracked_ticker import TrackedTicker
from app.models.intelligence_event import IntelligenceTopic
from app.models.prediction import Prediction
from app.models.report import Report
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


def _compute_next_run(frequency: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if frequency == "daily":
        tomorrow = (now + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0)
        return tomorrow
    elif frequency == "weekly":
        days_until_monday = (7 - now.weekday()) % 7 or 7
        next_monday = (now + timedelta(days=days_until_monday)).replace(
            hour=1, minute=0, second=0, microsecond=0
        )
        return next_monday
    return None


def subscribe(db: Session, user_id: UUID, ticker: str, frequency: str) -> TrackedTicker:
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
        frequency=frequency,
        next_run_at=_compute_next_run(frequency),
        config={
            "instrument": instrument,
            "report_status": "idle",
            "alerts": {
                "risk": True,
                "direction_reversal": True,
                "new_prediction": True,
                "report_failure": True,
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
    db: Session, user_id: UUID, tracking_id: UUID, *, frequency: str | None = None, status: str | None = None
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

    if frequency:
        record.frequency = frequency
        record.next_run_at = _compute_next_run(frequency)
    if status:
        record.status = status
        if status == "paused":
            record.next_run_at = None
        elif status == "active":
            record.next_run_at = _compute_next_run(record.frequency)

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


def get_due_subscriptions(db: Session) -> list[TrackedTicker]:
    now = datetime.now(timezone.utc)
    return list(
        db.execute(
            select(TrackedTicker).where(
                TrackedTicker.status == "active",
                TrackedTicker.next_run_at <= now,
                or_(
                    TrackedTicker.config["report_status"].astext.is_(None),
                    ~TrackedTicker.config["report_status"].astext.in_(("queued", "generating")),
                ),
            )
        ).scalars().all()
    )


def advance_next_run(db: Session, tracking_id: UUID) -> None:
    record = db.get(TrackedTicker, tracking_id)
    if not record:
        return
    record.last_report_at = datetime.now(timezone.utc)
    record.next_run_at = _compute_next_run(record.frequency)
    db.commit()


def _report_query(record: TrackedTicker, *, manual: bool) -> tuple[str, str]:
    if manual:
        return (
            f"{record.ticker} 当前博主观点摘要",
            f"生成 {record.ticker} 当前 Twitter 博主观点摘要，重点说明最新观点、重要变化、方向性预测和主要风险。",
        )
    if record.frequency == "weekly":
        return (
            f"{record.ticker} 每周博主观点摘要",
            f"生成 {record.ticker} 过去7天 Twitter 博主观点摘要，重点比较本周观点变化、新增证据、预测验证结果和风险变化。",
        )
    return (
        f"{record.ticker} 每日博主观点摘要",
        f"生成 {record.ticker} 过去24小时 Twitter 博主观点摘要，重点说明新增情报、观点方向变化、新预测和风险信号。",
    )


def recover_stale_tracking_reports(db: Session, *, stale_minutes: int = 30) -> int:
    """Move abandoned generating reports back to a retryable tracking state."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    stale = list(db.execute(
        select(Report).where(
            Report.status == "generating",
            Report.tracked_ticker_id.is_not(None),
            Report.created_at < cutoff,
        )
    ).scalars())
    now = datetime.now(timezone.utc)
    for report in stale:
        report.status = "failed"
        report.error_detail = "报告任务执行中断，已自动恢复为可重试状态"
        record = db.get(TrackedTicker, report.tracked_ticker_id)
        if record:
            config = dict(record.config or {})
            config.update({
                "report_status": "failed",
                "last_report_error": report.error_detail,
                "report_completed_at": now.isoformat(),
            })
            record.config = config
            if record.frequency != "manual":
                record.next_run_at = now
    db.commit()
    return len(stale)


def queue_tracking_report(
    db: Session,
    record: TrackedTicker,
    *,
    manual: bool,
) -> Report:
    """Create one asynchronous report per tracking item at a time."""
    locked = db.execute(
        select(TrackedTicker)
        .where(TrackedTicker.id == record.id)
        .with_for_update()
    ).scalar_one()
    record = locked
    existing = db.execute(
        select(Report)
        .where(
            Report.tracked_ticker_id == record.id,
            Report.status == "generating",
        )
        .order_by(Report.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing:
        return existing

    from app.services.report_service import create_report_record

    title, query = _report_query(record, manual=manual)
    report = create_report_record(
        db,
        record.user_id,
        record.ticker,
        trigger_type="manual" if manual else "scheduled",
        tracked_ticker_id=record.id,
        title=title,
        query=query,
    )
    config = dict(record.config or {})
    config.update({
        "report_status": "queued",
        "current_report_id": str(report.id),
        "report_queued_at": datetime.now(timezone.utc).isoformat(),
        "last_report_error": None,
    })
    record.config = config
    if not manual:
        record.next_run_at = None
    db.commit()
    return report


def finish_tracking_report(db: Session, report_id: UUID, *, success: bool, error: str | None = None) -> None:
    report = db.get(Report, report_id)
    if not report or not report.tracked_ticker_id:
        return
    record = db.get(TrackedTicker, report.tracked_ticker_id)
    if not record:
        return
    now = datetime.now(timezone.utc)
    config = dict(record.config or {})
    config.update({
        "report_status": "done" if success else "failed",
        "current_report_id": str(report.id),
        "report_completed_at": now.isoformat(),
        "last_report_error": None if success else (error or "报告生成失败")[:500],
    })
    record.config = config
    if success:
        record.last_report_at = now
        record.next_run_at = _compute_next_run(record.frequency)
    elif record.frequency != "manual":
        record.next_run_at = now + timedelta(minutes=30)
    db.commit()


def mark_tracking_report_generating(db: Session, report_id: UUID) -> None:
    report = db.get(Report, report_id)
    if not report or not report.tracked_ticker_id:
        return
    record = db.get(TrackedTicker, report.tracked_ticker_id)
    if not record:
        return
    config = dict(record.config or {})
    config["report_status"] = "generating"
    config["report_started_at"] = datetime.now(timezone.utc).isoformat()
    record.config = config
    db.commit()


def serialize_tracking(record: TrackedTicker, monitor: dict | None = None) -> dict:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "ticker": record.ticker,
        "frequency": record.frequency,
        "last_report_at": record.last_report_at,
        "next_run_at": record.next_run_at,
        "status": record.status,
        "config": record.config or {},
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "instrument": (record.config or {}).get("instrument"),
        "monitor": monitor or {},
    }


def tracking_monitoring(db: Session, records: list[TrackedTicker]) -> tuple[dict[UUID, dict], dict]:
    """Aggregate current intelligence, predictions and report state for Watchlist cards."""
    if not records:
        return {}, {"intelligence_24h": 0, "attention": 0, "failed_reports": 0}
    now = datetime.now(timezone.utc)
    tickers = {record.ticker for record in records}
    topics = list(db.execute(
        select(IntelligenceTopic).where(
            IntelligenceTopic.status == "active",
            IntelligenceTopic.primary_ticker.in_(tickers),
            IntelligenceTopic.last_seen_at >= now - timedelta(days=7),
        )
    ).scalars())
    predictions = list(db.execute(
        select(Prediction).where(Prediction.ticker.in_(tickers))
    ).scalars())
    reports = list(db.execute(
        select(Report)
        .where(Report.tracked_ticker_id.in_([record.id for record in records]))
        .order_by(Report.created_at.desc())
    ).scalars())
    latest_report: dict[UUID, Report] = {}
    for report in reports:
        latest_report.setdefault(report.tracked_ticker_id, report)

    output: dict[UUID, dict] = {}
    total_24h = 0
    attention = 0
    failed_reports = 0
    for record in records:
        ticker_topics = [topic for topic in topics if topic.primary_ticker == record.ticker]
        recent = [topic for topic in ticker_topics if topic.last_seen_at >= now - timedelta(hours=24)]
        previous = [topic for topic in ticker_topics if now - timedelta(hours=48) <= topic.last_seen_at < now - timedelta(hours=24)]
        bullish = sum(1 for topic in recent if topic.direction == "bullish")
        bearish = sum(1 for topic in recent if topic.direction == "bearish")
        direction = "bullish" if bullish > bearish else "bearish" if bearish > bullish else "mixed" if recent else "neutral"
        current_score = bullish - bearish
        previous_score = sum(1 if topic.direction == "bullish" else -1 if topic.direction == "bearish" else 0 for topic in previous)
        trend = "up" if current_score > previous_score else "down" if current_score < previous_score else "flat"
        ticker_predictions = [prediction for prediction in predictions if prediction.ticker == record.ticker]
        active_predictions = [prediction for prediction in ticker_predictions if prediction.verdict is None]
        new_predictions = [prediction for prediction in ticker_predictions if prediction.created_at >= now - timedelta(hours=24)]
        latest_topic = max(ticker_topics, key=lambda value: value.last_seen_at, default=None)
        latest_prediction = max(ticker_predictions, key=lambda value: value.published_at, default=None)
        report = latest_report.get(record.id)
        alerts: list[dict] = []
        if any(topic.lifecycle == "reversed" for topic in recent):
            alerts.append({"type": "direction_reversal", "level": "high", "message": "观点方向出现反转"})
        high_risks = sum(1 for topic in recent if topic.risk_level in {"high", "critical"})
        if high_risks:
            alerts.append({"type": "risk", "level": "high", "message": f"出现 {high_risks} 条高风险情报"})
        if new_predictions:
            alerts.append({"type": "new_prediction", "level": "info", "message": f"新增 {len(new_predictions)} 条方向性预测"})
        if report and report.status == "failed":
            alerts.append({"type": "report_failure", "level": "high", "message": "最近一次简报生成失败"})
            failed_reports += 1
        total_24h += len(recent)
        attention += 1 if alerts else 0
        output[record.id] = {
            "intelligence_24h": len(recent),
            "direction": direction,
            "direction_trend": trend,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "active_predictions": len(active_predictions),
            "latest_prediction_sentiment": latest_prediction.sentiment if latest_prediction else None,
            "risk_count": high_risks,
            "latest_title": latest_topic.title if latest_topic else None,
            "latest_seen_at": latest_topic.last_seen_at if latest_topic else None,
            "latest_report": ({
                "id": str(report.id), "status": report.status,
                "created_at": report.created_at, "consensus": report.consensus,
                "error": report.error_detail,
            } if report else None),
            "alerts": alerts,
        }
    return output, {"intelligence_24h": total_24h, "attention": attention, "failed_reports": failed_reports}
