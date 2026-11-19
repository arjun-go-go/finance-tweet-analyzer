from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbox_event import OutboxEvent
from app.models.runtime_control import RuntimeControl
from app.models.tweet import Tweet


ANALYSIS_CONTROL_KEY = "llm_analysis"
MODE_ENABLED = "enabled"
MODE_PAUSED_MANUAL = "paused_manual"
MODE_PAUSED_BUDGET = "paused_budget"
MODE_PAUSED_AUTH = "paused_auth"
MODE_COOLDOWN = "cooldown"

PAID_ANALYSIS_EVENTS = frozenset({
    "tweet.analysis_requested",
    "tweet.media_analyze_requested",
})


class AnalysisPausedError(RuntimeError):
    def __init__(self, control: dict[str, Any]):
        self.control = control
        reason = control.get("reason") or "大模型分析已暂停"
        super().__init__(str(reason))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create(db: Session, *, for_update: bool = False) -> RuntimeControl:
    query = (
        select(RuntimeControl)
        .where(RuntimeControl.key == ANALYSIS_CONTROL_KEY)
        .execution_options(populate_existing=True)
    )
    if for_update:
        query = query.with_for_update()
    control = db.execute(query).scalar_one_or_none()
    if control is None:
        control = RuntimeControl(
            key=ANALYSIS_CONTROL_KEY,
            mode=(MODE_ENABLED if settings.llm_analysis_default_enabled else MODE_PAUSED_MANUAL),
            reason=(None if settings.llm_analysis_default_enabled else "启动配置默认暂停"),
            updated_by="system",
        )
        db.add(control)
        db.flush()
    return control


def _resume_expired_cooldown(control: RuntimeControl) -> bool:
    if (
        control.mode == MODE_COOLDOWN
        and control.resume_after is not None
        and control.resume_after <= _now()
    ):
        control.mode = MODE_ENABLED
        control.reason = None
        control.resume_after = None
        control.paused_at = None
        control.consecutive_failures = 0
        control.updated_by = "automatic_recovery"
        return True
    return False


def serialize_analysis_control(control: RuntimeControl) -> dict[str, Any]:
    return {
        "key": control.key,
        "mode": control.mode,
        "enabled": control.mode == MODE_ENABLED,
        "reason": control.reason,
        "provider": control.provider,
        "model": control.model,
        "last_error": control.last_error,
        "consecutive_failures": control.consecutive_failures,
        "last_failure_at": control.last_failure_at.isoformat() if control.last_failure_at else None,
        "paused_at": control.paused_at.isoformat() if control.paused_at else None,
        "resume_after": control.resume_after.isoformat() if control.resume_after else None,
        "analysis_ingested_after": (
            control.analysis_ingested_after.isoformat() if control.analysis_ingested_after else None
        ),
        "updated_by": control.updated_by,
        "updated_at": control.updated_at.isoformat() if control.updated_at else None,
    }


def get_analysis_control(db: Session) -> dict[str, Any]:
    control = _get_or_create(db)
    if _resume_expired_cooldown(control):
        db.commit()
        db.refresh(control)
    return serialize_analysis_control(control)


def require_analysis_enabled(db: Session | None = None) -> dict[str, Any]:
    owns_session = db is None
    if owns_session:
        from app.core.deps import SessionLocal

        db = SessionLocal()
    assert db is not None
    try:
        control = _get_or_create(db)
        if _resume_expired_cooldown(control):
            if owns_session:
                db.commit()
            else:
                db.flush()
        snapshot = serialize_analysis_control(control)
        if owns_session:
            db.commit()
        if not snapshot["enabled"]:
            raise AnalysisPausedError(snapshot)
        return snapshot
    except AnalysisPausedError:
        raise
    except Exception as exc:
        logger.error("Unable to read LLM analysis control: {}", exc)
        raise AnalysisPausedError({
            "key": ANALYSIS_CONTROL_KEY,
            "mode": MODE_PAUSED_MANUAL,
            "enabled": False,
            "reason": "无法读取分析总开关，已按安全策略暂停模型调用",
        }) from exc
    finally:
        if owns_session:
            db.close()


