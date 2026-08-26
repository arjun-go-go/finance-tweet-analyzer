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
    TrackingValidateRequest,
)
from app.services import tracking_service

router = APIRouter(prefix="/api/tracking", tags=["tracking"])


def _check_rag_enabled():
    if not settings.feature_rag_enabled:
        raise HTTPException(status_code=404, detail="RAG feature is not enabled")


@router.post("/validate", response_model=dict)
def validate_tracking(
    body: TrackingValidateRequest,
    user: User = Depends(get_current_user),
):
    _check_rag_enabled()
    return tracking_service.validate_tracking_instrument(body.ticker)


@router.post("/", response_model=TrackingResponse, status_code=201)
def subscribe(
    body: TrackingCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    try:
        record = tracking_service.subscribe(db, user.id, body.ticker)
    except tracking_service.TrackingQuotaExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except tracking_service.DuplicateSubscription as e:
        return tracking_service.serialize_tracking(e.existing)
    except tracking_service.InvalidTrackingInstrument as e:
        raise HTTPException(status_code=422, detail=str(e))
    return tracking_service.serialize_tracking(record)


@router.get("/", response_model=TrackingListResponse)
def list_subscriptions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    items = tracking_service.list_subscriptions(db, user.id)
    monitoring, summary = tracking_service.tracking_monitoring(db, items)
    return TrackingListResponse(
        items=[tracking_service.serialize_tracking(i, monitoring.get(i.id)) for i in items],
        total=len(items),
        summary=summary,
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
        db, user.id, tracking_id, status=body.status
    )
    if not record:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return tracking_service.serialize_tracking(record)


@router.delete("/{tracking_id}", status_code=204)
def unsubscribe(
    tracking_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_rag_enabled()
    if not tracking_service.unsubscribe(db, user.id, tracking_id):
        raise HTTPException(status_code=404, detail="Subscription not found")
