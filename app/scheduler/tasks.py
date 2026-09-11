"""Celery 任务定义 —— 自动分析 + 预测批量生成。

任务特性：
- bind=True：访问 self（用于重试）
- autoretry_for：LLM 调用失败自动重试
- max_retries=3 + exponential backoff
- acks_late=True：Worker 挂掉后任务重新投递
"""
from celery import shared_task
from celery.utils.log import get_task_logger
import sqlalchemy as sa
from sqlalchemy import select, update
from uuid import UUID

from app.core.deps import SessionLocal
from app.models.analysis import AnalysisResult
from app.models.content_chunk import ContentChunk
from app.models.index_job import IndexJob
from app.models.tweet import Tweet
from app.scheduler.locks import (
    try_acquire,
    release,
    try_acquire_prediction_lock,
    release_prediction_lock,
    try_acquire_fetch_lock,
    release_fetch_lock,
)
from app.services.tweet_state_service import (
    ANALYSIS_READY_STATES,
    TweetProcessingState,
    transition_tweet_state,
)

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="app.scheduler.tasks.analyze_tweet_task",
    acks_late=True,
)
def analyze_tweet_task(self, tweet_id: str) -> dict:
    """Run the text and media-fused analysis for one ready tweet."""
    from app.services.analysis_service import analyze_single_tweet

    db = SessionLocal()
    try:
        tweet = db.get(Tweet, UUID(tweet_id))
        if tweet is None:
            return {"tweet_id": tweet_id, "status": "skipped", "reason": "not_found"}
        if tweet.status == "analyzed":
            return {"tweet_id": tweet_id, "status": "skipped", "reason": "already_analyzed"}
        if TweetProcessingState(tweet.status) not in ANALYSIS_READY_STATES:
            return {
                "tweet_id": tweet_id,
                "status": "skipped",
                "reason": f"not_analysis_ready:{tweet.status}",
            }
        return analyze_single_tweet(db, tweet_id)
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.analyze_tweet_media_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def analyze_tweet_media_task(self, tweet_id: str) -> dict:
    """Extract structured evidence from a tweet and all archived images."""
    from app.services.tweet_media_analysis_service import analyze_tweet_media

    db = SessionLocal()
    try:
        return analyze_tweet_media(db, tweet_id)
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.archive_tweet_media_task",
    acks_late=True,
)
def archive_tweet_media_task(self, tweet_id: str) -> dict:
    """Download and archive one tweet's original images to object storage."""
    from app.services.tweet_media_service import archive_tweet_media

    db = SessionLocal()
    try:
        return archive_tweet_media(db, tweet_id)
    except Exception as exc:
        db.rollback()
        tweet = db.get(Tweet, UUID(tweet_id))
        if tweet is not None:
            transition_tweet_state(
                tweet,
                TweetProcessingState.FAILED,
                failure_stage="media_archive",
                error=str(exc),
            )
            db.commit()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.project_intelligence_event_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def project_intelligence_event_task(self, analysis_result_id: str) -> dict:
    """Idempotently project one analysis result into the intelligence event store."""
    from app.services.intelligence_projection_service import project_analysis_to_intelligence_event

    db = SessionLocal()
    try:
        result = project_analysis_to_intelligence_event(db, analysis_result_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.backfill_intelligence_events_task",
    acks_late=True,
)
def backfill_intelligence_events_task(self) -> dict:
    """Backfill or refresh persistent intelligence events from historical analyses."""
    from app.services.intelligence_projection_service import backfill_intelligence_events

    db = SessionLocal()
    try:
        return backfill_intelligence_events(db)
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.dispatch_outbox_events_task",
    acks_late=True,
    ignore_result=True,
)
def dispatch_outbox_events_task(self, batch_size: int | None = None) -> dict:
    from datetime import datetime, timezone

    from app.core.config import settings as cfg
    from app.scheduler.locks import _get_redis
    from app.services.outbox_service import dispatch_pending_outbox_events

    db = SessionLocal()
    try:
        result = dispatch_pending_outbox_events(
            db,
            send_task=self.app.send_task,
            batch_size=batch_size,
        )
        _get_redis().setex(
            "health:celery_pipeline",
            cfg.celery_pipeline_heartbeat_ttl_seconds,
            datetime.now(timezone.utc).isoformat(),
        )
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _record_index_jobs(
    db,
    chunks,
    *,
    target: str,
    status: str,
    attempts: int,
    error_message: str | None = None,
) -> None:
    if db is None:
        return
    for chunk in chunks:
        previous_attempts = 0
        if hasattr(db, "get"):
            existing = db.get(IndexJob, {"content_chunk_id": chunk.id, "target": target})
            previous_attempts = getattr(existing, "attempts", 0) if existing else 0
        db.merge(
            IndexJob(
                content_chunk_id=chunk.id,
                target=target,
                status=status,
                attempts=previous_attempts + attempts,
                error_message=error_message,
            )
        )
    if hasattr(db, "flush"):
        db.flush()


def _best_effort_upsert_es_chunks(chunks, db=None) -> dict:
    """Best-effort Elasticsearch upsert for ContentChunk-like rows."""
    from app.rag.keyword_store import chunk_to_es_document, get_keyword_store

    chunk_list = list(chunks or [])
    stats = {"attempted": len(chunk_list), "indexed": 0, "errors": 0}
    if not chunk_list:
        return stats
    try:
        docs = [chunk_to_es_document(chunk) for chunk in chunk_list]
        indexed, errors = get_keyword_store().bulk_upsert_documents(docs)
        stats["indexed"] = int(indexed or 0)
        stats["errors"] = len(errors or [])
        if stats["errors"]:
            _record_index_jobs(
                db,
                chunk_list,
                target="elasticsearch",
                status="failed",
                attempts=1,
                error_message=str(errors[:3]),
            )
        else:
            _record_index_jobs(db, chunk_list, target="elasticsearch", status="success", attempts=1)
    except Exception as exc:
        stats["errors"] = len(chunk_list)
        _record_index_jobs(
            db,
            chunk_list,
            target="elasticsearch",
            status="failed",
            attempts=1,
            error_message=str(exc)[:1000],
        )
        logger.warning("[Celery] Elasticsearch chunk upsert skipped: %s", exc)
    return stats


