from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.deps import get_db
from app.models.user import User
from app.schemas.intelligence import IntelligenceFeedResponse
from app.services.intelligence_service import build_user_intelligence_feed


router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/feed", response_model=IntelligenceFeedResponse)
def get_intelligence_feed(
    limit: int = Query(20, ge=1, le=50),
    window: Literal["24h", "3d", "7d"] = Query("24h"),
    kind: Literal["all", "risk", "opinion"] = Query("all"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntelligenceFeedResponse:
    items, context = build_user_intelligence_feed(
        db,
        current_user.id,
        limit=limit,
        window=window,
        kind=kind,
    )
    return IntelligenceFeedResponse(
        items=items,
        total=context["candidate_total"],
        context=context,
    )
