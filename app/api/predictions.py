from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.prediction import VerifyRequest
from app.services.prediction_service import verify_prediction

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.post("/{prediction_id}/verify")
def verify_endpoint(
    prediction_id: str,
    body: VerifyRequest,
    db: Session = Depends(get_db),
):
    return verify_prediction(db, prediction_id, body)
