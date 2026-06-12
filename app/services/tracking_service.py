"""Service layer for ticker tracking subscriptions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tracked_ticker import TrackedTicker


class TrackingQuotaExceeded(Exception):
    pass


class DuplicateSubscription(Exception):
    def __init__(self, existing: TrackedTicker):
        self.existing = existing


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
