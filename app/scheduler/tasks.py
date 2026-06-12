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

from app.core.deps import SessionLocal
from app.models.analysis import AnalysisResult
from app.models.tweet import Tweet
from app.scheduler.locks import (
    try_acquire,
    release,
    try_acquire_prediction_lock,
    release_prediction_lock,
)
from app.services.analysis_service import analyze_by_blogger

logger = get_task_logger(__name__)


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
    logger.info("[Celery] Auto-analysis task started")

    db = SessionLocal()
    stats = {"total_bloggers": 0, "analyzed": 0, "skipped": 0, "errors": 0}

    try:
        handles = [
            row[0]
            for row in db.execute(
                select(Tweet.author_handle)
                .where(Tweet.status == "pending")
                .group_by(Tweet.author_handle)
            ).all()
        ]

        if not handles:
            logger.info("[Celery] No bloggers with pending tweets")
            return stats

        stats["total_bloggers"] = len(handles)
        logger.info("[Celery] Found %d bloggers with pending tweets", len(handles))

        for handle in handles:
            if not try_acquire(handle):
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
                stats["analyzed"] += 1
            except Exception as e:
                logger.error("[Celery] Error analyzing %s: %s", handle, e)
                stats["errors"] += 1
            finally:
                release(handle)

    except Exception as e:
        logger.error("[Celery] Unexpected error in auto_analysis: %s", e)
        raise
    finally:
        db.close()

    logger.info("[Celery] Auto-analysis completed: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.manual_analysis_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def manual_analysis_task(
    self,
    blogger_handles: list[str],
    reanalyze: bool = False,
    since: str | None = None,
) -> dict:
    """智能助手手动触发的分析任务，支持指定博主/重分析/时间范围。"""
    from datetime import datetime, timedelta, timezone

    logger.info(
        "[Celery] Manual analysis: handles=%s reanalyze=%s since=%s",
        blogger_handles, reanalyze, since,
    )

    db = SessionLocal()
    stats = {"total_bloggers": 0, "analyzed": 0, "skipped": 0, "errors": 0}

    try:
        since_dt = None
        if since:
            amount = int(since[:-1])
            unit = since[-1]
            delta = {"d": timedelta(days=amount), "w": timedelta(weeks=amount), "h": timedelta(hours=amount)}.get(unit)
            if delta:
                since_dt = datetime.now(timezone.utc) - delta

        statuses = ["pending", "analyzed"] if reanalyze else ["pending"]

        for handle in blogger_handles:
            if not try_acquire(handle):
                logger.info("[Celery] Skipping %s — locked", handle)
                stats["skipped"] += 1
                continue

            try:
                query = (
                    select(Tweet)
                    .where(Tweet.author_handle == handle, Tweet.status.in_(statuses))
                )
                if since_dt:
                    query = query.where(Tweet.published_at >= since_dt)

                tweets_to_reset = db.execute(query).scalars().all()

                if not tweets_to_reset:
                    stats["skipped"] += 1
                    continue

                for t in tweets_to_reset:
                    t.status = "pending"
                db.commit()

                result = analyze_by_blogger(db, handle)
                logger.info("[Celery] Manual done %s: analyzed=%d", handle, result["analyzed"])
                stats["analyzed"] += 1
            except Exception as e:
                db.rollback()
                logger.error("[Celery] Manual error %s: %s", handle, e)
                stats["errors"] += 1
            finally:
                release(handle)

        stats["total_bloggers"] = len(blogger_handles)
    except Exception as e:
        logger.error("[Celery] Manual analysis unexpected error: %s", e)
        raise
    finally:
        db.close()

    logger.info("[Celery] Manual analysis completed: %s", stats)
    return stats


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

    if not try_acquire_prediction_lock():
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

        from app.agents.prediction_agent import prediction_agent_node
        from app.models.tweet import Tweet as TweetModel

        tweet_ids = [ar.tweet_id for ar in pending_analyses]
        tweet_rows = db.execute(
            select(TweetModel).where(TweetModel.id.in_(tweet_ids))
        ).scalars().all()
        tweet_map = {t.id: t for t in tweet_rows}

        analyses_for_prediction = []
        tweets_for_prediction = []
        for ar in pending_analyses:
            result_data = ar.result or {}
            if not result_data.get("is_investment_related"):
                ar.prediction_status = "skipped"
                continue
            tweet = tweet_map.get(ar.tweet_id)
            if tweet is None:
                ar.prediction_status = "skipped"
                continue
            result_data["tweet_id"] = str(ar.tweet_id)
            result_data["author_handle"] = tweet.author_handle
            analyses_for_prediction.append(result_data)
            tweets_for_prediction.append({
                "id": str(tweet.id),
                "published_at": tweet.published_at,
                "author_handle": tweet.author_handle,
            })

        if analyses_for_prediction:
            try:
                pred_result = prediction_agent_node({
                    "analyses": analyses_for_prediction,
                    "tweets": tweets_for_prediction,
                    "predictions": [],
                })
                predictions = pred_result.get("predictions", [])

                ar_id_by_tweet = {str(ar.tweet_id): str(ar.id) for ar in pending_analyses}
                for pred in predictions:
                    pred["analysis_id"] = ar_id_by_tweet.get(pred.get("tweet_id"))

                stats["predictions_created"] = len(predictions)

                from app.services.prediction_service import save_predictions_batch
                save_predictions_batch(db, predictions)

                ticker_summaries = pred_result.get("ticker_summaries", [])
                ref_tweet_id = pending_analyses[0].tweet_id
                for summary in ticker_summaries:
                    ticker_symbol = summary.get("ticker", "")
                    existing_ts = db.execute(
                        select(AnalysisResult).where(
                            AnalysisResult.analysis_type == "ticker_summary",
                            AnalysisResult.result["ticker"].astext == ticker_symbol,
                        )
                    ).scalar_one_or_none()
                    if existing_ts:
                        existing_ts.result = summary
                        existing_ts.confidence = summary.get("recommendation_score", 0) / 100
                    else:
                        db.add(AnalysisResult(
                            tweet_id=ref_tweet_id,
                            analysis_type="ticker_summary",
                            result=summary,
                            model_used="aggregation",
                            confidence=summary.get("recommendation_score", 0) / 100,
                            prediction_status="skipped",
                        ))
                stats["ticker_summaries_saved"] = len(ticker_summaries)

                processed_ids = [ar.id for ar in pending_analyses if ar.prediction_status != "skipped"]
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

        # 预测完成后异步触发分析结果向量化，入库到 public_signals
        for ar in pending_analyses:
            if ar.prediction_status == "done":
                embed_signal_task.delay("analysis", str(ar.id))

    except Exception as e:
        db.rollback()
        logger.error("[Celery] Prediction batch error: %s", e)
        raise
    finally:
        db.close()
        release_prediction_lock()

    logger.info("[Celery] Prediction batch completed: %s", stats)
    return stats


