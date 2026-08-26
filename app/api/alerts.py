from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.deps import get_db
from app.models.user import User
from app.schemas.alert import AlertItem, AlertListResponse, AlertUpdateRequest
from app.services.alert_service import list_alerts, mark_all_read, update_alert


router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
def get_alerts(
    status: str = Query("unread", pattern="^(unread|read|dismissed|all)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_alerts(db, user.id, status=status, limit=limit, offset=offset)


@router.patch("/{alert_id}", response_model=AlertItem)
def patch_alert(
    alert_id: UUID,
    body: AlertUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.action not in {"read", "dismiss"}:
        raise HTTPException(status_code=422, detail="action must be read or dismiss")
    alert = update_alert(db, user.id, alert_id, action=body.action)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/read-all")
def read_all_alerts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"updated": mark_all_read(db, user.id)}