def _upsert_es_chunks_to_index(chunks, *, index_name: str) -> dict:
    from app.rag.keyword_store import chunk_to_es_document, get_keyword_store

    chunk_list = list(chunks or [])
    stats = {"attempted": len(chunk_list), "indexed": 0, "errors": 0}
    if not chunk_list:
        return stats
    try:
        docs = [chunk_to_es_document(chunk) for chunk in chunk_list]
        indexed, errors = get_keyword_store().bulk_upsert_documents_to_index(
            docs,
            index_name=index_name,
        )
        stats["indexed"] = int(indexed or 0)
        stats["errors"] = len(errors or [])
    except Exception as exc:
        stats["errors"] = len(chunk_list)
        logger.warning("[Celery] Elasticsearch version index upsert failed: %s", exc)
    return stats


def _delete_existing_source_chunks(db, source_type: str, source_id: str) -> dict:
    """Delete old PG/ES chunks for a source before rewriting it."""
    from app.rag.keyword_store import get_keyword_store

    stats = {"pg_deleted": 0, "es_deleted": 0}
    existing_chunks = db.execute(
        select(ContentChunk).where(
            ContentChunk.source_type == source_type,
            ContentChunk.source_id == str(source_id),
        )
    ).scalars().all()
    for chunk in existing_chunks:
        db.delete(chunk)
        stats["pg_deleted"] += 1

    try:
        result = get_keyword_store().delete_by_source(source_type, source_id)
        stats["es_deleted"] = int(result.get("deleted") or 0)
    except Exception as exc:
        logger.warning(
            "[Celery] Elasticsearch source cleanup skipped for %s:%s: %s",
            source_type,
            source_id,
            exc,
        )
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.auto_analysis_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def auto_analysis_task(self) -> dict:
    """扫描所有有 pending 推文的博主，逐个触发分析流水线。

    Redis 分布式锁确保同一博主不会被多个 Worker 重复分析。
    """
    from app.services.analysis_service import analysis_eligible_clause, analyze_by_blogger

    logger.info("[Celery] Auto-analysis task started")

    db = SessionLocal()
    stats = {
        "total_bloggers": 0,
        "attempted": 0,
        "analyzed": 0,
        "retrying": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }

    try:
        handles = [
            row[0]
            for row in db.execute(
                select(Tweet.author_handle)
                .where(analysis_eligible_clause())
                .group_by(Tweet.author_handle)
            ).all()
        ]

        if not handles:
            logger.info("[Celery] No bloggers with pending tweets")
            return stats

        stats["total_bloggers"] = len(handles)
        logger.info("[Celery] Found %d bloggers with pending tweets", len(handles))

        for handle in handles:
            acquired, lock_token = try_acquire(handle)
            if not acquired:
                logger.info("[Celery] Skipping %s — locked by another worker", handle)
                stats["skipped"] += 1
                continue
            try:
                logger.info("[Celery] Analyzing: %s", handle)
                result = analyze_by_blogger(db, handle)
                logger.info(
                    "[Celery] Done %s: analyzed=%d",
                    handle, result["analyzed"],
                )
                stats["attempted"] += result.get("attempted", 0)
                stats["analyzed"] += result.get("analyzed", 0)
                stats["retrying"] += result.get("retrying", 0)
                stats["failed"] += result.get("failed", 0)
            except Exception as e:
                logger.error("[Celery] Error analyzing %s: %s", handle, e)
                stats["errors"] += 1
            finally:
                release(handle, lock_token)

    except Exception as e:
        logger.error("[Celery] Unexpected error in auto_analysis: %s", e)
        raise
    finally:
        db.close()

    logger.info("[Celery] Auto-analysis completed: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.auto_verify_predictions_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,
)
def auto_verify_predictions_task(self, batch_size: int | None = None) -> dict:
    """Verify due predictions with their dedicated public-data verifier."""
    from app.services.market_verification_service import (
        record_auto_verification_runtime,
    )
    from app.services.prediction_verification_service import (
        run_due_prediction_verifications,
    )

    task_id = str(self.request.id or "")
    record_auto_verification_runtime("running", task_id=task_id)
    db = SessionLocal()
    try:
        result = run_due_prediction_verifications(db, batch_size=batch_size)
        record_auto_verification_runtime("success", task_id=task_id, result=result)
        return result
    except Exception as error:
        db.rollback()
        record_auto_verification_runtime("failed", task_id=task_id, error=str(error))
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.prediction_batch_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def prediction_batch_task(self) -> dict:
    """扫描 prediction_status='pending' 的分析结果，批量生成预测。

    全局分布式锁确保同一时刻只有一个 Worker 执行预测批处理。
    """
    logger.info("[Celery] Prediction batch task started")

    acquired, pred_token = try_acquire_prediction_lock()
    if not acquired:
        logger.info("[Celery] Prediction lock held by another worker, skipping")
        return {"status": "skipped"}

    db = SessionLocal()
    stats = {"processed": 0, "predictions_created": 0, "errors": 0}

    try:
        pending_analyses = db.execute(
            select(AnalysisResult)
            .where(
                AnalysisResult.analysis_type == "tweet_analysis",
                AnalysisResult.prediction_status == "pending",
            )
            .order_by(AnalysisResult.created_at.asc())
            .limit(50)
        ).scalars().all()

        if not pending_analyses:
            logger.info("[Celery] No pending analyses for prediction")
            return stats

        logger.info("[Celery] Found %d analyses awaiting prediction", len(pending_analyses))

        from app.agents.prediction_agent import (
            PREDICTION_RULE_VERSION,
            evaluate_prediction_eligibility,
            prediction_agent_node,
        )
        from app.models.instrument_claim import InstrumentClaim
        from app.models.tweet import Tweet as TweetModel
        from app.services.instrument_claim_service import serialize_instrument_claim

        tweet_ids = [ar.tweet_id for ar in pending_analyses]
        tweet_rows = db.execute(
            select(TweetModel).where(TweetModel.id.in_(tweet_ids))
        ).scalars().all()
        tweet_map = {t.id: t for t in tweet_rows}
        claim_rows = db.execute(
            select(InstrumentClaim)
            .where(
                InstrumentClaim.analysis_result_id.in_(
                    [analysis.id for analysis in pending_analyses]
                )
            )
            .order_by(
                InstrumentClaim.analysis_result_id,
                InstrumentClaim.claim_index,
            )
        ).scalars().all()
        claims_by_analysis: dict = {}
        for claim in claim_rows:
            claims_by_analysis.setdefault(claim.analysis_result_id, []).append(claim)

        claims_for_prediction = []
        processed_ids = []
        for ar in pending_analyses:
            result_data = dict(ar.result or {})
            tweet = tweet_map.get(ar.tweet_id)
            if tweet is None:
                ar.prediction_status = "skipped"
                ar.prediction_decision = {
                    "rule_version": PREDICTION_RULE_VERSION,
                    "eligible": False,
                    "reason_codes": ["tweet_not_found"],
                }
                continue
            tweet_payload = {
                "id": str(tweet.id),
                "published_at": tweet.published_at,
                "author_handle": tweet.author_handle,
                "tweet_type": tweet.tweet_type or "original",
            }
            serialized_claims = [
                serialize_instrument_claim(claim)
                for claim in claims_by_analysis.get(ar.id, [])
            ]
            decision = evaluate_prediction_eligibility(
                result_data,
                tweet_payload,
                serialized_claims,
            )
            ar.prediction_decision = decision
            if not decision["eligible"]:
                ar.prediction_status = "skipped"
                continue
            processed_ids.append(ar.id)
            for claim in serialized_claims:
                claims_for_prediction.append(
                    {
                        **claim,
                        "tweet_id": str(tweet.id),
                        "blogger_handle": tweet.author_handle,
                        "published_at": tweet.published_at,
                        "tweet_type": tweet.tweet_type or "original",
                        "is_investment_relevant": result_data.get(
                            "is_investment_relevant",
                            result_data.get("is_investment_related", False),
                        ),
                        "is_investment_related": result_data.get(
                            "is_investment_related", False
                        ),
                        "has_commercial_content": result_data.get(
                            "is_sponsored", False
                        ),
                    }
                )

        if claims_for_prediction:
            try:
                pred_result = prediction_agent_node({
                    "claims": claims_for_prediction,
                })
                predictions = pred_result.get("predictions", [])

                from app.services.prediction_service import save_predictions_batch
                stats["predictions_created"] = save_predictions_batch(db, predictions)

                candidate_counts: dict[str, int] = {}
                for prediction in predictions:
                    key = str(prediction.get("analysis_id") or "")
                    candidate_counts[key] = candidate_counts.get(key, 0) + 1
                for ar in pending_analyses:
                    if ar.prediction_status == "skipped" or not ar.prediction_decision:
                        continue
                    ar.prediction_decision = {
                        **ar.prediction_decision,
                        "candidate_count": candidate_counts.get(str(ar.id), 0),
                    }
                if processed_ids:
                    db.execute(
                        update(AnalysisResult)
                        .where(AnalysisResult.id.in_(processed_ids))
                        .values(prediction_status="done")
                    )
            except Exception as e:
                logger.error("[Celery] Prediction generation failed: %s", e)
                stats["errors"] += 1
                failed_ids = [ar.id for ar in pending_analyses if ar.prediction_status != "skipped"]
                if failed_ids:
                    db.execute(
                        update(AnalysisResult)
                        .where(AnalysisResult.id.in_(failed_ids))
                        .values(prediction_status="failed")
                    )

        db.commit()
        stats["processed"] = len(pending_analyses)

    except Exception as e:
        db.rollback()
        logger.error("[Celery] Prediction batch error: %s", e)
        raise
    finally:
        db.close()
        release_prediction_lock(pred_token)

    logger.info("[Celery] Prediction batch completed: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.embed_signal_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def embed_signal_task(self, source_type: str, source_id: str) -> dict:
    """Index raw tweets or canonical per-instrument claims into public signals."""
    from hashlib import sha256
    from uuid import UUID

    from app.core.config import settings
    from app.models.content_chunk import ContentChunk
    from app.models.instrument_claim import InstrumentClaim
    from app.rag.chunking import chunk_analysis, chunk_tweet
    from app.rag.embeddings import get_embedder
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    try:
        specs: list[dict] = []
        cleanup_targets: set[tuple[str, str]] = set()
        old_vector_ids: list[str] = []
        if source_type == "tweet":
            tweet = db.get(Tweet, UUID(source_id))
            if not tweet or not tweet.content:
                return {"skipped": True}
            from app.services.commercial_attribution_service import (
                detect_commercial_disclosure,
            )

            commercial_disclosure = detect_commercial_disclosure(tweet.content)
            cleanup_targets.add(("tweet", str(tweet.id)))
            specs.append(
                {
                    "source_type": "tweet",
                    "source_id": str(tweet.id),
                    "index_stage": "raw",
                    "chunks": chunk_tweet(tweet.content),
                    "metadata": {
                        "blogger_handle": tweet.author_handle,
                        "published_at": (
                            tweet.published_at.isoformat()
                            if tweet.published_at
                            else ""
                        ),
                        "ticker": "",
                        "direction": "none",
                        "sentiment": "none",
                        "horizon": "unknown",
                        "has_commercial_content": bool(
                            commercial_disclosure.get("has_commercial_content")
                        ),
                        "sponsor_name": str(
                            commercial_disclosure.get("sponsor_name") or ""
                        ),
                        "sponsor_handle": str(
                            commercial_disclosure.get("sponsor_handle") or ""
                        ),
                        "commercial_placement": str(
                            commercial_disclosure.get("placement") or "none"
                        ),
                    },
                }
            )
        elif source_type == "analysis":
            analysis = db.get(AnalysisResult, UUID(source_id))
            if not analysis or not analysis.result:
                return {"skipped": True}
            result_data = analysis.result
            tweet = db.get(Tweet, analysis.tweet_id)
            cleanup_targets.add(("analysis", str(analysis.id)))
            old_claim_chunks = list(
                db.execute(
                    select(ContentChunk).where(
                        ContentChunk.source_type == "claim",
                        ContentChunk.metadata_["parent_analysis_id"].astext
                        == str(analysis.id),
                    )
                ).scalars()
            )
            cleanup_targets.update(
                ("claim", chunk.source_id) for chunk in old_claim_chunks
            )

            claims = list(
                db.execute(
                    select(InstrumentClaim)
                    .where(
                        InstrumentClaim.analysis_result_id == analysis.id,
                        InstrumentClaim.downstream_eligible.is_(True),
                    )
                    .order_by(InstrumentClaim.claim_index)
                ).scalars()
            )
            for claim in claims:
                parts = [
                    f"标的：{claim.instrument_symbol}",
                    f"观点方向：{claim.direction}",
                    f"投资周期：{claim.horizon}",
                    f"观点类型：{claim.claim_type}",
                    f"观点归属：{claim.opinion_source}",
                ]
                if claim.thesis:
                    parts.append("核心论点：" + claim.thesis)
                if claim.evidence:
                    parts.append("正文证据：" + "；".join(claim.evidence))
                if claim.media_evidence:
                    parts.append("图片证据：" + "；".join(claim.media_evidence))
                if claim.catalysts:
                    parts.append("催化因素：" + "；".join(claim.catalysts))
                if claim.risk_factors:
                    parts.append("风险：" + "；".join(claim.risk_factors))
                if claim.entry_conditions:
                    parts.append("触发条件：" + "；".join(claim.entry_conditions))
                if claim.invalidation_conditions:
                    parts.append(
                        "失效条件：" + "；".join(claim.invalidation_conditions)
                    )
                if result_data.get("tweet_summary"):
                    parts.append("推文背景：" + str(result_data["tweet_summary"]))
                content = "\n".join(parts)
                specs.append(
                    {
                        "source_type": "claim",
                        "source_id": str(claim.id),
                        "index_stage": "claim",
                        "chunks": chunk_analysis(
                            content,
                            settings.chunk_size_analysis,
                        ),
                        "metadata": {
                            "parent_analysis_id": str(analysis.id),
                            "parent_tweet_id": str(analysis.tweet_id),
                            "blogger_handle": tweet.author_handle if tweet else "",
                            "published_at": (
                                tweet.published_at.isoformat()
                                if tweet and tweet.published_at
                                else ""
                            ),
                            "ticker": claim.instrument_symbol,
                            "direction": claim.direction,
                            "sentiment": claim.direction,
                            "horizon": claim.horizon,
                            "claim_type": claim.claim_type,
                            "opinion_source": claim.opinion_source,
                            "claim_confidence": claim.confidence,
                            "downstream_eligible": True,
                            "has_commercial_content": bool(
                                result_data.get("is_sponsored")
                            ),
                            "sponsor_name": str(
                                (
                                    result_data.get("commercial_disclosure")
                                    or {}
                                ).get("sponsor_name")
                                or ""
                            ),
                            "sponsor_handle": str(
                                (
                                    result_data.get("commercial_disclosure")
                                    or {}
                                ).get("sponsor_handle")
                                or ""
                            ),
                            "sponsor_relation": claim.sponsor_relation,
                            "performance_eligible": claim.performance_eligible,
                            "performance_exclusion_reason": (
                                claim.performance_exclusion_reason or ""
                            ),
                        },
                    }
                )
        else:
            return {"error": f"Unknown source_type: {source_type}"}

        for cleanup_type, cleanup_id in cleanup_targets:
            existing_chunks = db.execute(
                select(ContentChunk).where(
                    ContentChunk.source_type == cleanup_type,
                    ContentChunk.source_id == cleanup_id,
                )
            ).scalars().all()
            old_vector_ids.extend(
                chunk.vector_id for chunk in existing_chunks if chunk.vector_id
            )
        cleanup_stats = {"pg_deleted": 0, "es_deleted": 0, "milvus_deleted": 0}
        for cleanup_type, cleanup_id in cleanup_targets:
            result = _delete_existing_source_chunks(
                db,
                cleanup_type,
                cleanup_id,
            )
            cleanup_stats["pg_deleted"] += result["pg_deleted"]
            cleanup_stats["es_deleted"] += result["es_deleted"]

        vs = None
        if old_vector_ids:
            try:
                vs = get_vector_store()
                vs.delete("public_signals", old_vector_ids)
                cleanup_stats["milvus_deleted"] = len(old_vector_ids)
            except Exception as exc:
                logger.warning("[Celery] Milvus source cleanup skipped: %s", exc)

        entries = [
            {
                **spec,
                "chunk_index": index,
                "content": chunk_text,
            }
            for spec in specs
            for index, chunk_text in enumerate(spec["chunks"])
            if chunk_text
        ]
        if not entries:
            db.commit()
            return {
                "skipped": True,
                "reason": "no eligible claim content",
                "cleanup": cleanup_stats,
            }

        SHORT_TEXT_THRESHOLD = 100
        embed_texts = []
        for entry in entries:
            chunk_text = entry["content"]
            metadata = entry["metadata"]
            if len(chunk_text) <= SHORT_TEXT_THRESHOLD and entry["source_type"] == "tweet":
                prefix_parts = []
                if metadata.get("blogger_handle"):
                    prefix_parts.append(f"@{metadata['blogger_handle']}")
                if metadata.get("published_at"):
                    prefix_parts.append(metadata["published_at"][:10])
                prefix = " ".join(prefix_parts)
                embed_texts.append(f"[{prefix}] {chunk_text}" if prefix else chunk_text)
            else:
                embed_texts.append(chunk_text)

        vs = vs or get_vector_store()
        embedder = get_embedder()
        vectors = embedder.embed_documents(embed_texts)
        rows_to_index = []
        for entry in entries:
            chunk_text = entry["content"]
            content_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
            row_source_type = str(entry["source_type"])
            row_source_id = str(entry["source_id"])
            chunk_index = int(entry["chunk_index"])
            vector_id = f"{row_source_type}:{row_source_id}:{chunk_index}"
            row = ContentChunk(
                source_type=row_source_type,
                source_id=row_source_id,
                index_stage=str(entry["index_stage"]),
                chunk_index=chunk_index,
                content=chunk_text,
                content_hash=content_hash,
                char_count=len(chunk_text),
                metadata_=entry["metadata"],
                vector_id=vector_id,
            )
            db.add(row)
            rows_to_index.append(row)

        db.flush()
        _record_index_jobs(db, rows_to_index, target="milvus", status="pending", attempts=0)
        _record_index_jobs(db, rows_to_index, target="elasticsearch", status="pending", attempts=0)
        db.commit()

        milvus_error = None
        try:
            for row, vec in zip(rows_to_index, vectors):
                vector_metadata = {
                    **row.metadata_,
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "index_stage": row.index_stage,
                }
                vs.add(
                    "public_signals",
                    ids=[row.vector_id],
                    texts=[row.content],
                    embeddings=[vec],
                    metadatas=[vector_metadata],
                )
            _record_index_jobs(
                db,
                rows_to_index,
                target="milvus",
                status="success",
                attempts=1,
            )
        except Exception as exc:
            milvus_error = str(exc)[:1000]
            _record_index_jobs(
                db,
                rows_to_index,
                target="milvus",
                status="failed",
                attempts=1,
                error_message=milvus_error,
            )

        es_stats = _best_effort_upsert_es_chunks(rows_to_index, db=db)
        db.commit()
        return {
            "source_type": source_type,
            "source_id": source_id,
            "indexed": len(rows_to_index),
            "indexed_claims": len(
                {
                    row.source_id
                    for row in rows_to_index
                    if row.source_type == "claim"
                }
            ),
            "cleanup": cleanup_stats,
            "milvus": {"errors": len(rows_to_index) if milvus_error else 0},
            "es": es_stats,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.backfill_signals_task",
    acks_late=True,
)
def backfill_signals_task(self, batch_size: int = 100) -> dict:
    """回填历史原始推文的向量化。

    扫描有正文但尚未在 content_chunks 中有 source_type='tweet' 记录的推文，
    分批 dispatch embed_signal_task 避免队列积压。

    可通过 Celery Beat 定期执行，也可手动触发：
      backfill_signals_task.delay(batch_size=200)
    """
    from app.models.content_chunk import ContentChunk

    db = SessionLocal()
    stats = {"dispatched": 0, "already_indexed": 0}
    try:
        # 找出所有有正文但未向量化的推文
        # 子查询：已有 tweet 类型 content_chunk 的 source_id 集合
        indexed_subq = (
            select(ContentChunk.source_id)
            .where(ContentChunk.source_type == "tweet")
            .scalar_subquery()
        )

        pending_tweets = db.execute(
            select(Tweet)
            .where(
                Tweet.content.is_not(None),
                Tweet.id.cast(sa.String).not_in(indexed_subq),
            )
            .order_by(Tweet.published_at.desc())
            .limit(batch_size)
        ).scalars().all()

        for tweet in pending_tweets:
            embed_signal_task.delay("tweet", str(tweet.id))
            stats["dispatched"] += 1

    finally:
        db.close()

    logger.info("[Celery] backfill_signals: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.backfill_analysis_signals_task",
    acks_late=True,
)
def backfill_analysis_signals_task(self, batch_size: int = 100) -> dict:
    """回填历史逐标的观点的向量化。

    找出仍有已核验 claim 未进入 content_chunks 的分析结果，按分析批量重建。

    手动触发：
      backfill_analysis_signals_task.delay(batch_size=200)
    """
    from app.models.content_chunk import ContentChunk

    db = SessionLocal()
    stats = {"dispatched": 0}
    try:
        from app.models.instrument_claim import InstrumentClaim

        indexed_subq = (
            select(ContentChunk.source_id)
            .where(ContentChunk.source_type == "claim")
            .scalar_subquery()
        )

        pending = db.execute(
            select(AnalysisResult)
            .join(
                InstrumentClaim,
                InstrumentClaim.analysis_result_id == AnalysisResult.id,
            )
            .where(
                AnalysisResult.analysis_type == "tweet_analysis",
                InstrumentClaim.downstream_eligible.is_(True),
                InstrumentClaim.id.cast(sa.String).not_in(indexed_subq),
            )
            .distinct()
            .order_by(AnalysisResult.created_at.desc())
            .limit(batch_size)
        ).scalars().all()

        for ar in pending:
            embed_signal_task.delay("analysis", str(ar.id))
            stats["dispatched"] += 1

    finally:
        db.close()

    logger.info("[Celery] backfill_analysis_signals: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.reindex_elasticsearch_chunks_task",
    acks_late=True,
)
def reindex_elasticsearch_chunks_task(
    self,
    batch_size: int = 500,
    source_type: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Reindex existing content_chunks into the approved Elasticsearch RAG index."""
    db = SessionLocal()
    stats = {"scanned": 0, "attempted": 0, "indexed": 0, "errors": 0, "dry_run": dry_run}
    try:
        stmt = select(ContentChunk).order_by(
            ContentChunk.created_at.asc(), ContentChunk.id.asc()
        ).limit(batch_size)
        if source_type:
            stmt = stmt.where(ContentChunk.source_type == source_type)

        rows = list(db.execute(stmt).scalars())
        stats["scanned"] = len(rows)
        if dry_run or not rows:
            return stats

        result = _best_effort_upsert_es_chunks(rows, db=db)
        stats["attempted"] += result["attempted"]
        stats["indexed"] += result["indexed"]
        stats["errors"] += result["errors"]

        db.commit()
        return stats
    finally:
        db.close()


def _retry_milvus_chunk(db, chunk: ContentChunk) -> None:
    from app.rag.embeddings import get_embedder
    from app.rag.vector_store import get_vector_store

    metadata = {
        **dict(chunk.metadata_ or {}),
        "source_type": chunk.source_type,
        "source_id": chunk.source_id,
        "index_stage": chunk.index_stage,
        "chunk_index": chunk.chunk_index,
    }
    collection = "public_signals"
    vector_id = chunk.vector_id or f"{chunk.source_type}:{chunk.source_id}:{chunk.chunk_index}"

    vector = get_embedder().embed_documents([chunk.content])[0]
    get_vector_store().add(
        collection,
        ids=[vector_id],
        texts=[chunk.content],
        embeddings=[vector],
        metadatas=[metadata],
    )
    chunk.vector_id = vector_id


@shared_task(
    bind=True,
    name="app.scheduler.tasks.retry_failed_index_jobs_task",
    acks_late=True,
)
def retry_failed_index_jobs_task(
    self,
    batch_size: int = 200,
    target: str | None = None,
) -> dict:
    """Retry pending/failed Elasticsearch and Milvus projection jobs."""
    db = SessionLocal()
    stats = {
        "scanned": 0,
        "attempted": 0,
        "indexed": 0,
        "errors": 0,
        "missing_chunks": 0,
        "targets": {},
    }
    try:
        stmt = select(IndexJob).where(IndexJob.status.in_(["pending", "failed"]))
        if target:
            stmt = stmt.where(IndexJob.target == target)
        jobs = db.execute(
            stmt.order_by(IndexJob.updated_at.asc()).limit(batch_size)
        ).scalars().all()
        stats["scanned"] = len(jobs)

        for job in jobs:
            target_stats = stats["targets"].setdefault(
                job.target,
                {"attempted": 0, "indexed": 0, "errors": 0},
            )
            chunk = db.get(ContentChunk, job.content_chunk_id)
            if not chunk:
                job.status = "failed"
                job.error_message = "content_chunk missing"
                job.attempts = (job.attempts or 0) + 1
                stats["missing_chunks"] += 1
                continue

            stats["attempted"] += 1
            target_stats["attempted"] += 1
            if job.target == "elasticsearch":
                result = _best_effort_upsert_es_chunks([chunk], db=db)
                stats["indexed"] += result["indexed"]
                stats["errors"] += result["errors"]
                target_stats["indexed"] += result["indexed"]
                target_stats["errors"] += result["errors"]
            elif job.target == "milvus":
                try:
                    _retry_milvus_chunk(db, chunk)
                    _record_index_jobs(
                        db,
                        [chunk],
                        target="milvus",
                        status="success",
                        attempts=1,
                    )
                    stats["indexed"] += 1
                    target_stats["indexed"] += 1
                except Exception as exc:
                    _record_index_jobs(
                        db,
                        [chunk],
                        target="milvus",
                        status="failed",
                        attempts=1,
                        error_message=str(exc)[:1000],
                    )
                    stats["errors"] += 1
                    target_stats["errors"] += 1
            else:
                job.status = "failed"
                job.error_message = f"unsupported index target: {job.target}"
                job.attempts = (job.attempts or 0) + 1
                stats["errors"] += 1
                target_stats["errors"] += 1

        db.commit()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.reconcile_index_jobs_task",
    acks_late=True,
)
def reconcile_index_jobs_task(self, batch_size: int = 1000) -> dict:
    """Create missing ES/Milvus projection jobs and report storage count drift."""
    from app.rag.keyword_store import get_keyword_store
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    stats = {
        "content_chunks": 0,
        "created_jobs": {"elasticsearch": 0, "milvus": 0},
        "elasticsearch_docs": None,
        "milvus_vectors": None,
    }
    try:
        stats["content_chunks"] = int(
            db.execute(select(sa.func.count()).select_from(ContentChunk)).scalar() or 0
        )
        for target in ("elasticsearch", "milvus"):
            missing = db.execute(
                select(ContentChunk)
                .where(
                    ~sa.exists().where(
                        IndexJob.content_chunk_id == ContentChunk.id,
                        IndexJob.target == target,
                    )
                )
                .order_by(ContentChunk.created_at.asc())
                .limit(batch_size)
            ).scalars().all()
            _record_index_jobs(
                db,
                missing,
                target=target,
                status="pending",
                attempts=0,
            )
            stats["created_jobs"][target] = len(missing)
        db.commit()

        stats["elasticsearch_docs"] = int(get_keyword_store().stats().get("total") or 0)
        vector_store = get_vector_store()
        stats["milvus_vectors"] = {
            "public_signals": vector_store.count("public_signals"),
        }
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.rebuild_elasticsearch_alias_task",
    acks_late=True,
)
def rebuild_elasticsearch_alias_task(
    self,
    batch_size: int = 500,
    target_index: str | None = None,
    switch_alias: bool = True,
) -> dict:
    """Build a new versioned ES index from PG content_chunks and optionally switch alias."""
    from app.rag.keyword_store import get_keyword_store

    db = SessionLocal()
    store = get_keyword_store()
    store.create_index_if_missing()
    index_name = target_index or store.next_versioned_index_name()
    stats = {
        "target_index": index_name,
        "created": False,
        "scanned": 0,
        "attempted": 0,
        "indexed": 0,
        "errors": 0,
        "alias_switched": False,
    }
    try:
        stats["created"] = store.create_version_index(index_name)
        offset = 0
        while True:
            rows = list(db.execute(
                select(ContentChunk)
                .order_by(ContentChunk.created_at.asc(), ContentChunk.id.asc())
                .offset(offset)
                .limit(batch_size)
            ).scalars())
            if not rows:
                break
            stats["scanned"] += len(rows)
            result = _upsert_es_chunks_to_index(rows, index_name=index_name)
            stats["attempted"] += result["attempted"]
            stats["indexed"] += result["indexed"]
            stats["errors"] += result["errors"]
            offset += len(rows)

        if switch_alias and stats["errors"] == 0:
            store.switch_alias(index_name)
            stats["alias_switched"] = True
        return stats
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.rebuild_claim_chunks_task",
    acks_late=True,
)
def rebuild_claim_chunks_task(self) -> dict:
    """删除旧逐标的观点索引并从规范化 claims 重建。

    流程：
      1. 从 PG、ES、Milvus 删除 claim 和遗留 analysis 索引
      2. 找出至少有一项已核验观点的分析结果
      3. 逐条 dispatch embed_signal_task 重建 claim 索引

    手动触发：
      rebuild_claim_chunks_task.delay()
    """
    from app.models.content_chunk import ContentChunk
    from app.models.instrument_claim import InstrumentClaim
    from app.rag.keyword_store import get_keyword_store
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    stats = {
        "deleted_pg": 0,
        "deleted_es": 0,
        "deleted_vectors": 0,
        "dispatched": 0,
    }
    try:
        old_chunks = list(
            db.execute(
                select(ContentChunk).where(
                    ContentChunk.source_type.in_(("claim", "analysis"))
                )
            ).scalars()
        )

        vector_ids = [c.vector_id for c in old_chunks if c.vector_id]
        stats["deleted_pg"] = len(old_chunks)
        for chunk in old_chunks:
            db.delete(chunk)
        try:
            store = get_keyword_store()
            for indexed_source_type in ("claim", "analysis"):
                deleted = store.delete_by_source_type(indexed_source_type)
                stats["deleted_es"] += int(deleted.get("deleted") or 0)
        except Exception as exc:
            logger.warning("[Celery] Elasticsearch claim cleanup skipped: %s", exc)
        db.commit()

        vs = get_vector_store()
        for indexed_source_type in ("claim", "analysis"):
            vs.delete_where(
                "public_signals",
                {"source_type": indexed_source_type},
            )
        stats["deleted_vectors"] = len(vector_ids)

        all_analyses = list(
            db.execute(
                select(AnalysisResult)
                .join(
                    InstrumentClaim,
                    InstrumentClaim.analysis_result_id == AnalysisResult.id,
                )
                .where(
                    AnalysisResult.analysis_type == "tweet_analysis",
                    InstrumentClaim.downstream_eligible.is_(True),
                )
                .distinct()
            ).scalars()
        )

        for ar in all_analyses:
            embed_signal_task.delay("analysis", str(ar.id))
            stats["dispatched"] += 1

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("[Celery] rebuild_claim_chunks: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.rebuild_tweet_chunks_task",
    acks_late=True,
)
def rebuild_tweet_chunks_task(self) -> dict:
    """删除旧 tweet chunks 并按新切块逻辑（结构感知 + 合并）重建。

    流程：
      1. 从 content_chunks 删除 source_type='tweet' 的所有记录
      2. 从 Milvus public_signals 删除对应向量
      3. 对每条有 content 的 tweet dispatch embed_signal_task 重新入库

    手动触发：
      rebuild_tweet_chunks_task.delay()
    """
    from app.models.content_chunk import ContentChunk
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    stats = {"deleted_pg": 0, "deleted_vectors": 0, "dispatched": 0}
    try:
        old_chunks = db.execute(
            select(ContentChunk).where(ContentChunk.source_type == "tweet")
        ).scalars().all()

        vector_ids = [c.vector_id for c in old_chunks if c.vector_id]
        stats["deleted_pg"] = len(old_chunks)

        for c in old_chunks:
            db.delete(c)
        db.commit()

        if vector_ids:
            vs = get_vector_store()
            vs.delete("public_signals", vector_ids)
            stats["deleted_vectors"] = len(vector_ids)

        all_tweets = db.execute(
            select(Tweet.id)
            .where(
                Tweet.content.is_not(None),
            )
        ).scalars().all()

        for tid in all_tweets:
            embed_signal_task.delay("tweet", str(tid))
            stats["dispatched"] += 1

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("[Celery] rebuild_tweet_chunks: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.scan_blogger_tweets_task",
    acks_late=True,
)
def scan_blogger_tweets_task(self) -> dict:
    """扫描启用定时抓取且已到期的博主，分发逐博主抓取任务。

    由 Celery Beat 按 twitter_fetch_interval_minutes 间隔触发。
    只负责调度，不做实际网络请求，保证快速返回。
    """
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings as cfg
    from app.models.blogger import Blogger

    if not cfg.twitter_fetch_enabled:
        return {"status": "disabled"}

    db = SessionLocal()
    stats = {"dispatched": 0, "skipped": 0}
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cfg.twitter_fetch_interval_minutes)
        due_bloggers = db.execute(
            select(Blogger)
            .where(
                Blogger.fetch_enabled == True,
                sa.or_(Blogger.last_fetched_at == None, Blogger.last_fetched_at <= cutoff),
            )
            .order_by(Blogger.last_fetched_at.asc().nullsfirst())
            .limit(cfg.twitter_fetch_batch_size)
        ).scalars().all()

        for blogger in due_bloggers:
            fetch_blogger_tweets_task.delay(blogger.handle)
            stats["dispatched"] += 1

        if not due_bloggers:
            stats["skipped"] = 0

    finally:
        db.close()

    logger.info("[Celery] scan_blogger_tweets: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.fetch_blogger_tweets_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,
)
def fetch_blogger_tweets_task(self, handle: str) -> dict:
    """抓取单个博主的最新推文，入库并触发分析。

    流程：
      1. 获取 per-handle Redis 锁
      2. 确保 blogger 有 twitter_user_id（缺失则先获取 profile）
      3. 调用 Twitter GraphQL 爬取推文
      4. 通过 import_tweets 去重入库
      5. 更新 Blogger.last_fetched_at
      6. 如有新推文，触发 manual_analysis_task
    """
    from datetime import datetime, timezone

    from app.core.config import settings as cfg
    from app.models.blogger import Blogger
    from app.schemas.blogger import BloggerProfile
    from app.schemas.tweet import TweetImportItem
    from app.services.twitter_service import (
        convert_profile_to_upsert,
        convert_tweets_to_import,
        fetch_user_profile,
        fetch_user_tweets,
    )
    from app.services.tweet_service import import_tweets

    acquired, lock_token = try_acquire_fetch_lock(handle)
    if not acquired:
        logger.info("[Celery] Fetch lock held for %s, skipping", handle)
        return {"handle": handle, "status": "locked"}

    db = SessionLocal()
    stats = {"handle": handle, "imported": 0, "skipped": 0, "status": "ok"}
    try:
        blogger = db.execute(
            select(Blogger).where(Blogger.handle == handle)
        ).scalar_one_or_none()

        if not blogger:
            logger.warning("[Celery] Blogger %s not found in DB", handle)
            stats["status"] = "not_found"
            return stats

        # 确保 twitter_user_id 存在，缺失则先获取 profile
        if not blogger.twitter_user_id:
            logger.info("[Celery] Fetching profile for %s to get twitter_user_id", handle)
            raw_profile = fetch_user_profile(handle)
            if raw_profile is None:
                logger.warning("[Celery] Failed to fetch profile for %s", handle)
                stats["status"] = "profile_failed"
                return stats

            profile_data = convert_profile_to_upsert(raw_profile)
            blogger.twitter_user_id = profile_data.get("twitter_user_id")
            if not blogger.twitter_user_id:
                logger.warning("[Celery] No twitter_user_id in profile for %s", handle)
                stats["status"] = "no_user_id"
                return stats
            db.commit()

        # 抓取推文
        raw_tweets = fetch_user_tweets(
            blogger.twitter_user_id,
            max_pages=cfg.twitter_fetch_max_pages,
        )
        if not raw_tweets:
            logger.info("[Celery] No tweets fetched for %s", handle)
            blogger.last_fetched_at = datetime.now(timezone.utc)
            db.commit()
            stats["status"] = "no_tweets"
            return stats

        # 转换并入库
        import_items_raw = convert_tweets_to_import(raw_tweets)
        items = [TweetImportItem(**item) for item in import_items_raw]

        imported, skipped, _tweet_ids = import_tweets(db, items, return_ids=True)
        stats["imported"] = imported
        stats["skipped"] = skipped

        # 更新抓取时间
        blogger.last_fetched_at = datetime.now(timezone.utc)
        db.commit()

        # 有新推文则触发分析
        if imported > 0:
            logger.info("[Celery] %d new tweets for %s, analysis queued", imported, handle)

        logger.info("[Celery] Fetch %s done: imported=%d skipped=%d", handle, imported, skipped)

    except Exception as e:
        db.rollback()
        logger.error("[Celery] Fetch error for %s: %s", handle, e)
        raise
    finally:
        db.close()
        release_fetch_lock(handle, lock_token)

    return stats
