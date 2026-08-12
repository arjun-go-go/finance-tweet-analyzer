from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from urllib.parse import urlparse
from uuid import UUID

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.resilience import resilient_tool
from app.models.tweet import Tweet
from app.models.tweet_media_asset import TweetMediaAsset
from app.rag.storage import TweetMediaStorage
from app.services.outbox_service import enqueue_outbox_event


@resilient_tool(
    retries=3,
    circuit_name="tweet_media_download",
    fallback_message="推文媒体下载失败",
    retryable_exceptions=(httpx.HTTPError, OSError),
)
def _download_image(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "pbs.twimg.com":
        raise ValueError("Only HTTPS media from pbs.twimg.com can be archived")

    max_bytes = settings.tweet_media_max_size_mb * 1024 * 1024
    with httpx.Client(
        follow_redirects=True,
        timeout=30.0,
        proxy=settings.http_proxy or None,
    ) as client:
        with client.stream("GET", url, headers={"User-Agent": "finance-tweet-analyzer/1.0"}) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                raise ValueError(f"Unsupported tweet media content type: {content_type or 'unknown'}")
            parts: list[bytes] = []
            size = 0
            for part in response.iter_bytes():
                size += len(part)
                if size > max_bytes:
                    raise ValueError(f"Tweet media exceeds {settings.tweet_media_max_size_mb} MB")
                parts.append(part)
    return b"".join(parts), content_type


def _image_metadata(content: bytes) -> tuple[int, int, str, str]:
    with Image.open(BytesIO(content)) as image:
        image.verify()
    with Image.open(BytesIO(content)) as image:
        width, height = image.size
        image_format = (image.format or "").upper()
    extensions = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
    }
    content_types = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
        "GIF": "image/gif",
    }
    if image_format not in extensions:
        raise ValueError(f"Unsupported tweet image format: {image_format or 'unknown'}")
    return width, height, extensions[image_format], content_types[image_format]


def _media_sources(media_urls) -> list[tuple[str, str | None]]:
    if not isinstance(media_urls, list):
        return []
    sources: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for item in media_urls:
        if not isinstance(item, dict):
            continue
        url = str(item.get("media_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        media_status_id = item.get("media_status_id")
        sources.append((url, str(media_status_id) if media_status_id else None))
    return sources


def archive_tweet_media(db: Session, tweet_id: UUID | str) -> dict:
    tweet = db.get(Tweet, UUID(str(tweet_id)))
    if tweet is None:
        raise ValueError(f"Tweet not found: {tweet_id}")

    sources = _media_sources(tweet.media_urls)
    stats = {"tweet_id": str(tweet.id), "total": len(sources), "downloaded": 0, "skipped": 0, "failed": 0}
    if not sources:
        tweet.status = "pending"
        enqueue_outbox_event(db, "tweet.analysis_requested", {"tweet_id": str(tweet.id)})
        db.commit()
        return stats

    storage = TweetMediaStorage()
    for source_url, media_status_id in sources:
        asset = db.execute(
            select(TweetMediaAsset).where(
                TweetMediaAsset.tweet_id == tweet.id,
                TweetMediaAsset.source_url == source_url,
            )
        ).scalar_one_or_none()
        if asset is not None and asset.status == "downloaded" and asset.object_key:
            stats["skipped"] += 1
            continue
        if asset is None:
            asset = TweetMediaAsset(
                tweet_id=tweet.id,
                media_status_id=media_status_id,
                source_url=source_url,
                storage_backend=storage.backend,
            )
            db.add(asset)

        asset.status = "downloading"
        asset.attempts = (asset.attempts or 0) + 1
        asset.error_detail = None
        try:
            downloaded = _download_image(source_url)
            if isinstance(downloaded, str):
                raise RuntimeError(downloaded)
            content, _ = downloaded
            width, height, extension, content_type = _image_metadata(content)
            content_hash = sha256(content).hexdigest()
            asset.object_key = storage.save(
                tweet.tweet_id,
                content_hash,
                content,
                extension,
                content_type,
            )
            asset.content_hash = content_hash
            asset.content_type = content_type
            asset.file_size_bytes = len(content)
            asset.width = width
            asset.height = height
            asset.status = "downloaded"
            stats["downloaded"] += 1
        except Exception as exc:
            asset.status = "failed"
            asset.error_detail = str(exc)[:1000]
            stats["failed"] += 1

    db.flush()
    has_archived_media = bool(
        db.execute(
            select(TweetMediaAsset.id).where(
                TweetMediaAsset.tweet_id == tweet.id,
                TweetMediaAsset.status == "downloaded",
                TweetMediaAsset.object_key.is_not(None),
            ).limit(1)
        ).scalar_one_or_none()
    )
    enqueue_outbox_event(
        db,
        "tweet.media_analyze_requested" if has_archived_media else "tweet.analysis_requested",
        {"tweet_id": str(tweet.id)},
    )
    if not has_archived_media:
        tweet.status = "pending"
    db.commit()
    return stats


def enqueue_tweet_media_backfill(db: Session) -> dict:
    tweets = db.execute(select(Tweet).order_by(Tweet.created_at.asc())).scalars().all()
    queued = 0
    for tweet in tweets:
        if not _media_sources(tweet.media_urls):
            continue
        enqueue_outbox_event(db, "tweet.media_archive_requested", {"tweet_id": str(tweet.id)})
        queued += 1
    db.commit()
    return {"queued": queued}