def pause_analysis_manually(
    db: Session,
    *,
    reason: str,
    updated_by: str,
) -> dict[str, Any]:
    control = _get_or_create(db, for_update=True)
    control.mode = MODE_PAUSED_MANUAL
    control.reason = reason.strip() or "管理员手动暂停"
    control.paused_at = _now()
    control.resume_after = None
    control.updated_by = updated_by
    db.commit()
    db.refresh(control)
    return serialize_analysis_control(control)


def resume_analysis_manually(
    db: Session, *, updated_by: str, include_backlog: bool = True
) -> dict[str, Any]:
    control = _get_or_create(db, for_update=True)
    control.mode = MODE_ENABLED
    control.reason = None
    control.provider = None
    control.model = None
    control.last_error = None
    control.consecutive_failures = 0
    control.last_failure_at = None
    control.paused_at = None
    control.resume_after = None
    control.analysis_ingested_after = (
        None if include_backlog else (
            control.analysis_ingested_after or db.scalar(select(func.clock_timestamp()))
        )
    )
    control.updated_by = updated_by
    db.commit()
    db.refresh(control)
    return serialize_analysis_control(control)


def analysis_ingest_cutoff(control: dict[str, Any] | None) -> datetime | None:
    value = (control or {}).get("analysis_ingested_after")
    return datetime.fromisoformat(value) if value else None


def analysis_backlog(db: Session, control: dict[str, Any] | None = None) -> dict[str, int]:
    cutoff = analysis_ingest_cutoff(control or get_analysis_control(db))
    held = func.count().filter(Tweet.created_at < cutoff) if cutoff else func.count().filter(False)
    rows = db.execute(
        select(Tweet.status, func.count(), held).where(
            Tweet.status.in_([
                "media_analysis_ready",
                "media_analyzing",
                "pending",
                "analyzing",
                "retrying",
            ])
        ).group_by(Tweet.status)
    ).all()
    statuses = {status: int(count - waiting) for status, count, waiting in rows}
    held_outbox = db.execute(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.status == "pending",
            OutboxEvent.event_type.in_(PAID_ANALYSIS_EVENTS),
        )
    ).scalar_one()
    vision = statuses.get("media_analysis_ready", 0) + statuses.get("media_analyzing", 0)
    text = (
        statuses.get("pending", 0)
        + statuses.get("analyzing", 0)
        + statuses.get("retrying", 0)
    )
    return {
        "text": text,
        "vision": vision,
        "total": text + vision,
        "held_outbox": int(held_outbox or 0),
        "held_history": sum(int(waiting) for _, _, waiting in rows),
    }


def requeue_waiting_media_analysis(db: Session, *, ingested_after: datetime | None = None) -> int:
    from app.services.outbox_service import enqueue_outbox_event

    ready_media = select(Tweet.id).where(Tweet.status == "media_analysis_ready")
    if ingested_after is not None:
        ready_media = ready_media.where(Tweet.created_at >= ingested_after)
    tweet_ids = list(
        db.execute(ready_media).scalars().all()
    )
    if not tweet_ids:
        return 0

    pending_ids = {
        str(value)
        for value in db.execute(
            select(OutboxEvent.payload["tweet_id"].astext).where(
                OutboxEvent.status == "pending",
                OutboxEvent.event_type == "tweet.media_analyze_requested",
                OutboxEvent.payload["tweet_id"].astext.in_([str(value) for value in tweet_ids]),
            )
        ).scalars().all()
        if value
    }
    queued = 0
    for tweet_id in tweet_ids:
        if str(tweet_id) in pending_ids:
            continue
        enqueue_outbox_event(
            db,
            "tweet.media_analyze_requested",
            {"tweet_id": str(tweet_id)},
        )
        queued += 1
    db.commit()
    return queued


