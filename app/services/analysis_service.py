import json
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
from app.services.instrument_claim_service import (
    normalize_forecast_attribution,
    replace_analysis_claims,
    serialize_instrument_claim,
)
from app.services.instrument_resolver import resolve_analysis_claims
from app.services.commercial_attribution_service import normalize_commercial_attribution
from app.services.analysis_business_validator import (
    normalize_before_resolution,
    validate_after_resolution,
)
from app.services.trace_service import write_trace_immediate
from app.services.tweet_context_service import build_tweet_contexts
from app.services.tweet_state_service import (
    TweetProcessingState,
    transition_tweet_state,
)

BATCH_SIZE = 10


def analysis_eligible_clause(now: datetime | None = None):
    """Return the SQL condition for analysis work that can run now."""
    current = now or datetime.now(timezone.utc)
    stale_before = current - timedelta(
        seconds=settings.analysis_processing_timeout_seconds
    )
    return or_(
        Tweet.status == TweetProcessingState.ANALYSIS_PENDING.value,
        and_(
            Tweet.status == TweetProcessingState.RETRYING.value,
            or_(
                Tweet.analysis_next_retry_at.is_(None),
                Tweet.analysis_next_retry_at <= current,
            ),
        ),
        and_(
            Tweet.status == TweetProcessingState.ANALYZING.value,
            or_(
                Tweet.analysis_started_at.is_(None),
                Tweet.analysis_started_at <= stale_before,
            ),
        ),
    )


def reset_analysis_state(tweet: Tweet) -> None:
    transition_tweet_state(tweet, TweetProcessingState.ANALYSIS_PENDING)
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
            "claims_created": 0,
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
        "claims_created": 0,
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
        transition_tweet_state(tweet, TweetProcessingState.ANALYZED)
        tweet.analysis_last_error = None
        tweet.analysis_next_retry_at = None
        tweet.analysis_started_at = None
        tweet.analysis_completed_at = datetime.now(timezone.utc)
    return successful_tweets


def _mark_analysis_started(tweets: list[Tweet]) -> None:
    started_at = datetime.now(timezone.utc)
    for tweet in tweets:
        transition_tweet_state(tweet, TweetProcessingState.ANALYZING)
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
            transition_tweet_state(
                tweet,
                TweetProcessingState.FAILED,
                failure_stage="text_analysis",
                error=error_text,
            )
            tweet.analysis_next_retry_at = None
            failed += 1
            continue

        delay_seconds = min(
            settings.analysis_retry_base_seconds * (2 ** max(attempts - 1, 0)),
            settings.analysis_retry_max_seconds,
        )
        transition_tweet_state(
            tweet,
            TweetProcessingState.RETRYING,
            failure_stage="text_analysis",
            error=error_text,
        )
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
    total_claims = 0
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
        conversation_context_by_tweet = build_tweet_contexts(db, batch_tweets)
        tweet_dicts = [
            {
                "id": str(t.id),
                "content": t.content,
                "author_handle": t.author_handle,
                "published_at": t.published_at,
                "media_context": media_context_by_tweet.get(t.id),
                "conversation_context": conversation_context_by_tweet.get(t.id, {}),
            }
            for t in batch_tweets
        ]

        batch_start = time.perf_counter()
        try:
            state = supervisor.invoke({
                "tweets": tweet_dicts,
                "analyses": [],
                "_trace_conv_id": str(batch_id),
            })
            source_tweet_by_id = {
                str(tweet.id): tweet for tweet in batch_tweets
            }
            attribution_text_by_id = {
                str(tweet.id): "\n".join(
                    (
                        tweet.content,
                        json.dumps(
                            conversation_context_by_tweet.get(tweet.id, {}),
                            ensure_ascii=False,
                            default=str,
                        ),
                    )
                )
                for tweet in batch_tweets
            }
            normalized_analyses: list[dict] = []
            for analysis in state.get("analyses", []):
                analysis_tweet_id = str(analysis.get("tweet_id"))
                source_tweet = source_tweet_by_id.get(analysis_tweet_id)
                source_text = source_tweet.content if source_tweet else ""
                normalized = normalize_commercial_attribution(
                    normalize_forecast_attribution(
                        analysis,
                        attribution_text_by_id.get(analysis_tweet_id, ""),
                        source_tweet.published_at if source_tweet else None,
                    ),
                    source_text,
                )
                normalized_analyses.append(
                    normalize_before_resolution(
                        normalized,
                        source_text=source_text,
                    )
                )
            state["analyses"] = normalized_analyses
            state["analyses"] = resolve_analysis_claims(
                state.get("analyses", []), db=db
            )
            state["analyses"] = [
                validate_after_resolution(
                    analysis,
                    source_text=(
                        source_tweet_by_id[str(analysis.get("tweet_id"))].content
                        if str(analysis.get("tweet_id")) in source_tweet_by_id
                        else ""
                    ),
                )
                for analysis in state.get("analyses", [])
            ]
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
        persisted_analyses: list[dict] = []
        persisted_claim_count = 0
        for analysis_output in state["analyses"]:
            analysis = dict(analysis_output)
            tweet_id_str = str(analysis.pop("tweet_id"))
            author = str(analysis.pop("author_handle"))
            tid = uuid.UUID(tweet_id_str)
            analysis["analysis_schema_version"] = settings.user_analysis_pipeline_version
            final_model = str(
                (analysis.get("model_routing") or {}).get("final_model")
                or settings.signal_model
            )

            existing = db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.tweet_id == tid,
                    AnalysisResult.analysis_type == "tweet_analysis",
                )
            ).scalar_one_or_none()

            if existing:
                existing.result = analysis
                existing.model_used = final_model
                existing.confidence = analysis.get("confidence", 0.0)
                existing.batch_id = batch_id
                existing.prediction_status = "pending"
                existing.prediction_decision = None
                existing.pipeline_version = settings.user_analysis_pipeline_version
                analysis_result = existing
            else:
                analysis_result_id = uuid.uuid4()
                analysis_result = AnalysisResult(
                    id=analysis_result_id,
                    tweet_id=tid,
                    analysis_type="tweet_analysis",
                    result=analysis,
                    model_used=final_model,
                    confidence=analysis.get("confidence", 0.0),
                    batch_id=batch_id,
                    prediction_status="pending",
                    pipeline_version=settings.user_analysis_pipeline_version,
                )
                db.add(analysis_result)

            db.flush()
            db.execute(delete(Prediction).where(Prediction.tweet_id == tid))
            claim_records = replace_analysis_claims(
                db,
                analysis_result.id,
                analysis,
            )
            analysis_result_ids.append(analysis_result.id)
            persisted_claim_count += len(claim_records)
            persisted_analyses.append(
                {
                    **analysis,
                    "tweet_id": tweet_id_str,
                    "author_handle": author,
                    "claims": [
                        serialize_instrument_claim(claim) for claim in claim_records
                    ],
                }
            )

        state["analyses"] = persisted_analyses

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
            logger.info(
                "Batch {}-{} committed: {} analyses / {} claims",
                i,
                i + len(batch_tweets),
                len(state["analyses"]),
                persisted_claim_count,
            )
        except Exception as e:
            db.rollback()
            logger.error("Batch {}-{} commit failed: {}", i, i + len(batch_tweets), e)
            continue

        # 分析完成后异步触发向量化，将结构化分析结果入库到 public_signals collection
        all_analyses.extend(state["analyses"])
        total_claims += persisted_claim_count
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
            "claims_count": total_claims,
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
        "claims_created": total_claims,
    }
