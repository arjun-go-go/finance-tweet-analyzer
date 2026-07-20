from __future__ import annotations

from uuid import UUID

from app.services import user_resource_service
from app.services import tracking_service


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
