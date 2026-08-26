from __future__ import annotations

from uuid import UUID

from app.services import user_resource_service
from app.services import tracking_service
from app.services import user_resource_service
from app.agents.chat.tool_results import tool_ok, tool_error


def set_blogger_follow_impl(db, user_id: UUID, handle: str, *, follow: bool) -> str:
    from sqlalchemy import func, select
    from app.models.blogger import Blogger
    from app.core.config import settings

    normalized = handle.strip().lstrip("@").lower()
    blogger = db.execute(
        select(Blogger).where(func.lower(Blogger.handle) == normalized)
    ).scalar_one_or_none()
    if not blogger:
        return tool_error("BLOGGER_NOT_FOUND", f"未找到博主 @{normalized}。请先新增信息源或获取博主资料。")
    if follow:
        user_resource_service.follow_blogger(
            db,
            user_id,
            blogger.id,
            max_follows=settings.max_followed_bloggers_per_user,
        )
        db.commit()
        return tool_ok(
            f"已将 @{blogger.handle} 加入正式关注列表。",
            data={"blogger_id": str(blogger.id), "handle": blogger.handle, "followed": True},
        )
    removed = user_resource_service.unfollow_blogger(db, user_id, blogger.id)
    db.commit()
    return tool_ok(
        f"已取消关注 @{blogger.handle}。" if removed else f"@{blogger.handle} 当前不在正式关注列表中。",
        data={"blogger_id": str(blogger.id), "handle": blogger.handle, "followed": False},
    )


def list_my_tracked_tickers_impl(db, user_id: UUID) -> str:
    """Return the current user's tracked ticker subscriptions."""
    items = tracking_service.list_subscriptions(db, user_id)
    if not items:
        return "当前没有订阅任何标的。可以通过「订阅 TSLA」来添加。"

    lines = [f"- {item.ticker} ({item.frequency}, {item.status})" for item in items]
    return f"你的订阅列表（{len(items)} 个）：\n" + "\n".join(lines)


def list_my_followed_bloggers_impl(db, user_id: UUID) -> str:
    """Return the current user's formal blogger follow list."""
    bloggers, total = user_resource_service.list_followed_bloggers(
        db,
        user_id,
        limit=20,
        offset=0,
    )
    if not bloggers:
        return "你的正式关注列表为空。可以先在个人工作台关注博主。"

    lines = []
    for blogger in bloggers:
        verified = int(blogger.total_predictions or 0)
        correct = float(blogger.correct_predictions or 0.0)
        accuracy = (correct / verified * 100) if verified else 0.0
        name = f"（{blogger.name}）" if blogger.name else ""
        lines.append(
            f"- @{blogger.handle}{name} | 可信度 {float(blogger.credibility_score):.1f}"
            f" | 已验证 {verified} | 准确率 {accuracy:.1f}%"
        )

    suffix = "" if total <= len(bloggers) else f"\n仅显示前 {len(bloggers)} 个，共 {total} 个。"
    return "你的正式关注列表：\n" + "\n".join(lines) + suffix
