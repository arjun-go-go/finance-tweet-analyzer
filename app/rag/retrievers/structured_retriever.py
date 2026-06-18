"""
结构化数据检索器（SQL 路径）
============================================================
职责：从 PostgreSQL 中查询与 ticker 相关的预测结果和分析摘要。

为什么不走向量检索：
- predictions 和 analysis_results 是结构化表数据（含数值字段如 score/verdict）
- 需要精确的 ticker 过滤 + 时间排序，SQL 比向量检索更高效更精确
- 结果已经是结构化的（不需要语义匹配），直接按 ticker 查询即可

提供的数据类型：
1. Prediction：系统对某 ticker 的多空预测（含 sentiment/score/verdict）
2. AnalysisResult（ticker_summary 类型）：对某 ticker 的汇总分析

与向量检索路径互补：向量路径提供语义相关的非结构化内容，
SQL 路径提供精确的结构化数据（历史预测准确率、数值评分等）。

注意：此检索器的 score 是固定值（0.5/0.6），因为 SQL 查询无相似度概念。
RRF 融合时只看排名不看分数，所以固定值不影响最终融合质量。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.self_query_agent import QueryIntent
from app.core.deps import SessionLocal
from app.models.analysis import AnalysisResult
from app.models.prediction import Prediction


def retrieve_structured(intent: QueryIntent) -> list[dict]:
    """从 PostgreSQL 查询 ticker 相关的预测和分析摘要。"""
    db: Session = SessionLocal()
    results: list[dict] = []

    try:
        has_ticker = intent.ticker and intent.ticker != "UNKNOWN"

        # 路径 1：预测结果（仅返回已验证的预测，score 不为空）
        if has_ticker:
            pred_stmt = (
                select(Prediction)
                .where(
                    Prediction.ticker == intent.ticker,
                    Prediction.score.isnot(None),
                )
                .order_by(Prediction.created_at.desc())
                .limit(20)
            )
        else:
            pred_stmt = (
                select(Prediction)
                .where(Prediction.score.isnot(None))
                .order_by(Prediction.created_at.desc())
                .limit(10)
            )

        if intent.blogger_filter:
            pred_stmt = pred_stmt.where(
                Prediction.blogger_handle.in_(intent.blogger_filter)
            )
        if intent.time_range_start:
            pred_stmt = pred_stmt.where(Prediction.created_at >= intent.time_range_start)
        if intent.time_range_end:
            pred_stmt = pred_stmt.where(Prediction.created_at <= intent.time_range_end)

        predictions = db.execute(pred_stmt).scalars().all()

        for p in predictions:
            results.append({
                "unique_id": f"pred:{p.id}",
                "content": (
                    f"Ticker: {p.ticker} | Sentiment: {p.sentiment} | "
                    f"Score: {p.score} | Verdict: {p.verdict} | "
                    f"Blogger: {p.blogger_handle}"
                ),
                "source_type": "structured",
                "metadata": {
                    "ticker": p.ticker,
                    "sentiment": p.sentiment,
                    "blogger_handle": p.blogger_handle,
                    "score": p.score,
                    "verdict": p.verdict,
                    "created_at": p.created_at.isoformat() if p.created_at else "",
                },
                "score": 0.5,
            })

        # 路径 2：ticker_summary 汇总分析
        if has_ticker:
            ticker_summaries = db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.analysis_type == "ticker_summary",
                    AnalysisResult.result["ticker"].astext == intent.ticker,
                )
            ).scalars().all()
        else:
            ticker_summaries = db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.analysis_type == "ticker_summary")
                .order_by(AnalysisResult.result["recommendation_score"].desc())
                .limit(5)
            ).scalars().all()

        for ts in ticker_summaries:
            data = ts.result or {}
            content_parts = [
                f"标的：{data.get('ticker', '')}",
                f"共识：{data.get('consensus', 'neutral')}",
                f"推荐度：{data.get('recommendation_score', 0)}",
                f"看多：{data.get('bullish_count', 0)} 看空：{data.get('bearish_count', 0)}",
            ]
            if data.get("summary"):
                content_parts.append(f"观点：{data['summary']}")
            if data.get("bloggers"):
                content_parts.append(f"博主：{'、'.join(data['bloggers'][:5])}")
            results.append({
                "unique_id": f"summary:{ts.id}",
                "content": " | ".join(content_parts),
                "source_type": "structured",
                "metadata": data,
                "score": 0.6,
            })

    finally:
        db.close()

    return results