def _resolve_text(doc) -> str:
    """Resolve the document's text content based on its source_type.

    - paste/markdown/url: text stored as .txt on disk by the API layer
    - pdf/docx: raw binary stored on disk, re-parsed here
    """
    from app.core.config import settings
    from app.rag.parsers.docx_parser import parse_docx
    from app.rag.parsers.pdf_parser import parse_pdf
    from app.rag.storage import DocumentStorage

    storage = DocumentStorage(settings.document_storage_root)
    base = storage.root / str(doc.user_id) / str(doc.id)

    if doc.source_type in ("paste", "markdown", "url"):
        return base.with_suffix(".txt").read_bytes().decode("utf-8")
    elif doc.source_type == "pdf":
        return parse_pdf(base.with_suffix(".pdf").read_bytes()).text
    elif doc.source_type == "docx":
        return parse_docx(base.with_suffix(".docx").read_bytes()).text
    else:
        raise ValueError(f"Unknown source_type: {doc.source_type}")


@shared_task(
    bind=True,
    name="app.scheduler.tasks.ingest_document_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def ingest_document_task(self, document_id: str) -> dict:
    """Parse, chunk, embed, and index a document into the vector store."""
    from hashlib import sha256
    from uuid import UUID

    from app.core.config import settings
    from app.models.doc_chunk import DocChunk
    from app.models.document import Document
    from app.rag.chunking import chunk_document
    from app.rag.embeddings import get_embedder
    from app.rag.repository import Chunk, UserDocumentRepository
    from app.rag.tokenizer import tokenize_for_tsvector
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    try:
        doc = db.get(Document, UUID(document_id))
        if not doc or doc.status == "deleted":
            return {"skipped": True}

        doc.status = "processing"
        db.commit()

        text = _resolve_text(doc)
        chunks = chunk_document(
            text,
            chunk_size=settings.chunk_size_document,
            chunk_overlap=settings.chunk_overlap_document,
        )

        # Normalize tickers: can be ["BTC"] or [{"symbol":"NOK",...}]
        ticker_items = doc.tickers or []
        ticker_symbols = [
            (t["symbol"] if isinstance(t, dict) and "symbol" in t else str(t)).upper()
            for t in ticker_items
        ]
        tickers_str = ",".join(ticker_symbols) if ticker_symbols else ""

        rows = [
            DocChunk(
                document_id=doc.id,
                chunk_index=i,
                content=c,
                content_hash=sha256(c.encode("utf-8")).hexdigest(),
                char_count=len(c),
                metadata_={
                    k: v
                    for k, v in {
                        "title": doc.title,
                        "source_type": doc.source_type,
                        "source_uri": doc.source_uri,
                        "tickers": tickers_str or None,
                        "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
                    }.items()
                    if v is not None
                },
                search_vector=sa.func.to_tsvector("simple", tokenize_for_tsvector(c)),
            )
            for i, c in enumerate(chunks)
        ]
        db.add_all(rows)
        db.flush()

        repo = UserDocumentRepository(get_vector_store(), get_embedder())
        vector_ids = repo.add_chunks(
            user_id=doc.user_id,
            document_id=doc.id,
            chunks=[
                Chunk(chunk_index=r.chunk_index, content=r.content, metadata=r.metadata_)
                for r in rows
            ],
        )
        for r, vid in zip(rows, vector_ids):
            r.vector_id = vid

        doc.chunk_count = len(rows)
        doc.status = "indexed"
        db.commit()
        return {"document_id": str(doc.id), "chunks": len(rows)}
    except Exception as e:
        db.rollback()
        try:
            doc = db.get(Document, UUID(document_id))
            if doc:
                doc.status = "failed"
                doc.error_detail = str(e)[:1000]
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


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
    """Vectorize a tweet or analysis result into the public_signals collection."""
    from hashlib import sha256
    from uuid import UUID

    from app.core.config import settings
    from app.models.doc_chunk import DocChunk
    from app.rag.chunking import chunk_analysis, chunk_tweet
    from app.rag.embeddings import get_embedder
    from app.rag.tokenizer import tokenize_for_tsvector
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    try:
        if source_type == "tweet":
            tweet = db.get(Tweet, UUID(source_id))
            if not tweet or not tweet.content:
                return {"skipped": True}
            chunks = chunk_tweet(tweet.content)
            tickers = []
            analysis = db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.tweet_id == tweet.id,
                    AnalysisResult.analysis_type == "tweet_analysis",
                )
            ).scalar_one_or_none()
            result_data = analysis.result if analysis else {}
            # 只对投资市场分析相关的推文做向量化，闲聊/生活类直接跳过
            if not result_data.get("is_investment_related"):
                return {"skipped": True, "reason": "not investment related"}
            tickers = result_data.get("tickers", [])
            sentiment = result_data.get("overall_sentiment", "neutral")
            # horizon 是 per-ticker 字段，取第一个有效值
            horizon = "unknown"
            for t in (tickers or []):
                if isinstance(t, dict) and t.get("horizon", "unknown") != "unknown":
                    horizon = t["horizon"]
                    break
            metadata_base = {
                "source_type": "tweet",
                "source_id": str(tweet.id),
                "blogger_handle": tweet.author_handle,
                "sentiment": sentiment,
                "horizon": horizon,
                "published_at": tweet.published_at.isoformat() if tweet.published_at else "",
                "credibility_score": 0.0,
            }
        elif source_type == "analysis":
            analysis = db.get(AnalysisResult, UUID(source_id))
            if not analysis or not analysis.result:
                return {"skipped": True}
            result_data = analysis.result
            tweet = db.get(Tweet, analysis.tweet_id)
            tweet_text = tweet.content if tweet and tweet.content else ""

            # 从结构化分析结果中提取有语义价值的字段，避免 str(dict) 噪声
            parts: list[str] = []
            if result_data.get("reasoning"):
                parts.append(result_data["reasoning"])
            if result_data.get("key_points"):
                parts.append("核心观点：" + "；".join(result_data["key_points"]))
            if result_data.get("tickers"):
                ticker_descs = []
                for t in result_data["tickers"]:
                    if isinstance(t, dict):
                        ticker_descs.append(f"{t.get('symbol', '')}({t.get('sentiment', '')})")
                    else:
                        ticker_descs.append(str(t))
                parts.append("标的：" + "、".join(ticker_descs))
            if result_data.get("risk_factors"):
                parts.append("风险：" + "；".join(result_data["risk_factors"]))
            summary_text = "\n".join(parts) if parts else result_data.get("overall_sentiment", "neutral")

            content = f"{tweet_text}\n\n分析：{summary_text}" if tweet_text else summary_text
            chunks = chunk_analysis(content, settings.chunk_size_analysis)
            tickers = result_data.get("tickers", [])
            sentiment = result_data.get("overall_sentiment", "neutral")
            horizon = "unknown"
            for t in (tickers or []):
                if isinstance(t, dict) and t.get("horizon", "unknown") != "unknown":
                    horizon = t["horizon"]
                    break
            metadata_base = {
                "source_type": "analysis",
                "source_id": str(analysis.id),
                "blogger_handle": tweet.author_handle if tweet else "",
                "sentiment": sentiment,
                "horizon": horizon,
                "published_at": tweet.published_at.isoformat() if tweet and tweet.published_at else "",
                "credibility_score": analysis.confidence or 0.0,
            }
        else:
            return {"error": f"Unknown source_type: {source_type}"}

        if not chunks:
            return {"skipped": True, "reason": "empty content"}

        # Normalize tickers: can be ["BTC"] or [{"symbol": "NOK", ...}]
        ticker_symbols: list[str] = []
        for t in (tickers or []):
            if isinstance(t, str):
                ticker_symbols.append(t)
            elif isinstance(t, dict) and "symbol" in t:
                ticker_symbols.append(t["symbol"])

        # Store tickers as comma-joined string (ChromaDB doesn't support array metadata)
        tickers_str = ",".join(ticker_symbols) if ticker_symbols else ""

        # 短文本 context 增强：对 ≤100 字的 chunk 拼接 [博主][日期][标的] 前缀用于 embedding
        # 存储 content 保持原文不变，只影响向量计算输入
        SHORT_TEXT_THRESHOLD = 100
        embed_texts = []
        for chunk_text in chunks:
            if len(chunk_text) <= SHORT_TEXT_THRESHOLD and source_type == "tweet":
                prefix_parts = []
                if metadata_base.get("blogger_handle"):
                    prefix_parts.append(f"@{metadata_base['blogger_handle']}")
                if metadata_base.get("published_at"):
                    prefix_parts.append(metadata_base["published_at"][:10])
                if tickers_str:
                    prefix_parts.append(tickers_str)
                prefix = " ".join(prefix_parts)
                embed_texts.append(f"[{prefix}] {chunk_text}" if prefix else chunk_text)
            else:
                embed_texts.append(chunk_text)

        vs = get_vector_store()
        embedder = get_embedder()
        vectors = embedder.embed_documents(embed_texts)
        indexed = 0

        for i, (chunk_text, vec) in enumerate(zip(chunks, vectors)):
            content_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
            vector_id = f"{source_type}:{source_id}:{i}"
            meta = {**metadata_base, "ticker": tickers_str}
            vs.add(
                "public_signals",
                ids=[vector_id],
                texts=[chunk_text],
                embeddings=[vec],
                metadatas=[meta],
            )
            db.add(DocChunk(
                document_id=None,
                chunk_index=i,
                content=chunk_text,
                content_hash=content_hash,
                char_count=len(chunk_text),
                metadata_=meta,
                vector_id=vector_id,
                search_vector=sa.func.to_tsvector("simple", tokenize_for_tsvector(chunk_text)),
            ))
            indexed += 1

        db.commit()
        return {"source_type": source_type, "source_id": source_id, "indexed": indexed}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.scan_due_tracking_task",
    acks_late=True,
)
def scan_due_tracking_task(self) -> dict:
    """Scan for tracked tickers with next_run_at <= now, dispatch report tasks."""
    from app.services.tracking_service import get_due_subscriptions

    db = SessionLocal()
    stats = {"dispatched": 0}
    try:
        due = get_due_subscriptions(db)
        for record in due:
            scheduled_report_task.delay(str(record.id))
            stats["dispatched"] += 1
    finally:
        db.close()
    logger.info("[Celery] scan_due_tracking: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.scheduled_report_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def scheduled_report_task(self, tracking_id: str) -> dict:
    """Generate a scheduled report for a tracked ticker subscription."""
    from uuid import UUID

    from app.models.tracked_ticker import TrackedTicker
    from app.services.report_service import create_and_run_report
    from app.services.tracking_service import advance_next_run

    db = SessionLocal()
    try:
        record = db.get(TrackedTicker, UUID(tracking_id))
        if not record or record.status != "active":
            return {"skipped": True}

        report = create_and_run_report(
            db, record.user_id, record.ticker,
            trigger_type="scheduled", tracked_ticker_id=record.id,
        )
        advance_next_run(db, record.id)
        return {"report_id": str(report.id), "status": report.status}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.report_streaming_task",
    acks_late=True,
    max_retries=0,  # 失败不重试：用户已看到流式中断，重跑应由用户触发
)
def report_streaming_task(self, report_id: str, user_id: str, ticker: str) -> dict:
    """跑流式报告生成；通过 Redis pub/sub 推 SSE，增量写库。"""
    from uuid import UUID

    from app.services.report_streaming import run_report_streaming

    db = SessionLocal()
    try:
        return run_report_streaming(
            db=db,
            report_id=UUID(report_id),
            user_id=UUID(user_id),
            query=f"生成 {ticker} 跟踪报告",
        )
    finally:
        db.close()


