from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_admin, get_current_user
from app.models.user import User
from app.scheduler.locks import try_acquire, release
from app.services.analysis_service import (
    analyze_by_blogger,
    analyze_by_bloggers,
    analyze_single_tweet,
    trigger_analysis,
)
from app.services.analysis_control_service import (
    AnalysisPausedError,
    get_analysis_control,
    require_analysis_enabled,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisResponse(BaseModel):
    batch_id: str
    analyzed: int
    analyses: list[dict]
    claims_created: int


class MultiBloggerRequest(BaseModel):
    blogger_handles: list[str]


def _require_analysis_available(db: Session) -> None:
    try:
        require_analysis_enabled(db)
    except AnalysisPausedError as exc:
        raise HTTPException(
            status_code=423,
            detail={
                "message": str(exc),
                "analysis_control": exc.control,
            },
        ) from exc


@router.get("/status")
def analysis_status_endpoint(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    control = get_analysis_control(db)
    messages = {
        "paused_manual": "大模型分析已由管理员暂停",
        "paused_budget": "模型额度不足，分析已自动暂停",
        "paused_auth": "模型服务认证异常，分析已自动暂停",
        "cooldown": "模型服务暂时不可用，分析正在冷却等待恢复",
    }
    return {
        "enabled": control["enabled"],
        "mode": control["mode"],
        "message": messages.get(control["mode"]),
        "paused_at": control["paused_at"],
        "resume_after": control["resume_after"],
        "analysis_ingested_after": control["analysis_ingested_after"],
    }


@router.post("/trigger", response_model=AnalysisResponse)
def trigger_analysis_endpoint(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """分析所有 pending 推文"""
    _require_analysis_available(db)
    return trigger_analysis(db)


@router.post("/tweet/{tweet_id}", response_model=AnalysisResponse)
def analyze_single_tweet_endpoint(
    tweet_id: str,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """分析单条推文（支持重新分析已分析过的推文）"""
    _require_analysis_available(db)
    lock_key = f"tweet_analysis:{tweet_id}"
    acquired, lock_token = try_acquire(lock_key)
    if not acquired:
        raise HTTPException(status_code=409, detail="该推文正在分析中，请稍后再试")
    try:
        return analyze_single_tweet(db, tweet_id)
    finally:
        release(lock_key, lock_token)


@router.post("/blogger/{blogger_handle}", response_model=AnalysisResponse)
def analyze_single_blogger(
    blogger_handle: str,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """分析单个博主的推文"""
    _require_analysis_available(db)
    acquired, lock_token = try_acquire(blogger_handle)
    if not acquired:
        raise HTTPException(status_code=409, detail=f"正在分析 {blogger_handle}，请稍后再试")
    try:
        return analyze_by_blogger(db, blogger_handle)
    finally:
        release(blogger_handle, lock_token)


@router.post("/bloggers", response_model=AnalysisResponse)
def analyze_multiple_bloggers(
    request: MultiBloggerRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """多博主综合分析，交叉对比观点"""
    _require_analysis_available(db)
    return analyze_by_bloggers(db, request.blogger_handles)
