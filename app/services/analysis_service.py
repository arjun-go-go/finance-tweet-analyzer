import time
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.agents.supervisor import supervisor
from app.core.config import settings
from app.models.analysis import AnalysisResult
from app.models.prediction import Prediction
from app.models.tweet import Tweet
from app.models.tweet_media_analysis import TweetMediaAnalysis
from app.services.instrument_resolver import resolve_analysis_tickers
from app.services.trace_service import write_trace_immediate

BATCH_SIZE = 10


def analysis_eligible_clause(now: datetime | None = None):
    """Return the SQL condition for analysis work that can run now."""
    current = now or datetime.now(timezone.utc)
    stale_before = current - timedelta(
        seconds=settings.analysis_processing_timeout_seconds
    )
    return or_(
        Tweet.status == "pending",
        and_(
            Tweet.status == "retrying",
            or_(
                Tweet.analysis_next_retry_at.is_(None),
                Tweet.analysis_next_retry_at <= current,
            ),
        ),
        and_(
            Tweet.status == "analyzing",
            or_(
                Tweet.analysis_started_at.is_(None),
                Tweet.analysis_started_at <= stale_before,
            ),
        ),
    )


def reset_analysis_state(tweet: Tweet) -> None:
    tweet.status = "pending"
    tweet.analysis_attempts = 0
    tweet.analysis_last_error = None
    tweet.analysis_next_retry_at = None
    tweet.analysis_started_at = None
    tweet.analysis_completed_at = None


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
    reset_analysis_state(tweet)
    db.commit()

    return _run_analysis(db, [tweet], batch_id)


def analyze_by_blogger(
    db: Session,
    blogger_handle: str,
    since: datetime | None = None,
) -> dict:
    batch_id = uuid.uuid4()

    query = select(Tweet).where(
            Tweet.author_handle == blogger_handle,
            analysis_eligible_clause(),
        )
    if since is not None:
        query = query.where(Tweet.published_at >= since)
    tweets = db.execute(
        query
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
            analysis_eligible_clause(),
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
        select(Tweet).where(analysis_eligible_clause()).limit(50)
    ).scalars().all()

    if not pending_tweets:
        return _empty_result(batch_id)

    return _run_analysis(db, pending_tweets, batch_id)