@shared_task(
    bind=True,
    name="app.scheduler.tasks.gc_vector_task",
    acks_late=True,
)
def gc_vector_task(self) -> dict:
    """Clean up vectors for soft-deleted documents older than 24h."""
    from datetime import datetime, timedelta, timezone

    from app.models.doc_chunk import DocChunk
    from app.models.document import Document
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    stats = {"cleaned": 0}
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        deleted_docs = db.execute(
            select(Document).where(
                Document.status == "deleted",
                Document.updated_at <= cutoff,
            )
        ).scalars().all()

        vs = get_vector_store()
        for doc in deleted_docs:
            chunks = db.execute(
                select(DocChunk).where(DocChunk.document_id == doc.id)
            ).scalars().all()
            vector_ids = [c.vector_id for c in chunks if c.vector_id]
            if vector_ids:
                vs.delete("user_documents", vector_ids)
            for c in chunks:
                db.delete(c)
            db.delete(doc)
            stats["cleaned"] += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("[Celery] gc_vector: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.backfill_signals_task",
    acks_late=True,
)
def backfill_signals_task(self, batch_size: int = 100) -> dict:
    """回填历史已分析推文的向量化。

    扫描 status='analyzed' 但尚未在 doc_chunks 中有 source_type='tweet' 记录的推文，
    分批 dispatch embed_signal_task 避免队列积压。

    可通过 Celery Beat 定期执行，也可手动触发：
      backfill_signals_task.delay(batch_size=200)
    """
    from app.models.doc_chunk import DocChunk

    db = SessionLocal()
    stats = {"dispatched": 0, "already_indexed": 0}
    try:
        # 找出所有已分析但未向量化的推文
        # 子查询：已有 tweet 类型 doc_chunk 的 source_id 集合
        indexed_subq = (
            select(DocChunk.metadata_["source_id"].astext)
            .where(DocChunk.metadata_["source_type"].astext == "tweet")
            .scalar_subquery()
        )

        pending_tweets = db.execute(
            select(Tweet)
            .where(
                Tweet.status == "analyzed",
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
    """回填历史分析结果的向量化。

    扫描 analysis_type='tweet_analysis' 且尚未在 doc_chunks 中有
    source_type='analysis' 记录的分析结果，分批 dispatch embed_signal_task。

    手动触发：
      backfill_analysis_signals_task.delay(batch_size=200)
    """
    from app.models.doc_chunk import DocChunk

    db = SessionLocal()
    stats = {"dispatched": 0}
    try:
        indexed_subq = (
            select(DocChunk.metadata_["source_id"].astext)
            .where(DocChunk.metadata_["source_type"].astext == "analysis")
            .scalar_subquery()
        )

        pending = db.execute(
            select(AnalysisResult)
            .where(
                AnalysisResult.analysis_type == "tweet_analysis",
                AnalysisResult.id.cast(sa.String).not_in(indexed_subq),
            )
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
    name="app.scheduler.tasks.backfill_search_vector_task",
    acks_late=True,
)
def backfill_search_vector_task(self, batch_size: int = 200) -> dict:
    """回填已有 doc_chunks 的 search_vector 列（逐批 UPDATE）。

    查询 search_vector IS NULL 的记录，用 jieba 分词后写入 tsvector。
    每次处理 batch_size 条，通过 Beat 定期执行直到全部回填完毕。

    手动触发：
      backfill_search_vector_task.delay(batch_size=500)
    """
    from app.models.doc_chunk import DocChunk
    from app.rag.tokenizer import tokenize_for_tsvector

    db = SessionLocal()
    stats = {"updated": 0, "remaining": 0}
    try:
        rows = db.execute(
            select(DocChunk)
            .where(DocChunk.search_vector.is_(None))
            .limit(batch_size)
        ).scalars().all()

        for chunk in rows:
            tokenized = tokenize_for_tsvector(chunk.content or "")
            if tokenized:
                chunk.search_vector = sa.func.to_tsvector("simple", tokenized)
            else:
                chunk.search_vector = sa.func.to_tsvector("simple", "")
            stats["updated"] += 1

        db.commit()

        remaining = db.execute(
            select(sa.func.count())
            .select_from(DocChunk)
            .where(DocChunk.search_vector.is_(None))
        ).scalar() or 0
        stats["remaining"] = remaining

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("[Celery] backfill_search_vector: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.rebuild_analysis_chunks_task",
    acks_late=True,
)
def rebuild_analysis_chunks_task(self, batch_size: int = 100) -> dict:
    """删除旧 analysis chunks 并重建（修复 str(dict) 噪声内容）。

    流程：
      1. 从 doc_chunks 删除 source_type='analysis' 的所有记录
      2. 从 ChromaDB public_signals 删除对应向量
      3. 逐批 dispatch embed_signal_task 重新入库

    手动触发：
      rebuild_analysis_chunks_task.delay()
    """
    from app.models.doc_chunk import DocChunk
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    stats = {"deleted_pg": 0, "deleted_vectors": 0, "dispatched": 0}
    try:
        old_chunks = db.execute(
            select(DocChunk).where(
                DocChunk.metadata_["source_type"].astext == "analysis"
            )
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

        all_analyses = db.execute(
            select(AnalysisResult).where(
                AnalysisResult.analysis_type == "tweet_analysis",
            )
        ).scalars().all()

        for ar in all_analyses:
            embed_signal_task.delay("analysis", str(ar.id))
            stats["dispatched"] += 1

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    logger.info("[Celery] rebuild_analysis_chunks: %s", stats)
    return stats


@shared_task(
    bind=True,
    name="app.scheduler.tasks.rebuild_tweet_chunks_task",
    acks_late=True,
)
def rebuild_tweet_chunks_task(self) -> dict:
    """删除旧 tweet chunks 并按新切块逻辑（结构感知 + 合并）重建。

    流程：
      1. 从 doc_chunks 删除 source_type='tweet' 的所有记录
      2. 从 ChromaDB public_signals 删除对应向量
      3. 对每条有 content 的 tweet dispatch embed_signal_task 重新入库

    手动触发：
      rebuild_tweet_chunks_task.delay()
    """
    from app.models.doc_chunk import DocChunk
    from app.rag.vector_store import get_vector_store

    db = SessionLocal()
    stats = {"deleted_pg": 0, "deleted_vectors": 0, "dispatched": 0}
    try:
        old_chunks = db.execute(
            select(DocChunk).where(
                DocChunk.metadata_["source_type"].astext == "tweet"
            )
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
            .join(AnalysisResult, AnalysisResult.tweet_id == Tweet.id)
            .where(
                Tweet.content.is_not(None),
                AnalysisResult.analysis_type == "tweet_analysis",
                AnalysisResult.result["is_investment_related"].astext == "true",
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
