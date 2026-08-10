from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbox_event import OutboxEvent


EVENT_TASKS: dict[str, tuple[str, str]] = {
    "tweet.index_requested": ("app.scheduler.tasks.embed_signal_task", "embed"),
    "analysis.index_requested": ("app.scheduler.tasks.embed_signal_task", "embed"),
    "document.ingest_requested": ("app.scheduler.tasks.ingest_document_task", "ingest"),
    "report.generate_requested": ("app.scheduler.tasks.report_streaming_task", "report"),
    "analysis.job_requested": ("app.scheduler.tasks.user_analysis_job_task", "analysis"),
    "blogger.analysis_requested": ("app.scheduler.tasks.manual_analysis_task", "analysis"),
}


def enqueue_outbox_event(db: Session, event_type: str, payload: dict) -> OutboxEvent:
    if event_type not in EVENT_TASKS:
        raise ValueError(f"Unsupported outbox event type: {event_type}")
    event = OutboxEvent(event_type=event_type, payload=payload)
    db.add(event)
    db.flush()
    return event


def _task_message(event: OutboxEvent) -> tuple[str, str, list, dict, str]:
    task_name, queue = EVENT_TASKS[event.event_type]
    payload = event.payload or {}

    if event.event_type == "tweet.index_requested":
        args = ["tweet", payload["tweet_id"]]
    elif event.event_type == "analysis.index_requested":
        args = ["analysis", payload["analysis_result_id"]]
    elif event.event_type == "document.ingest_requested":
        args = [payload["document_id"]]
    elif event.event_type == "report.generate_requested":
        args = [payload["report_id"], payload["user_id"], payload["ticker"]]
    elif event.event_type == "analysis.job_requested":
        args = [payload["job_id"]]
    elif event.event_type == "blogger.analysis_requested":
        args = [payload["blogger_handles"]]
    else:
        raise ValueError(f"Unsupported outbox event type: {event.event_type}")

    return task_name, queue, args, {}, str(payload.get("task_id") or event.id)


def dispatch_pending_outbox_events(
    db: Session,
    *,
    send_task: Callable[..., object],
    batch_size: int | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    rows = list(
        db.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_size or settings.outbox_dispatch_batch_size)
            .with_for_update(skip_locked=True)
        ).scalars().all()
    )
    stats = {"selected": len(rows), "dispatched": 0, "failed": 0}

    for event in rows:
        try:
            task_name, queue, args, kwargs, task_id = _task_message(event)
            send_task(task_name, args=args, kwargs=kwargs, task_id=task_id, queue=queue)
            event.status = "dispatched"
            event.dispatched_at = now
            event.last_error = None
            event.attempts += 1
            stats["dispatched"] += 1
        except Exception as exc:
            event.attempts += 1
            event.last_error = str(exc)[:1000]
            delay = min(
                settings.outbox_retry_max_seconds,
                settings.outbox_retry_base_seconds * (2 ** max(event.attempts - 1, 0)),
            )
            event.available_at = now + timedelta(seconds=delay)
            stats["failed"] += 1

    db.commit()
    return stats
