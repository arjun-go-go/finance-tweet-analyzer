from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.tweet import Tweet
from app.schemas.blogger import BloggerProfile
from app.schemas.tweet import TweetImportItem
from app.services.blogger_service import ensure_blogger, upsert_blogger


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

    for item in items:
        if item.tweet_id in seen_ids:
            skipped += 1
            continue
        seen_ids.add(item.tweet_id)

        exists = db.execute(
            select(Tweet).where(Tweet.tweet_id == item.tweet_id)
        ).scalar_one_or_none()

        if exists:
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
            status="pending",
        )
        db.add(tweet)
        imported_tweets.append(tweet)
        imported += 1

    if return_ids and imported_tweets and hasattr(db, "flush"):
        db.flush()

    db.commit()
    logger.info("Tweet import: {} imported, {} skipped", imported, skipped)
    if return_ids:
        return imported, skipped, [t.id for t in imported_tweets]
    return imported, skipped
