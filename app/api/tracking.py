"""Tracking subscription API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import get_db
from app.models.user import User
from app.schemas.tracking import (
    TrackingCreateRequest,
    TrackingListResponse,
    TrackingResponse,
    TrackingUpdateRequest,
)
from app.services import tracking_service

router = APIRouter(prefix="/api/tracking", tags=["tracking"])


def _check_rag_enabled():
    if not settings.feature_rag_enabled:
        raise HTTPException(status_code=404, detail="RAG feature is not enabled")


@router.post("/", response_model=TrackingResponse, status_code=201)
def subscribe(
    body: TrackingCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    try:
        record = tracking_service.subscribe(db, user.id, body.ticker, body.frequency)
    except tracking_service.TrackingQuotaExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except tracking_service.DuplicateSubscription as e:
        return TrackingResponse.model_validate(e.existing)
    return TrackingResponse.model_validate(record)


@router.get("/", response_model=TrackingListResponse)
def list_subscriptions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    items = tracking_service.list_subscriptions(db, user.id)
    return TrackingListResponse(
        items=[TrackingResponse.model_validate(i) for i in items],
        total=len(items),
    )


@router.patch("/{tracking_id}", response_model=TrackingResponse)
def update_subscription(
    tracking_id: UUID,
    body: TrackingUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    record = tracking_service.update_subscription(
        db, user.id, tracking_id, frequency=body.frequency, status=body.status
    )
    if not record:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return TrackingResponse.model_validate(record)


@router.delete("/{tracking_id}", status_code=204)
def unsubscribe(
    tracking_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    if not tracking_service.unsubscribe(db, user.id, tracking_id):
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post("/{tracking_id}/trigger", response_model=dict)
def trigger_report(
    tracking_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Immediately trigger a report for a tracked ticker."""
    _check_rag_enabled()
    from app.models.tracked_ticker import TrackedTicker

    record = db.get(TrackedTicker, tracking_id)
    if not record or record.user_id != user.id or record.status == "deleted":
        raise HTTPException(status_code=404, detail="Subscription not found")

    from app.scheduler.tasks import embed_signal_task  # noqa: F401
    from app.services.report_service import create_and_run_report

    report = create_and_run_report(
        db, user.id, record.ticker, trigger_type="manual", tracked_ticker_id=tracking_id
    )
    return {"report_id": str(report.id), "status": report.status}
