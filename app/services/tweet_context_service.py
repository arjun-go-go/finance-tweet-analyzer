from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tweet import Tweet


THREAD_CONTEXT_LIMIT = 8
CONTEXT_CONTENT_LIMIT = 2000


def _context_tweet(tweet: Tweet) -> dict:
    return {
        "tweet_id": tweet.tweet_id,
        "tweet_type": tweet.tweet_type or "original",
        "author_handle": tweet.author_handle,
        "content": (tweet.content or "")[:CONTEXT_CONTENT_LIMIT],
        "published_at": tweet.published_at.isoformat() if tweet.published_at else None,
    }


def _bounded_references(references: list[dict] | None) -> list[dict]:
    bounded = []
    for reference in (references or [])[:5]:
        item = dict(reference)
        item["content"] = str(item.get("content") or "")[:CONTEXT_CONTENT_LIMIT]
        bounded.append(item)
    return bounded


def build_tweet_contexts(db: Session, tweets: list[Tweet]) -> dict:
    """Build bounded local thread/reference context with one database query."""
    conversation_ids = {
        tweet.conversation_tweet_id
        for tweet in tweets
        if tweet.conversation_tweet_id
    }
    thread_rows = []
    if conversation_ids:
        thread_rows = db.execute(
            select(Tweet)
            .where(Tweet.conversation_tweet_id.in_(conversation_ids))
            .order_by(Tweet.published_at.asc())
        ).scalars().all()

    grouped: dict[tuple[str, str], list[Tweet]] = defaultdict(list)
    for row in thread_rows:
        key = (row.conversation_tweet_id, row.author_handle.lower())
        grouped[key].append(row)

    contexts = {}
    for tweet in tweets:
        key = (tweet.conversation_tweet_id, tweet.author_handle.lower())
        same_author_thread = grouped.get(key, []) if tweet.conversation_tweet_id else []
        current_index = next(
            (index for index, row in enumerate(same_author_thread) if row.id == tweet.id),
            len(same_author_thread),
        )
        start = max(0, current_index - THREAD_CONTEXT_LIMIT // 2)
        selected = same_author_thread[start:start + THREAD_CONTEXT_LIMIT]

        contexts[tweet.id] = {
            "tweet_type": tweet.tweet_type or "original",
            "conversation_tweet_id": tweet.conversation_tweet_id,
            "in_reply_to_tweet_id": tweet.in_reply_to_tweet_id,
            "quoted_tweet_id": tweet.quoted_tweet_id,
            "reposted_tweet_id": tweet.reposted_tweet_id,
            "author_thread": [_context_tweet(row) for row in selected],
            "references": _bounded_references(tweet.referenced_tweets),
            "attribution_rule": (
                "author_thread is the followed blogger's own context; references are "
                "third-party content and must not be attributed to the blogger."
            ),
        }
    return contexts
