"""
结构化数据检索器（SQL 路径）
============================================================
职责：从 PostgreSQL 中精确查询预测结果和规范化逐标的观点。

为什么不走向量检索：
- predictions 和 instrument_claims 是结构化表数据（含数值字段如 score/verdict）
- 需要精确的 ticker 过滤 + 时间排序，SQL 比向量检索更高效更精确
- 结果已经是结构化的（不需要语义匹配），直接按 ticker 查询即可

提供的数据类型：
1. Prediction：系统对某 ticker 的多空预测（含 sentiment/score/verdict）
2. InstrumentClaim：对某 ticker 的独立观点、证据与归属

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
from app.models.instrument_claim import InstrumentClaim
from app.models.prediction import Prediction
from app.models.tweet import Tweet


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

        # 路径 2：规范化逐标的观点
        claim_stmt = (
            select(InstrumentClaim, Tweet)
            .join(
                AnalysisResult,
                AnalysisResult.id == InstrumentClaim.analysis_result_id,
            )
            .join(Tweet, Tweet.id == AnalysisResult.tweet_id)
            .where(InstrumentClaim.downstream_eligible.is_(True))
        )
        if has_ticker:
            claim_stmt = claim_stmt.where(
                InstrumentClaim.instrument_symbol == intent.ticker.upper()
            )
        else:
            claim_stmt = claim_stmt.limit(10)
        if intent.blogger_filter:
            claim_stmt = claim_stmt.where(
                Tweet.author_handle.in_(intent.blogger_filter)
            )
        if intent.sentiment_filter:
            claim_stmt = claim_stmt.where(
                InstrumentClaim.direction.in_(intent.sentiment_filter)
            )
        if intent.horizon_filter:
            claim_stmt = claim_stmt.where(
                InstrumentClaim.horizon.in_(intent.horizon_filter)
            )
        if intent.time_range_start:
            claim_stmt = claim_stmt.where(Tweet.published_at >= intent.time_range_start)
        if intent.time_range_end:
            claim_stmt = claim_stmt.where(Tweet.published_at <= intent.time_range_end)
        claim_rows = db.execute(
            claim_stmt.order_by(Tweet.published_at.desc()).limit(20)
        ).all()

        for claim, tweet in claim_rows:
            content_parts = [
                f"标的：{claim.instrument_symbol}",
                f"方向：{claim.direction}",
                f"周期：{claim.horizon}",
                f"类型：{claim.claim_type}",
                f"归属：{claim.opinion_source}",
                f"商业关联：{claim.sponsor_relation}",
            ]
            if claim.thesis:
                content_parts.append(f"观点：{claim.thesis}")
            if claim.evidence:
                content_parts.append(f"证据：{'；'.join(claim.evidence)}")
            results.append({
                "unique_id": f"claim:{claim.id}",
                "content": " | ".join(content_parts),
                "source_type": "structured",
                "metadata": {
                    "source_type": "claim",
                    "source_id": str(claim.id),
                    "ticker": claim.instrument_symbol,
                    "direction": claim.direction,
                    "sentiment": claim.direction,
                    "horizon": claim.horizon,
                    "claim_type": claim.claim_type,
                    "opinion_source": claim.opinion_source,
                    "has_commercial_content": claim.sponsor_relation != "none",
                    "sponsor_relation": claim.sponsor_relation,
                    "performance_eligible": claim.performance_eligible,
                    "performance_exclusion_reason": (
                        claim.performance_exclusion_reason or ""
                    ),
                    "blogger_handle": tweet.author_handle,
                    "published_at": tweet.published_at.isoformat(),
                },
                "score": 0.6,
            })

    finally:
        db.close()

    return results
