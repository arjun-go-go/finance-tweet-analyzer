"""预测 Agent —— 标的聚合 + 可验证预测生成。

职责：
    1. 标的聚合 (_aggregate_tickers)：将多条推文分析结果按 ticker 维度汇聚，
       统计多空比例，生成共识评级 (strong_buy / buy / neutral / sell / strong_sell)。
    2. 预测生成 (_generate_predictions)：将满足条件的分析结果转化为可验证的预测记录，
       设定验证时间窗口（short=7天 / medium=30天 / long=180天），用于后续标注与可信度计算。

运行方式：
    - 已从 Supervisor 实时管道中移除
    - 由 Celery prediction_batch_task 定时调用（每5分钟）
    - 输入：已完成分析 + 关联推文数据（从 DB 查询组装）

去重策略：
    同一博主 + 同一标的 + 同一方向 + 24小时内 → 只保留一条预测，
    避免同一篇推文被重复处理时产生重复预测。
"""
from collections import defaultdict
from datetime import datetime, timedelta

from app.schemas.signal import TickerSummary

# 投资周期 → 验证天数映射
HORIZON_DAYS = {"short": 7, "medium": 30, "long": 180, "unknown": 30}


def prediction_agent_node(state: dict) -> dict:
    """预测 Agent 主入口。

    Args:
        state: 包含 analyses（分析结果列表）和 tweets（原始推文列表）

    Returns:
        {"ticker_summaries": [...], "predictions": [...]}
    """
    analyses = state.get("analyses", [])
    tweets = state.get("tweets", [])

    ticker_summaries = _aggregate_tickers(analyses)
    predictions = _generate_predictions(analyses, tweets)

    return {
        "ticker_summaries": ticker_summaries,
        "predictions": predictions,
    }


# ============================================================
# 标的维度聚合 —— 多博主多推文 → 单标的综合评级
# ------------------------------------------------------------
# 算法：
#   1. 按 ticker 聚合所有投资相关分析的 sentiment
#   2. 计算 bullish 占比 → 映射到共识等级
#   3. 合并 key_points + risks 去重
#   4. 输出 TickerSummary 供前端标的排行展示
# ============================================================
def _aggregate_tickers(analyses: list[dict]) -> list[dict]:
    """将分析结果按标的聚合，生成共识评级和推荐分数。"""
    # 过滤出投资相关的分析
    investment_analyses = [
        a for a in analyses if a.get("is_investment_related")
    ]

    # 按 ticker 收集统计数据
    ticker_data: dict[str, dict] = defaultdict(lambda: {
        "bloggers": set(),
        "bullish": 0,
        "bearish": 0,
        "neutral": 0,
        "key_points": [],
        "risks": [],
    })

    for analysis in investment_analyses:
        raw_tickers = analysis.get("tickers", [])

        for ticker_item in raw_tickers:
            symbol = ticker_item.get("symbol", "")
            sentiment = ticker_item.get("sentiment", "neutral")

            if not symbol:
                continue

            data = ticker_data[symbol]
            data["bloggers"].add(analysis["author_handle"])
            if sentiment == "bullish":
                data["bullish"] += 1
            elif sentiment == "bearish":
                data["bearish"] += 1
            else:
                data["neutral"] += 1
            data["key_points"].extend(analysis.get("key_points", []))
            data["risks"].extend(analysis.get("risk_factors", []))

    # 计算共识评级和推荐分数
    summaries = []
    for ticker, data in ticker_data.items():
        total = data["bullish"] + data["bearish"] + data["neutral"]
        if total == 0:
            continue

        # 多空比例 → 共识等级
        bullish_ratio = data["bullish"] / total
        if bullish_ratio >= 0.7:
            consensus = "strong_buy"
        elif bullish_ratio >= 0.5:
            consensus = "buy"
        elif data["bearish"] / total >= 0.7:
            consensus = "strong_sell"
        elif data["bearish"] / total >= 0.5:
            consensus = "sell"
        else:
            consensus = "neutral"

        # 推荐分数 = bullish 占比 * 100（前端排序用）
        score = round(bullish_ratio * 100, 1)

        # 观点去重（保留顺序，最多5条）
        points = data["key_points"]
        unique_points = list(dict.fromkeys(points))[:5]
        risks = list(dict.fromkeys(data["risks"]))[:3]
        summary_parts = unique_points
        if risks:
            summary_parts.append(f"风险提示: {'; '.join(risks)}")

        summaries.append(TickerSummary(
            ticker=ticker,
            mention_count=total,
            bloggers=sorted(data["bloggers"]),
            consensus=consensus,
            bullish_count=data["bullish"],
            bearish_count=data["bearish"],
            recommendation_score=score,
            summary="；".join(summary_parts),
        ).model_dump())

    # 按推荐分数降序排列
    summaries.sort(key=lambda x: x["recommendation_score"], reverse=True)
    return summaries


# ============================================================
# 预测记录生成 —— 分析结果 → 可验证预测
# ------------------------------------------------------------
# 筛选条件：
#   1. is_investment_related = True
#   2. confidence >= 0.5（低置信度分析不产出预测）
#   3. 有明确 ticker
#
# 去重规则（内存级）：
#   同一 (博主, 标的, 方向) 在 24h 内只产出一条预测。
#   DB 级去重由 prediction_service.save_predictions_batch 再做一层保障。
#
# 验证时间计算：
#   published_at + HORIZON_DAYS[investment_horizon]
# ============================================================
def _generate_predictions(analyses: list[dict], tweets: list[dict]) -> list[dict]:
    """将高置信度分析转化为可验证预测记录。"""
    tweet_by_id = {t["id"]: t for t in tweets}
    out: list[dict] = []
    # 内存去重：(博主, 标的, 方向) → 最近一次发布时间
    seen_by_key: dict[tuple, datetime] = {}

    # 按发布时间排序，确保去重时保留最早的预测
    sorted_analyses = sorted(
        [a for a in analyses if a.get("tweet_id") in tweet_by_id],
        key=lambda a: tweet_by_id[a["tweet_id"]]["published_at"],
    )

    for analysis in sorted_analyses:
        # 跳过非投资相关
        if not analysis.get("is_investment_related"):
            continue
        # 跳过低置信度
        if analysis.get("confidence", 0) < 0.5:
            continue

        tweet = tweet_by_id[analysis["tweet_id"]]
        published_at: datetime = tweet["published_at"]

        # 为每个 ticker 生成一条预测
        raw_tickers = analysis.get("tickers", []) or []

        for ticker_item in raw_tickers:
            ticker = ticker_item.get("symbol", "")
            sentiment = ticker_item.get("sentiment", "neutral")
            horizon = ticker_item.get("horizon", "unknown")

            if not ticker:
                continue

            days = HORIZON_DAYS.get(horizon, 30)
            verifiable_at = published_at + timedelta(days=days)

            key = (analysis["author_handle"], ticker, sentiment)
            prior = seen_by_key.get(key)
            # 24h 内去重：同博主同标的同方向不重复
            if prior is not None and abs(published_at - prior) < timedelta(hours=24):
                continue
            seen_by_key[key] = published_at
            out.append({
                "tweet_id": analysis["tweet_id"],
                "blogger_handle": analysis["author_handle"],
                "ticker": ticker,
                "sentiment": sentiment,
                "investment_horizon": horizon,
                "published_at": published_at,
                "verifiable_at": verifiable_at,
            })

    return out
