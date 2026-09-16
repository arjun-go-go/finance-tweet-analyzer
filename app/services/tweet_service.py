from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone

from app.models.tweet import Tweet
from app.schemas.blogger import BloggerProfile
from app.schemas.tweet import TweetImportItem
from app.services.blogger_service import ensure_blogger, upsert_blogger
from app.services.outbox_service import enqueue_outbox_event


def import_tweets(
    db: Session,
    items: list[TweetImportItem],
    blogger: BloggerProfile | None = None,
    *,
    return_ids: bool = False,
) -> tuple[int, int] | tuple[int, int, list[UUID]]:
    if blogger is not None:
        upsert_blogger(db, blogger)

    imported = 0
    skipped = 0
    seen_ids: set[str] = set()
    imported_tweets: list[Tweet] = []
    enriched_tweets: list[Tweet] = []

    for item in items:
        if item.tweet_id in seen_ids:
            skipped += 1
            continue
        seen_ids.add(item.tweet_id)

        if not item.content.strip() and not item.media_urls and not item.referenced_tweets:
            logger.warning("Skipping tweet {} because it has no analyzable content", item.tweet_id)
            skipped += 1
            continue

        exists = db.execute(
            select(Tweet).where(Tweet.tweet_id == item.tweet_id)
        ).scalar_one_or_none()

        if exists:
            # Re-fetching an older tweet can enrich relationship metadata added
            # after its initial import without changing the original content.
            exists.tweet_type = item.tweet_type
            exists.conversation_tweet_id = item.conversation_tweet_id
            exists.in_reply_to_tweet_id = item.in_reply_to_tweet_id
            exists.quoted_tweet_id = item.quoted_tweet_id
            exists.reposted_tweet_id = item.reposted_tweet_id
            exists.referenced_tweets = item.referenced_tweets
            if item.content.strip() and not (exists.content or "").strip():
                exists.content = item.content
                exists.raw_json = item.raw_json
                exists.media_urls = item.media_urls
                exists.author_name = item.author_name
                exists.status = "media_pending" if item.media_urls else "pending"
                exists.analysis_attempts = 0
                exists.analysis_last_error = None
                exists.analysis_next_retry_at = None
                exists.analysis_started_at = None
                exists.analysis_completed_at = None
                exists.failure_stage = None
                exists.processing_updated_at = datetime.now(timezone.utc)
                enriched_tweets.append(exists)
                logger.info(
                    "Enriched previously empty tweet {} with {} characters",
                    item.tweet_id,
                    len(item.content),
                )
            skipped += 1
            continue

        tweet = Tweet(
            tweet_id=item.tweet_id,
            author_handle=item.author_handle,
            author_name=item.author_name,
            content=item.content,
            published_at=item.published_at,
            metrics=item.metrics,
            media_urls=item.media_urls,
            raw_json=item.raw_json,
            tweet_type=item.tweet_type,
            conversation_tweet_id=item.conversation_tweet_id,
            in_reply_to_tweet_id=item.in_reply_to_tweet_id,
            quoted_tweet_id=item.quoted_tweet_id,
            reposted_tweet_id=item.reposted_tweet_id,
            referenced_tweets=item.referenced_tweets,
            status="media_pending" if isinstance(item.media_urls, list) and item.media_urls else "pending",
            processing_updated_at=datetime.now(timezone.utc),
        )
        db.add(tweet)
        imported_tweets.append(tweet)
        imported += 1

    pipeline_tweets = imported_tweets + enriched_tweets
    if pipeline_tweets and hasattr(db, "flush"):
        db.flush()

    for tweet in pipeline_tweets:
        enqueue_outbox_event(
            db,
            "tweet.index_requested",
            {"tweet_id": str(tweet.id)},
        )
        if isinstance(tweet.media_urls, list) and tweet.media_urls:
            enqueue_outbox_event(
                db,
                "tweet.media_archive_requested",
                {"tweet_id": str(tweet.id)},
            )
        else:
            enqueue_outbox_event(
                db,
                "tweet.analysis_requested",
                {"tweet_id": str(tweet.id)},
            )

    db.commit()
    logger.info("Tweet import: {} imported, {} skipped", imported, skipped)
    if return_ids:
        return imported, skipped, [t.id for t in imported_tweets]
    return imported, skipped