def _empty_result(batch_id: uuid.UUID) -> dict:
    return {
        "batch_id": str(batch_id),
        "analyzed": 0,
        "attempted": 0,
        "retrying": 0,
        "failed": 0,
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
        tweet.analysis_last_error = None
        tweet.analysis_next_retry_at = None
        tweet.analysis_started_at = None
        tweet.analysis_completed_at = datetime.now(timezone.utc)
    return successful_tweets


def _mark_analysis_started(tweets: list[Tweet]) -> None:
    started_at = datetime.now(timezone.utc)
    for tweet in tweets:
        tweet.status = "analyzing"
        tweet.analysis_attempts = (tweet.analysis_attempts or 0) + 1
        tweet.analysis_last_error = None
        tweet.analysis_next_retry_at = None
        tweet.analysis_started_at = started_at
        tweet.analysis_completed_at = None


def _mark_analysis_failed(
    tweets: list[Tweet],
    error: str,
) -> tuple[int, int]:
    """Move failed attempts to retrying or the terminal failed state."""
    retrying = 0
    failed = 0
    current = datetime.now(timezone.utc)
    error_text = error[:2000]
    for tweet in tweets:
        attempts = tweet.analysis_attempts or 1
        tweet.analysis_last_error = error_text
        tweet.analysis_started_at = None
        tweet.analysis_completed_at = None
        if attempts >= settings.analysis_max_attempts:
            tweet.status = "failed"
            tweet.analysis_next_retry_at = None
            failed += 1
            continue

        delay_seconds = min(
            settings.analysis_retry_base_seconds * (2 ** max(attempts - 1, 0)),
            settings.analysis_retry_max_seconds,
        )
        tweet.status = "retrying"
        tweet.analysis_next_retry_at = current + timedelta(seconds=delay_seconds)
        retrying += 1
    return retrying, failed


def _enqueue_analysis_indexing(db: Session, analysis_result_ids: list[uuid.UUID]) -> None:
    from app.services.outbox_service import enqueue_outbox_event
    for analysis_result_id in analysis_result_ids:
        enqueue_outbox_event(
            db,
            "analysis.index_requested",
            {"analysis_result_id": str(analysis_result_id)},
        )
        enqueue_outbox_event(
            db,
            "intelligence.project_requested",
            {"analysis_result_id": str(analysis_result_id)},
        )


def _run_analysis(db: Session, tweets: list[Tweet], batch_id: uuid.UUID) -> dict:
    """实时分析链路：classify → analysis ‖ risk → merge → 写DB。

    预测由 Celery 后台任务异步完成，此处仅写入 analysis_results
    并标记 prediction_status='pending' 供后台任务消费。
    """
    all_analyses = []
    all_summaries = []
    analyzed_tweets = []
    attempted_count = 0
    retrying_count = 0
    failed_count = 0
    overall_start = time.perf_counter()

    write_trace_immediate(
        conversation_id=batch_id,
        node_name="analysis_service",
        input={"tweet_count": len(tweets), "batch_size": BATCH_SIZE},
        status="initiated",
    )

    for i in range(0, len(tweets), BATCH_SIZE):
        batch_tweets = tweets[i:i + BATCH_SIZE]
        _mark_analysis_started(batch_tweets)
        db.commit()
        attempted_count += len(batch_tweets)
        media_rows = db.execute(
            select(TweetMediaAnalysis).where(
                TweetMediaAnalysis.tweet_id.in_([tweet.id for tweet in batch_tweets]),
                TweetMediaAnalysis.status == "completed",
            )
        ).scalars().all()
        media_context_by_tweet = {row.tweet_id: row.result for row in media_rows if row.result}
        tweet_dicts = [
            {
                "id": str(t.id),
                "content": t.content,
                "author_handle": t.author_handle,
                "published_at": t.published_at,
                "media_context": media_context_by_tweet.get(t.id),
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
            state["analyses"] = resolve_analysis_tickers(
                state.get("analyses", []), db=db
            )
        except Exception as e:
            logger.error("Batch {}-{} supervisor failed: {}", i, i + len(batch_tweets), e)
            retrying, failed = _mark_analysis_failed(
                batch_tweets,
                f"supervisor_failed: {e}",
            )
            retrying_count += retrying
            failed_count += failed
            db.commit()
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
        successful_ids = {tweet.id for tweet in successful_batch_tweets}
        missing_tweets = [
            tweet for tweet in batch_tweets if tweet.id not in successful_ids
        ]
        if missing_tweets:
            retrying, failed = _mark_analysis_failed(
                missing_tweets,
                "analysis_result_missing",
            )
            retrying_count += retrying
            failed_count += failed
        _enqueue_analysis_indexing(db, analysis_result_ids)

        try:
            db.commit()
            logger.info("Batch {}-{} committed: {} analyses",
                        i, i + len(batch_tweets), len(state["analyses"]))
        except Exception as e:
            db.rollback()
            logger.error("Batch {}-{} commit failed: {}", i, i + len(batch_tweets), e)
            continue

        # 分析完成后异步触发向量化，将结构化分析结果入库到 public_signals collection
        all_analyses.extend(state["analyses"])
        all_summaries.extend(state["ticker_summaries"])
        analyzed_tweets.extend(successful_batch_tweets)

    write_trace_immediate(
        conversation_id=batch_id,
        node_name="analysis_service",
        output={
            "analyzed": len(analyzed_tweets),
            "attempted": attempted_count,
            "retrying": retrying_count,
            "failed": failed_count,
            "analyses_count": len(all_analyses),
            "summaries_count": len(all_summaries),
        },
        status="success",
        latency_ms=int((time.perf_counter() - overall_start) * 1000),
    )

    return {
        "batch_id": str(batch_id),
        "analyzed": len(analyzed_tweets),
        "attempted": attempted_count,
        "retrying": retrying_count,
        "failed": failed_count,
        "analyses": all_analyses,
        "ticker_summaries": all_summaries,
    }
