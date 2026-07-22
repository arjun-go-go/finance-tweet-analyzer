import time
import uuid

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.supervisor import supervisor
from app.core.config import settings
from app.models.analysis import AnalysisResult
from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.services.trace_service import write_trace_immediate

BATCH_SIZE = 10


def analyze_single_tweet(db: Session, tweet_id: str) -> dict:
    """分析单条推文（支持重新分析已分析过的推文）。"""
    batch_id = uuid.uuid4()

    tweet = db.execute(
        select(Tweet).where(Tweet.id == uuid.UUID(tweet_id))
    ).scalar_one_or_none()

    if not tweet:
        return {
            "batch_id": str(batch_id),
            "analyzed": 0,
            "analyses": [],
            "ticker_summaries": [],
            "error": f"Tweet {tweet_id} not found",
        }

    # Allow re-analysis: reset status to pending so _run_analysis picks it up
    tweet.status = "pending"
    db.commit()

    return _run_analysis(db, [tweet], batch_id)


def analyze_by_blogger(db: Session, blogger_handle: str) -> dict:
    batch_id = uuid.uuid4()

    tweets = db.execute(
        select(Tweet).where(
            Tweet.author_handle == blogger_handle,
            Tweet.status == "pending",
        )
        .order_by(Tweet.published_at.desc())
        .limit(50)
    ).scalars().all()

    if not tweets:
        return _empty_result(batch_id)
    return _run_analysis(db, tweets, batch_id)


def analyze_by_bloggers(db: Session, blogger_handles: list[str]) -> dict:
    batch_id = uuid.uuid4()

    tweets = db.execute(
        select(Tweet).where(
            Tweet.author_handle.in_(blogger_handles),
            Tweet.status == "pending",
        )
        .order_by(Tweet.published_at.desc())
        .limit(100)
    ).scalars().all()

    if not tweets:
        return _empty_result(batch_id)
    return _run_analysis(db, tweets, batch_id)


def trigger_analysis(db: Session) -> dict:
    batch_id = uuid.uuid4()

    pending_tweets = db.execute(
        select(Tweet).where(Tweet.status == "pending").limit(50)
    ).scalars().all()

    if not pending_tweets:
        return _empty_result(batch_id)

    return _run_analysis(db, pending_tweets, batch_id)


def _empty_result(batch_id: uuid.UUID) -> dict:
    return {
        "batch_id": str(batch_id),
        "analyzed": 0,
        "analyses": [],
        "ticker_summaries": [],
    }


def _mark_successful_tweets(
    tweets: list[Tweet], analyses: list[dict]
) -> list[Tweet]:
    """Mark only tweets that produced an analysis as completed."""
    successful_ids = {
        str(analysis.get("tweet_id"))
        for analysis in analyses
        if analysis.get("tweet_id")
    }
    successful_tweets = [
        tweet for tweet in tweets if str(tweet.id) in successful_ids
    ]
    for tweet in successful_tweets:
        tweet.status = "analyzed"
    return successful_tweets


def _dispatch_analysis_indexing(analysis_result_ids: list[uuid.UUID]) -> None:
    from app.scheduler.tasks import embed_signal_task

    for analysis_result_id in analysis_result_ids:
        embed_signal_task.delay("analysis", str(analysis_result_id))


