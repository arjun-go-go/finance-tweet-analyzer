"""博主画像查询服务 —— 供 analysis_agent / risk_agent 共享。

职责：
    批量查询博主历史可信度、命中率、情绪分布，
    生成可注入 system prompt 的上下文文本块。

为什么独立为 service：
    analysis_agent 和 risk_agent 都需要博主画像，
    抽取到此处避免 agent 间直接依赖（循环引用/耦合风险）。
"""
from sqlalchemy import func, select

from app.core.deps import SessionLocal
from app.models.blogger import Blogger
from app.models.prediction import Prediction
from app.services.credibility import compute_score


def fetch_blogger_contexts(handles: list[str]) -> dict[str, str]:
    """批量查询博主可信度 + 情绪分布，返回 {handle: context_string} 字典。"""
    if not handles:
        return {}

    db = SessionLocal()
    try:
        bloggers = db.execute(
            select(Blogger).where(Blogger.handle.in_(handles))
        ).scalars().all()
        blogger_map = {b.handle: b for b in bloggers}

        sentiment_rows = db.execute(
            select(
                Prediction.blogger_handle,
                Prediction.sentiment,
                func.count().label("cnt"),
            )
            .where(
                Prediction.blogger_handle.in_(handles),
                Prediction.verdict.is_not(None),
            )
            .group_by(Prediction.blogger_handle, Prediction.sentiment)
        ).all()

        stats_rows = db.execute(
            select(
                Prediction.blogger_handle,
                func.count().label("total"),
                func.coalesce(func.sum(Prediction.score), 0.0).label("correct_sum"),
            )
            .where(
                Prediction.blogger_handle.in_(handles),
                Prediction.verdict.is_not(None),
            )
            .group_by(Prediction.blogger_handle)
        ).all()

        stats_map: dict[str, dict] = {}
        for handle, total, correct_sum in stats_rows:
            hit_rate = float(correct_sum) / total if total > 0 else None
            score = compute_score(float(correct_sum), int(total))
            stats_map[handle] = {
                "total": int(total),
                "hit_rate": hit_rate,
                "credibility": round(score, 1),
            }

        sentiment_map: dict[str, dict[str, int]] = {}
        for handle, sentiment, cnt in sentiment_rows:
            sentiment_map.setdefault(handle, {})[sentiment] = int(cnt)

        contexts: dict[str, str] = {}
        for handle in handles:
            parts = []
            blogger = blogger_map.get(handle)
            stats = stats_map.get(handle)

            if stats and stats["total"] > 0:
                hr_str = f"{stats['hit_rate']:.0%}" if stats["hit_rate"] is not None else "N/A"
                parts.append(
                    f"可信度={stats['credibility']}, "
                    f"历史预测={stats['total']}次, 命中率={hr_str}"
                )
                sent = sentiment_map.get(handle, {})
                if sent:
                    dist = ", ".join(f"{k}:{v}" for k, v in sorted(sent.items()))
                    parts.append(f"历史情绪分布: {dist}")
            elif blogger:
                parts.append("新博主, 暂无历史预测数据")
            else:
                parts.append("未入库博主, 无历史数据")

            if blogger and blogger.market_focus:
                parts.append(f"关注领域: {', '.join(blogger.market_focus)}")

            contexts[handle] = "; ".join(parts)

        return contexts
    finally:
        db.close()


def build_blogger_context_block(contexts: dict[str, str]) -> str:
    """将博主画像字典格式化为可直接嵌入 system prompt 的文本块。"""
    if not contexts:
        return "暂无博主历史数据"
    lines = ["博主历史画像（供参考）："]
    for handle, ctx in contexts.items():
        lines.append(f"- @{handle}: {ctx}")
    return "\n".join(lines)
