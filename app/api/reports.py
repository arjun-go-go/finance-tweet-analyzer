"""Report API endpoints."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.models.user import User
from app.schemas.report import (
    ReportGenerateRequest,
    ReportListItem,
    ReportListResponse,
    ReportResponse,
)
from app.services import report_service
from app.services.report_streaming import channel_for

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _check_rag_enabled():
    if not settings.feature_rag_enabled:
        raise HTTPException(status_code=404, detail="RAG feature is not enabled")


@router.post("/generate", response_model=ReportResponse, status_code=202)
def generate_report(
    body: ReportGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a pending report row and dispatch async generation to Celery.

    Returns immediately with status='generating'. Client should subscribe to
    GET /api/reports/{id}/stream for incremental SSE updates.
    """
    _check_rag_enabled()
    report = report_service.create_report_record(
        db, user.id, body.ticker, trigger_type="manual"
    )

    import app.celery_app  # noqa: F401 — bind shared_task to configured Redis broker
    from app.scheduler.tasks import report_streaming_task
    report_streaming_task.delay(str(report.id), str(user.id), body.ticker)

    return ReportResponse.model_validate(report)


@router.get("/", response_model=ReportListResponse)
def list_reports(
    ticker: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    items, total = report_service.list_reports(db, user.id, ticker=ticker, page=page, size=size)
    return ReportListResponse(
        items=[ReportListItem.model_validate(r) for r in items],
        total=total,
    )


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    report = report_service.get_report(db, user.id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportResponse.model_validate(report)


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    if not report_service.delete_report(db, user.id, report_id):
        raise HTTPException(status_code=404, detail="Report not found")


# ============================================================
# SSE Streaming
# ============================================================

@router.get("/{report_id}/stream")
async def stream_report(
    report_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Subscribe to a report's generation progress via SSE.

    Flow:
      1. Verify report belongs to user.
      2. Emit a 'snapshot' event with current DB state (enables resume).
      3. If report already terminal (done/failed), emit 'done' and close.
      4. Otherwise subscribe to Redis pub/sub channel and forward messages.
      5. Heartbeat every report_stream_heartbeat_sec to keep the connection alive.
    """
    _check_rag_enabled()
    report = report_service.get_report(db, user.id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    snapshot = {
        "id": str(report.id),
        "ticker": report.ticker,
        "status": report.status,
        "sections": report.sections or {},
        "citations": report.citations or [],
        "summary": report.summary,
        "consensus": report.consensus,
        "latency_ms": report.latency_ms,
        "error_detail": report.error_detail,
    }
    terminal = report.status in ("done", "failed")
    channel = channel_for(report_id)

    async def event_generator():
        # 1. Snapshot for hydration / reconnect
        yield {
            "event": "snapshot",
            "data": json.dumps(snapshot, ensure_ascii=False, default=str),
        }

        if terminal:
            yield {"event": "done", "data": "{}"}
            return

        # 2. Subscribe to Redis pub/sub
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(channel)
            heartbeat = settings.report_stream_heartbeat_sec
            max_wait = settings.report_stream_max_wait_sec
            elapsed = 0.0

            while elapsed < max_wait:
                if await request.is_disconnected():
                    logger.info(f"SSE client disconnected for report {report_id}")
                    break

                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=heartbeat
                )
                if msg is None:
                    yield {"event": "ping", "data": "{}"}
                    elapsed += heartbeat
                    continue

                elapsed = 0.0
                try:
                    payload = json.loads(msg["data"])
                except Exception:
                    continue

                event_name = payload.get("event", "message")
                yield {
                    "event": event_name,
                    "data": json.dumps(payload.get("data", {}), ensure_ascii=False),
                }
                if event_name in ("done", "error"):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"SSE stream error for report {report_id}: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)[:200]}, ensure_ascii=False),
            }
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                await redis_client.close()
            except Exception:
                pass

    return EventSourceResponse(event_generator())
