from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.deps import get_db
from app.models.user import User
from app.schemas.intelligence import (
    IntelligenceCorrectionRequest,
    IntelligenceCorrectionResponse,
    IntelligenceDetailResponse,
    IntelligenceDigestResponse,
    IntelligenceFeedResponse,
)
from app.services.intelligence_service import (
    build_user_daily_digest,
    build_user_intelligence_detail,
    build_user_intelligence_feed,
    submit_intelligence_correction,
)


router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/digest", response_model=IntelligenceDigestResponse)
def get_daily_digest(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntelligenceDigestResponse:
    return IntelligenceDigestResponse.model_validate(
        build_user_daily_digest(db, current_user.id)
    )


@router.get("/feed", response_model=IntelligenceFeedResponse)
def get_intelligence_feed(
    limit: int = Query(20, ge=1, le=50),
    window: Literal["24h", "3d", "7d"] = Query("24h"),
    kind: Literal["all", "risk", "opinion", "news"] = Query("all"),
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


@router.get("/{topic_id}", response_model=IntelligenceDetailResponse)
def get_intelligence_detail(
    topic_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntelligenceDetailResponse:
    detail = build_user_intelligence_detail(db, current_user.id, topic_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="情报不存在或缺少原始证据")
    return IntelligenceDetailResponse.model_validate(detail)


@router.post(
    "/{topic_id}/corrections",
    response_model=IntelligenceCorrectionResponse,
    status_code=201,
)
def create_intelligence_correction(
    topic_id: UUID,
    body: IntelligenceCorrectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IntelligenceCorrectionResponse:
    correction = submit_intelligence_correction(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        category=body.category,
        note=body.note,
    )
    if correction is None:
        raise HTTPException(status_code=404, detail="情报不存在")
    return IntelligenceCorrectionResponse(
        id=str(correction.id),
        topic_id=str(correction.topic_id),
        category=correction.category,
        status=correction.status,
        created_at=correction.created_at,
    )
