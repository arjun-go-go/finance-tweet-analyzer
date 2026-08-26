"""Deterministic read-only queries for common Chat Agent requests."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from app.agents.chat.tool_results import tool_error, tool_ok
from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.services.blogger_service import get_blogger_detail, list_predictions_by_blogger


def _direct(message: str, data: dict | None = None) -> str:
    payload = {"direct_response": True}
    payload.update(data or {})
    return tool_ok(message, data=payload)


def _find_blogger(db, handle: str) -> Blogger | None:
    return db.execute(
        select(Blogger).where(func.lower(Blogger.handle) == handle.strip().lstrip("@").lower())
    ).scalar_one_or_none()


def get_blogger_overview_impl(db, handle: str) -> str:
    blogger = _find_blogger(db, handle)
    if blogger is None:
        return tool_error("BLOGGER_NOT_FOUND", f"未找到博主 @{handle.strip().lstrip('@')}。")
    detail = get_blogger_detail(db, blogger.handle)
    if detail is None:
        return tool_error("BLOGGER_NOT_FOUND", f"未找到博主 @{blogger.handle}。")
    hit_rate = detail.get("hit_rate_overall")
    lines = [
        f"@{blogger.handle}（{blogger.name or '未设置昵称'}）",
        f"简介：{blogger.bio or '暂无简介'}",
        f"粉丝：{blogger.followers_count:,}；推文总数：{blogger.tweets_count:,}；关注：{blogger.following_count:,}",
        (
            f"预测评分：{detail['credibility_score']:.1f}（{detail['score_label']}，"
            f"样本充分度 {detail['sample_confidence'] * 100:.0f}%）；"
            f"已验证预测：{detail['verified_count']}；待验证：{detail['pending_count']}"
            if detail["verified_count"]
            else f"预测评分：暂无；已验证预测：0；待验证：{detail['pending_count']}"
        ),
        f"已验证命中率：{hit_rate * 100:.1f}%" if hit_rate is not None else "已验证命中率：暂无足够数据",
    ]
    if detail.get("top_tickers"):
        lines.append("擅长标的：" + "、".join(item["ticker"] for item in detail["top_tickers"][:5]))
    return _direct("\n".join(lines), {"handle": blogger.handle})


def get_blogger_recent_analysis_impl(db, handle: str, limit: int = 5) -> str:
    blogger = _find_blogger(db, handle)
    if blogger is None:
        return tool_error("BLOGGER_NOT_FOUND", f"未找到博主 @{handle.strip().lstrip('@')}。")
    rows = db.execute(
        select(AnalysisResult, Tweet)
        .join(Tweet, AnalysisResult.tweet_id == Tweet.id)
        .where(func.lower(Tweet.author_handle) == blogger.handle.lower())
        .order_by(AnalysisResult.created_at.desc())
        .limit(max(1, min(limit, 10)))
    ).all()
    if not rows:
        return _direct(f"@{blogger.handle} 暂无分析结果。", {"handle": blogger.handle})
    lines = [f"@{blogger.handle} 最近 {len(rows)} 条分析："]
    for index, (analysis, tweet) in enumerate(rows, 1):
        result = analysis.result or {}
        tickers = [str(item.get("symbol") or item.get("ticker") or "") for item in result.get("tickers") or [] if isinstance(item, dict)]
        points = result.get("key_points") or []
        summary = "；".join(str(point) for point in points[:2]) or str(result.get("reasoning") or "暂无观点摘要")[:260]
        lines.append(
            f"{index}. {tweet.published_at:%Y-%m-%d} | {','.join(filter(None, tickers)) or '未识别标的'} | "
            f"置信度 {float(analysis.confidence or 0):.2f}\n{summary[:360]}"
        )
    return _direct("\n\n".join(lines), {"handle": blogger.handle, "count": len(rows)})


def _prediction_lines(items: list[dict], title: str) -> str:
    if not items:
        return f"{title}：暂无匹配预测。"
    lines = [f"{title}（最近 {len(items)} 条）："]
    labels = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
    verdicts = {None: "待验证", "correct": "正确", "partial": "部分正确", "incorrect": "错误", "excluded": "已排除"}
    for index, item in enumerate(items, 1):
        lines.append(
            f"{index}. {item['ticker']} | {labels.get(item['sentiment'], item['sentiment'])} | "
            f"{item['investment_horizon']} | {verdicts.get(item['verdict'], item['verdict'])} | "
            f"{str(item.get('published_at') or '')[:10]}\n{item['tweet']['content'][:220]}"
        )
    return "\n\n".join(lines)


def get_blogger_predictions_impl(db, handle: str, status: str = "all", limit: int = 5) -> str:
    blogger = _find_blogger(db, handle)
    if blogger is None:
        return tool_error("BLOGGER_NOT_FOUND", f"未找到博主 @{handle.strip().lstrip('@')}。")
    result = list_predictions_by_blogger(db, blogger.handle, status=status, limit=max(1, min(limit, 10)))
    return _direct(
        _prediction_lines(result["items"], f"@{blogger.handle} 的预测；共 {result['total']} 条"),
        {"handle": blogger.handle, "total": result["total"]},
    )


def get_ticker_predictions_impl(db, ticker: str, status: str = "all", limit: int = 5) -> str:
    normalized = ticker.strip().upper().lstrip("$")
    query = select(Prediction, Tweet).join(Tweet, Prediction.tweet_id == Tweet.id).where(Prediction.ticker == normalized)
    if status == "pending":
        query = query.where(Prediction.verdict.is_(None))
    elif status == "verified":
        query = query.where(Prediction.verdict.in_(("correct", "partial", "incorrect")))
    rows = db.execute(query.order_by(Prediction.published_at.desc()).limit(max(1, min(limit, 10)))).all()
    items = [{
        "ticker": prediction.ticker,
        "sentiment": prediction.sentiment,
        "investment_horizon": prediction.investment_horizon,
        "verdict": prediction.verdict,
        "published_at": prediction.published_at.isoformat() if prediction.published_at else None,
        "tweet": {"content": tweet.content},
    } for prediction, tweet in rows]
    return _direct(_prediction_lines(items, f"{normalized} 相关预测"), {"ticker": normalized, "count": len(items)})


def get_prediction_review_summary_impl(db) -> str:
    rows = db.execute(
        select(Prediction.verdict, func.count(Prediction.id)).group_by(Prediction.verdict)
    ).all()
    counts = {verdict or "pending": int(count) for verdict, count in rows}
    message = (
        "预测复核概况：\n"
        f"待验证/待处理：{counts.get('pending', 0)}\n"
        f"正确：{counts.get('correct', 0)}；部分正确：{counts.get('partial', 0)}；"
        f"错误：{counts.get('incorrect', 0)}；已排除：{counts.get('excluded', 0)}"
    )
    return _direct(message, {"counts": counts})