def _run_analysis(db: Session, tweets: list[Tweet], batch_id: uuid.UUID) -> dict:
    """实时分析链路：classify → analysis ‖ risk → merge → 写DB。

    预测由 Celery 后台任务异步完成，此处仅写入 analysis_results
    并标记 prediction_status='pending' 供后台任务消费。
    """
    all_analyses = []
    all_summaries = []
    analyzed_tweets = []
    overall_start = time.perf_counter()

    write_trace_immediate(
        conversation_id=batch_id,
        node_name="analysis_service",
        input={"tweet_count": len(tweets), "batch_size": BATCH_SIZE},
        status="initiated",
    )

    for i in range(0, len(tweets), BATCH_SIZE):
        batch_tweets = tweets[i:i + BATCH_SIZE]
        tweet_dicts = [
            {
                "id": str(t.id),
                "content": t.content,
                "author_handle": t.author_handle,
                "published_at": t.published_at,
            }
            for t in batch_tweets
        ]

        batch_start = time.perf_counter()
        try:
            state = supervisor.invoke({
                "tweets": tweet_dicts,
                "analyses": [],
                "ticker_summaries": [],
                "_trace_conv_id": str(batch_id),
            })
        except Exception as e:
            logger.error("Batch {}-{} supervisor failed: {}", i, i + len(batch_tweets), e)
            write_trace_immediate(
                conversation_id=batch_id,
                node_name="analysis_service",
                status="error",
                latency_ms=int((time.perf_counter() - batch_start) * 1000),
                error_detail=f"Batch {i}-{i+len(batch_tweets)}: {str(e)[:300]}",
            )
            continue

        # Upsert 分析结果：按 (tweet_id, analysis_type) 更新或插入
        analysis_result_ids: list[uuid.UUID] = []
        for analysis in state["analyses"]:
            tweet_id_str = analysis.pop("tweet_id")
            author = analysis.pop("author_handle")
            tid = uuid.UUID(tweet_id_str)

            existing = db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.tweet_id == tid,
                    AnalysisResult.analysis_type == "tweet_analysis",
                )
            ).scalar_one_or_none()

            if existing:
                existing.result = analysis
                existing.model_used = settings.signal_model
                existing.confidence = analysis.get("confidence", 0.0)
                existing.batch_id = batch_id
                existing.prediction_status = "pending"
                analysis_result_ids.append(existing.id)
                db.execute(
                    delete(Prediction).where(Prediction.tweet_id == tid)
                )
            else:
                analysis_result_id = uuid.uuid4()
                db.add(AnalysisResult(
                    id=analysis_result_id,
                    tweet_id=tid,
                    analysis_type="tweet_analysis",
                    result=analysis,
                    model_used=settings.signal_model,
                    confidence=analysis.get("confidence", 0.0),
                    batch_id=batch_id,
                    prediction_status="pending",
                ))
                analysis_result_ids.append(analysis_result_id)

            analysis["tweet_id"] = tweet_id_str
            analysis["author_handle"] = author

        for summary in state["ticker_summaries"]:
            ticker_symbol = summary.get("ticker", "")
            ref_tweet_id = batch_tweets[0].id

            existing_summary = db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.tweet_id == ref_tweet_id,
                    AnalysisResult.analysis_type == "ticker_summary",
                    AnalysisResult.result["ticker"].astext == ticker_symbol,
                )
            ).scalar_one_or_none()

            if existing_summary:
                existing_summary.result = summary
                existing_summary.model_used = settings.signal_model
                existing_summary.confidence = summary.get("recommendation_score", 0) / 100
                existing_summary.batch_id = batch_id
            else:
                db.add(AnalysisResult(
                    tweet_id=ref_tweet_id,
                    analysis_type="ticker_summary",
                    result=summary,
                    model_used=settings.signal_model,
                    confidence=summary.get("recommendation_score", 0) / 100,
                    batch_id=batch_id,
                    prediction_status="skipped",
                ))

        successful_batch_tweets = _mark_successful_tweets(
            batch_tweets, state["analyses"]
        )

        try:
            db.commit()
            logger.info("Batch {}-{} committed: {} analyses",
                        i, i + len(batch_tweets), len(state["analyses"]))
        except Exception as e:
            db.rollback()
            logger.error("Batch {}-{} commit failed: {}", i, i + len(batch_tweets), e)
            continue

        # 分析完成后异步触发向量化，将结构化分析结果入库到 public_signals collection
        _dispatch_analysis_indexing(analysis_result_ids)

        all_analyses.extend(state["analyses"])
        all_summaries.extend(state["ticker_summaries"])
        analyzed_tweets.extend(successful_batch_tweets)

    write_trace_immediate(
        conversation_id=batch_id,
        node_name="analysis_service",
        output={
            "analyzed": len(analyzed_tweets),
            "analyses_count": len(all_analyses),
            "summaries_count": len(all_summaries),
        },
        status="success",
        latency_ms=int((time.perf_counter() - overall_start) * 1000),
    )

    return {
        "batch_id": str(batch_id),
        "analyzed": len(analyzed_tweets),
        "analyses": all_analyses,
        "ticker_summaries": all_summaries,
    }
