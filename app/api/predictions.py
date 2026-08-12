from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_admin
from app.models.user import User
from app.schemas.prediction import (
    CorrectInstrumentRequest,
    ExcludePredictionRequest,
    ValidateInstrumentRequest,
    VerifyRequest,
)
from app.services.prediction_service import (
    correct_prediction_instrument,
    exclude_prediction,
    list_prediction_review_queue,
    validate_prediction_instrument,
    verify_prediction,
)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.post("/instruments/validate")
def validate_instrument_endpoint(
    body: ValidateInstrumentRequest,
    _admin: User = Depends(get_current_admin),
):
    return validate_prediction_instrument(body)


@router.get("/review-queue")
def review_queue_endpoint(
    status: str = Query(
        "all", pattern="^(all|manual_review|market_data_unavailable)$"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return list_prediction_review_queue(
        db, status=status, limit=limit, offset=offset
    )


@router.post("/{prediction_id}/verify")
def verify_endpoint(
    prediction_id: str,
    body: VerifyRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return verify_prediction(db, prediction_id, body)


@router.post("/{prediction_id}/exclude")
def exclude_endpoint(
    prediction_id: str,
    body: ExcludePredictionRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return exclude_prediction(db, prediction_id, body)


@router.post("/{prediction_id}/correct-instrument")
def correct_instrument_endpoint(
    prediction_id: str,
    body: CorrectInstrumentRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return correct_prediction_instrument(
        db, prediction_id, body, corrected_by=_admin.id
    )