def _exception_details(exc: Exception) -> tuple[int | None, str | None, str]:
    messages: list[str] = []
    status_code: int | None = None
    error_code: str | None = None
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current))
        if error_code is None:
            raw_code = getattr(current, "code", None)
            if isinstance(raw_code, str):
                error_code = raw_code
        if status_code is None:
            raw_status = getattr(current, "status_code", None)
            if isinstance(raw_status, int):
                status_code = raw_status
            response = getattr(current, "response", None)
            response_status = getattr(response, "status_code", None)
            if isinstance(response_status, int):
                status_code = response_status
            response_text = getattr(response, "text", None)
            if response_text:
                messages.append(str(response_text))
        current = current.__cause__ or current.__context__
    return status_code, error_code, " | ".join(part for part in messages if part)[:2000]


def record_model_failure(
    exc: Exception,
    *,
    provider: str,
    model: str,
) -> dict[str, Any] | None:
    if not settings.llm_auto_pause_enabled or isinstance(exc, AnalysisPausedError):
        return None

    status_code, error_code, error_text = _exception_details(exc)
    lowered = error_text.lower()
    budget_error = status_code == 402 or error_code in {
        "credit_balance_exhausted",
        "insufficient_quota",
        "organization_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "project_spend_limit_exceeded",
    } or any(token in lowered for token in (
        "insufficient credit",
        "insufficient_credit",
        "insufficient quota",
        "insufficient_quota",
        "credit balance",
        "payment required",
    ))
    auth_error = status_code in {401, 403} or any(token in lowered for token in (
        "invalid api key",
        "invalid_api_key",
        "authentication failed",
        "unauthorized",
    ))
    rate_limit = status_code == 429
    transient = (
        status_code is not None and status_code >= 500
    ) or any(token in lowered for token in (
        "timed out",
        "timeout",
        "connection error",
        "connection reset",
        "temporarily unavailable",
    ))
    if not (budget_error or auth_error or rate_limit or transient):
        return None

    from app.core.deps import SessionLocal

    db = SessionLocal()
    try:
        control = _get_or_create(db, for_update=True)
        now = _now()
        if control.mode == MODE_PAUSED_MANUAL:
            return serialize_analysis_control(control)
        control.provider = provider
        control.model = model
        control.last_error = error_text
        control.last_failure_at = now
        control.consecutive_failures = (control.consecutive_failures or 0) + 1
        control.updated_by = "automatic_protection"

        if budget_error:
            control.mode = MODE_PAUSED_BUDGET
            control.reason = "模型服务余额或额度不足，已自动暂停"
            control.paused_at = now
            control.resume_after = None
        elif auth_error:
            control.mode = MODE_PAUSED_AUTH
            control.reason = "模型服务认证失败，已自动暂停"
            control.paused_at = now
            control.resume_after = None
        else:
            threshold = (
                settings.llm_rate_limit_failure_threshold
                if rate_limit
                else settings.llm_transient_failure_threshold
            )
            if control.consecutive_failures >= threshold:
                control.mode = MODE_COOLDOWN
                control.reason = (
                    "模型服务连续限流，已进入临时冷却"
                    if rate_limit
                    else "模型服务连续不可用，已进入临时冷却"
                )
                control.paused_at = now
                control.resume_after = now + timedelta(
                    seconds=settings.llm_transient_cooldown_seconds
                )

        db.commit()
        db.refresh(control)
        snapshot = serialize_analysis_control(control)
        if not snapshot["enabled"]:
            logger.error(
                "LLM analysis automatically paused: mode={} provider={} model={} reason={}",
                control.mode,
                provider,
                model,
                control.reason,
            )
        return snapshot
    except Exception as control_error:
        db.rollback()
        logger.error("Failed to record model failure: {}", control_error)
        return None
    finally:
        db.close()


def record_model_success(db: Session) -> None:
    control = _get_or_create(db, for_update=True)
    if control.mode != MODE_ENABLED or not control.consecutive_failures:
        return
    control.consecutive_failures = 0
    control.last_error = None
    control.last_failure_at = None
    control.provider = None
    control.model = None
    control.updated_by = "model_success"
    db.flush()
