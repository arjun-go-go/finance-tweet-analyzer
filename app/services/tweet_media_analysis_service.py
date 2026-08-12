from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import get_vision_llm
from app.core.config import settings
from app.models.tweet import Tweet
from app.models.tweet_media_analysis import TweetMediaAnalysis
from app.models.tweet_media_asset import TweetMediaAsset
from app.prompts import get_prompt
from app.rag.storage import TweetMediaStorage
from app.schemas.media_analysis import TweetMediaAnalysisOutput
from app.services.outbox_service import enqueue_outbox_event


def _prepare_image(content: bytes) -> bytes:
    with Image.open(BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
        else:
            image = image.copy()

        max_dimension = settings.vision_max_image_dimension
        if max(image.size) > max_dimension:
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="JPEG", quality=settings.vision_jpeg_quality, optimize=True)
        return output.getvalue()


def _media_set_hash(assets: list[TweetMediaAsset]) -> str:
    digest_input = "|".join(asset.content_hash or str(asset.id) for asset in assets)
    return sha256(digest_input.encode("utf-8")).hexdigest()


def _usage_from_message(message) -> dict:
    usage = dict(getattr(message, "usage_metadata", None) or {})
    metadata = dict(getattr(message, "response_metadata", None) or {})
    token_usage = metadata.get("token_usage") or metadata.get("usage") or {}
    normalized = {
        "input_tokens": int(usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or token_usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or token_usage.get("total_tokens") or 0),
    }
    cost = metadata.get("cost") or token_usage.get("cost")
    if isinstance(cost, (int, float)):
        normalized["cost_usd"] = float(cost)
    return normalized


def get_tweet_media_context(db: Session, tweet_id: UUID | str) -> dict | None:
    row = db.execute(
        select(TweetMediaAnalysis).where(
            TweetMediaAnalysis.tweet_id == UUID(str(tweet_id)),
            TweetMediaAnalysis.status == "completed",
        )
    ).scalar_one_or_none()
    return row.result if row and row.result else None


def analyze_tweet_media(db: Session, tweet_id: UUID | str) -> dict:
    tweet = db.get(Tweet, UUID(str(tweet_id)))
    if tweet is None:
        raise ValueError(f"Tweet not found: {tweet_id}")

    assets = list(
        db.execute(
            select(TweetMediaAsset)
            .where(
                TweetMediaAsset.tweet_id == tweet.id,
                TweetMediaAsset.status == "downloaded",
                TweetMediaAsset.object_key.is_not(None),
            )
            .order_by(TweetMediaAsset.created_at.asc())
            .limit(settings.vision_max_images_per_tweet)
        ).scalars().all()
    )
    if not assets:
        tweet.status = "pending"
        enqueue_outbox_event(db, "tweet.analysis_requested", {"tweet_id": str(tweet.id)})
        db.commit()
        return {"tweet_id": str(tweet.id), "status": "skipped", "reason": "no_archived_media"}

    media_hash = _media_set_hash(assets)
    record = db.execute(
        select(TweetMediaAnalysis).where(TweetMediaAnalysis.tweet_id == tweet.id)
    ).scalar_one_or_none()
    if (
        record
        and record.status == "completed"
        and record.media_set_hash == media_hash
        and record.model_used == settings.vision_model
        and record.prompt_version == settings.vision_prompt_version
    ):
        return {"tweet_id": str(tweet.id), "status": "cached", "analysis_id": str(record.id)}

    if record is None:
        record = TweetMediaAnalysis(
            tweet_id=tweet.id,
            media_set_hash=media_hash,
            model_used=settings.vision_model,
            prompt_version=settings.vision_prompt_version,
        )
        db.add(record)
    record.media_set_hash = media_hash
    record.model_used = settings.vision_model
    record.prompt_version = settings.vision_prompt_version
    record.status = "analyzing"
    record.error_detail = None
    record.attempts = (record.attempts or 0) + 1
    db.commit()

    storage = TweetMediaStorage()
    try:
        human_content: list[dict] = [
            {
                "type": "text",
                "text": get_prompt(
                    "vision/human",
                    author_handle=tweet.author_handle,
                    content=tweet.content,
                    image_count=len(assets),
                ),
            }
        ]
        for index, asset in enumerate(assets, start=1):
            image_bytes = _prepare_image(storage.load(asset.object_key))
            data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
            human_content.append({"type": "text", "text": f"图片 {index}"})
            human_content.append({"type": "image_url", "image_url": {"url": data_url}})

        structured_llm = get_vision_llm().with_structured_output(
            TweetMediaAnalysisOutput,
            include_raw=True,
        )
        envelope = structured_llm.invoke(
            [
                SystemMessage(content=get_prompt("vision/system")),
                HumanMessage(content=human_content),
            ]
        )
        response = envelope.get("parsed") if isinstance(envelope, dict) else envelope
        if response is None:
            raise RuntimeError("Vision model returned no structured result")

        result = response.model_dump()
        result["asset_ids"] = [str(asset.id) for asset in assets]
        record.result = result
        record.usage = _usage_from_message(envelope.get("raw")) if isinstance(envelope, dict) else {}
        record.status = "completed"
        record.error_detail = None
        record.analyzed_at = datetime.now(timezone.utc)
        tweet.status = "pending"
        enqueue_outbox_event(db, "tweet.analysis_requested", {"tweet_id": str(tweet.id)})
        db.commit()
        return {
            "tweet_id": str(tweet.id),
            "status": "completed",
            "analysis_id": str(record.id),
            "image_count": len(assets),
            "confidence": result.get("confidence", 0.0),
        }
    except Exception as exc:
        db.rollback()
        record = db.execute(
            select(TweetMediaAnalysis).where(TweetMediaAnalysis.tweet_id == tweet.id)
        ).scalar_one()
        record.status = "failed"
        record.error_detail = str(exc)[:2000]
        db.commit()
        raise


def enqueue_tweet_media_analysis_backfill(db: Session) -> dict:
    tweet_ids = list(
        db.execute(
            select(TweetMediaAsset.tweet_id)
            .where(TweetMediaAsset.status == "downloaded")
            .distinct()
        ).scalars().all()
    )
    for tweet_id in tweet_ids:
        enqueue_outbox_event(db, "tweet.media_analyze_requested", {"tweet_id": str(tweet_id)})
    db.commit()
    return {"queued": len(tweet_ids)}
