from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.blogger import Blogger
from app.models.intelligence_event import IntelligenceEvent, IntelligenceTopic
from app.models.prediction import Prediction
from app.models.tracked_ticker import TrackedTicker
from app.models.tweet import Tweet
from app.models.user_alert import UserAlert
from app.models.user_blogger_follow import UserBloggerFollow


def _interested_user_ids(db: Session, *, blogger_handle: str, tickers: list[str]) -> set[UUID]:
    user_ids = set(db.execute(
        select(UserBloggerFollow.user_id)
        .join(Blogger, Blogger.id == UserBloggerFollow.blogger_id)
        .where(func.lower(Blogger.handle) == blogger_handle.lower())
    ).scalars())
    if tickers:
        user_ids.update(db.execute(
            select(TrackedTicker.user_id).where(
                TrackedTicker.status == "active",
                TrackedTicker.ticker.in_([ticker.upper() for ticker in tickers]),
            )
        ).scalars())
    return user_ids


def _create_alert(
    db: Session,
    *,
    user_id: UUID,
    alert_key: str,
    kind: str,
    severity: str,
    title: str,
    message: str,
    source_type: str,
    source_id: str,
    target_url: str,
    ticker: str | None,
    blogger_handle: str | None,
    occurred_at: datetime,
) -> bool:
    existing = db.execute(
        select(UserAlert.id).where(UserAlert.user_id == user_id, UserAlert.alert_key == alert_key)
    ).first()
    if existing:
        return False
    db.add(UserAlert(
        user_id=user_id,
        alert_key=alert_key,
        kind=kind,
        severity=severity,
        title=title,
        message=message[:1000],
        source_type=source_type,
        source_id=source_id,
        target_url=target_url,
        ticker=ticker,
        blogger_handle=blogger_handle,
        occurred_at=occurred_at,
    ))
    return True


def publish_intelligence_alerts(
    db: Session,
    *,
    event: IntelligenceEvent,
    topic: IntelligenceTopic,
    tweet: Tweet,
) -> int:
    if topic.lifecycle == "reversed":
        kind = "direction_reversal"
        severity = "high"
        title = f"{event.primary_ticker} 博主观点出现反转"
        message = topic.summary
    elif event.kind == "risk" and event.risk_level in {"high", "critical"}:
        kind = "high_risk"
        severity = "high"
        title = f"{event.primary_ticker} 出现高风险线索"
        message = event.summary
    else:
        return 0

    users = _interested_user_ids(
        db,
        blogger_handle=tweet.author_handle,
        tickers=event.tickers or [],
    )
    target = f"/tweets?q={quote(event.primary_ticker)}" if event.primary_ticker != "市场" else "/"
    created = 0
    for user_id in users:
        if _create_alert(
            db,
            user_id=user_id,
            alert_key=f"intelligence:{event.id}:{kind}",
            kind=kind,
            severity=severity,
            title=title,
            message=message,
            source_type="intelligence_event",
            source_id=str(event.id),
            target_url=target,
            ticker=event.primary_ticker if event.primary_ticker != "市场" else None,
            blogger_handle=tweet.author_handle,
            occurred_at=event.published_at,
        ):
            created += 1
    return created


def publish_prediction_alerts(db: Session, prediction: Prediction) -> int:
    users = _interested_user_ids(
        db,
        blogger_handle=prediction.blogger_handle,
        tickers=[prediction.ticker],
    )
    type_labels = {
        "price_direction": "价格方向预测",
        "price_target": "目标价格预测",
        "fundamental_metric": "基本面预测",
        "event_outcome": "事件预测",
    }
    direction = (
        "看好"
        if prediction.sentiment == "bullish"
        else "看空"
        if prediction.sentiment == "bearish"
        else "待验证"
    )
    target = prediction.target_spec or {}
    target_text = str(
        target.get("target_value")
        or target.get("target_condition")
        or target.get("target_metric")
        or direction
    )
    timing = (
        f"预计 {prediction.verifiable_at.date().isoformat()} 验证"
        if prediction.verifiable_at
        else "等待专用数据源补全验证日期"
    )
    created = 0
    for user_id in users:
        if _create_alert(
            db,
            user_id=user_id,
            alert_key=f"prediction:{prediction.id}:created",
            kind="new_prediction",
            severity="info",
            title=f"@{prediction.blogger_handle.lstrip('@')} 新增 {prediction.ticker} 预测",
            message=(
                f"{type_labels.get(prediction.prediction_type, '预测')} · "
                f"{target_text} · {prediction.investment_horizon}，{timing}。"
            ),
            source_type="prediction",
            source_id=str(prediction.id),
            target_url=f"/bloggers/{quote(prediction.blogger_handle, safe='')}",
            ticker=prediction.ticker,
            blogger_handle=prediction.blogger_handle,
            occurred_at=prediction.published_at,
        ):
            created += 1
    return created


def _serialize(alert: UserAlert) -> dict:
    return {
        "id": str(alert.id),
        "kind": alert.kind,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "target_url": alert.target_url,
        "ticker": alert.ticker,
        "blogger_handle": alert.blogger_handle,
        "status": alert.status,
        "occurred_at": alert.occurred_at,
        "read_at": alert.read_at,
    }


def list_alerts(db: Session, user_id: UUID, *, status: str, limit: int, offset: int) -> dict:
    filters = [UserAlert.user_id == user_id]
    if status != "all":
        filters.append(UserAlert.status == status)
    total = db.scalar(select(func.count()).select_from(UserAlert).where(*filters)) or 0
    unread = db.scalar(select(func.count()).select_from(UserAlert).where(
        UserAlert.user_id == user_id, UserAlert.status == "unread"
    )) or 0
    high_priority = db.scalar(select(func.count()).select_from(UserAlert).where(
        UserAlert.user_id == user_id,
        UserAlert.status == "unread",
        UserAlert.severity == "high",
    )) or 0
    rows = db.execute(
        select(UserAlert).where(*filters).order_by(UserAlert.occurred_at.desc()).limit(limit).offset(offset)
    ).scalars()
    return {
        "items": [_serialize(row) for row in rows],
        "total": int(total),
        "unread": int(unread),
        "high_priority": int(high_priority),
    }


def update_alert(db: Session, user_id: UUID, alert_id: UUID, *, action: str) -> dict | None:
    alert = db.execute(select(UserAlert).where(
        UserAlert.id == alert_id, UserAlert.user_id == user_id
    )).scalar_one_or_none()
    if alert is None:
        return None
    alert.status = "read" if action == "read" else "dismissed"
    alert.read_at = datetime.now(timezone.utc) if action == "read" else alert.read_at
    db.commit()
    db.refresh(alert)
    return _serialize(alert)


def mark_all_read(db: Session, user_id: UUID) -> int:
    alerts = list(db.execute(select(UserAlert).where(
        UserAlert.user_id == user_id, UserAlert.status == "unread"
    )).scalars())
    now = datetime.now(timezone.utc)
    for alert in alerts:
        alert.status = "read"
        alert.read_at = now
    db.commit()
    return len(alerts)
