from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_admin, get_current_user
from app.models.user import User
from app.models.analysis import AnalysisResult
from app.models.instrument_claim import InstrumentClaim
from app.models.tweet import Tweet
from app.models.tweet_media_asset import TweetMediaAsset
from app.rag.storage import TweetMediaStorage
from app.schemas.tweet import TweetImportRequest, TweetImportResponse, TweetMediaItem
from app.services.tweet_service import import_tweets
from app.services.instrument_claim_service import (
    analysis_payload_with_claims,
    claims_by_analysis_ids,
)

router = APIRouter(prefix="/api/tweets", tags=["tweets"])


class TweetListItem(BaseModel):
    id: str
    tweet_id: str
    author_handle: str
    author_name: str
    content: str
    published_at: str
    status: str
    analysis_attempts: int = 0
    analysis_last_error: str | None = None
    analysis_next_retry_at: str | None = None
    analysis_started_at: str | None = None
    analysis_completed_at: str | None = None
    failure_stage: str | None = None
    processing_updated_at: str | None = None
    metrics: dict | None = None
    analysis: dict | None = None
    media: list[TweetMediaItem] = []
    tweet_type: str = "original"
    conversation_tweet_id: str | None = None
    in_reply_to_tweet_id: str | None = None
    quoted_tweet_id: str | None = None
    reposted_tweet_id: str | None = None
    referenced_tweets: list[dict] = Field(default_factory=list)


class TweetListResponse(BaseModel):
    items: list[TweetListItem]
    total: int


@router.get("", response_model=TweetListResponse)
def list_tweets(
    status: str | None = Query(
        None,
        description="pending / analyzing / retrying / analyzed / failed",
    ),
    blogger: str | None = Query(None),
    ticker: str | None = Query(None, max_length=64),
    include_analysis: bool = Query(False, description="Include latest tweet_analysis result"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Tweet).order_by(Tweet.published_at.desc())
    count_query = select(func.count()).select_from(Tweet)
    normalized_ticker = ticker.strip().upper() if ticker else None

    if status:
        query = query.where(Tweet.status == status)
        count_query = count_query.where(Tweet.status == status)
    if blogger:
        query = query.where(Tweet.author_handle == blogger)
        count_query = count_query.where(Tweet.author_handle == blogger)
    if normalized_ticker:
        matching_tweet_ids = (
            select(AnalysisResult.tweet_id)
            .join(
                InstrumentClaim,
                InstrumentClaim.analysis_result_id == AnalysisResult.id,
            )
            .where(
                AnalysisResult.analysis_type == "tweet_analysis",
                InstrumentClaim.instrument_symbol == normalized_ticker,
                InstrumentClaim.downstream_eligible.is_(True),
            )
        )
        query = query.where(Tweet.id.in_(matching_tweet_ids))
        count_query = count_query.where(Tweet.id.in_(matching_tweet_ids))

    total = db.execute(count_query).scalar() or 0
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()

    # If include_analysis, batch-fetch related analysis_results
    analysis_map: dict[str, dict] = {}
    media_map: dict[str, list[TweetMediaItem]] = {}
    reference_media_map: dict[str, dict[str, TweetMediaItem]] = {}
    if rows:
        reference_urls_by_tweet: dict[str, set[str]] = {}
        for tweet in rows:
            urls = {
                str(media.get("media_url") or "")
                for reference in (tweet.referenced_tweets or [])
                if isinstance(reference, dict)
                for media in (reference.get("media_urls") or [])
                if isinstance(media, dict) and media.get("media_url")
            }
            reference_urls_by_tweet[str(tweet.id)] = urls
        assets = db.execute(
            select(TweetMediaAsset)
            .where(
                TweetMediaAsset.tweet_id.in_([tweet.id for tweet in rows]),
                TweetMediaAsset.status == "downloaded",
                TweetMediaAsset.object_key.is_not(None),
            )
            .order_by(TweetMediaAsset.created_at.asc())
        ).scalars().all()
        for asset in assets:
            item = TweetMediaItem(
                id=str(asset.id),
                width=asset.width,
                height=asset.height,
                content_type=asset.content_type,
            )
            tweet_key = str(asset.tweet_id)
            if asset.source_url in reference_urls_by_tweet.get(tweet_key, set()):
                reference_media_map.setdefault(tweet_key, {})[asset.source_url] = item
            else:
                media_map.setdefault(tweet_key, []).append(item)
    if include_analysis and rows:
        tweet_ids = [t.id for t in rows]
        analysis_rows = db.execute(
            select(AnalysisResult).where(
                AnalysisResult.tweet_id.in_(tweet_ids),
                AnalysisResult.analysis_type == "tweet_analysis",
            )
        ).scalars().all()
        # Keep the latest analysis per tweet (by created_at desc)
        latest_by_tweet: dict[str, AnalysisResult] = {}
        for ar in analysis_rows:
            tid = str(ar.tweet_id)
            current = latest_by_tweet.get(tid)
            if current is None or (
                ar.created_at
                and (current.created_at is None or current.created_at < ar.created_at)
            ):
                latest_by_tweet[tid] = ar
        claim_map = claims_by_analysis_ids(
            db,
            [analysis.id for analysis in latest_by_tweet.values()],
        )
        for tid, ar in latest_by_tweet.items():
            claims = claim_map.get(ar.id, [])
            if normalized_ticker:
                claims = [
                    claim
                    for claim in claims
                    if claim.instrument_symbol == normalized_ticker
                    and claim.downstream_eligible
                ]
            analysis_map[tid] = {
                **analysis_payload_with_claims(
                    ar.result,
                    claims,
                ),
                "confidence": ar.confidence,
                "_created_at": ar.created_at.isoformat() if ar.created_at else "",
            }

    def references_with_archived_media(tweet: Tweet) -> list[dict]:
        archived = reference_media_map.get(str(tweet.id), {})
        output: list[dict] = []
        for raw_reference in tweet.referenced_tweets or []:
            if not isinstance(raw_reference, dict):
                continue
            reference = dict(raw_reference)
            media_items: list[dict] = []
            for raw_media in reference.get("media_urls") or []:
                if not isinstance(raw_media, dict):
                    continue
                media = dict(raw_media)
                stored = archived.get(str(media.get("media_url") or ""))
                if stored:
                    media.update(stored.model_dump())
                media_items.append(media)
            reference["media_urls"] = media_items
            output.append(reference)
        return output

    items = [
        TweetListItem(
            id=str(t.id),
            tweet_id=t.tweet_id,
            author_handle=t.author_handle,
            author_name=t.author_name or "",
            content=t.content,
            published_at=t.published_at.isoformat() if t.published_at else "",
            status=t.status or "pending",
            analysis_attempts=t.analysis_attempts or 0,
            analysis_last_error=t.analysis_last_error,
            analysis_next_retry_at=(
                t.analysis_next_retry_at.isoformat()
                if t.analysis_next_retry_at else None
            ),
            analysis_started_at=(
                t.analysis_started_at.isoformat()
                if t.analysis_started_at else None
            ),
            analysis_completed_at=(
                t.analysis_completed_at.isoformat()
                if t.analysis_completed_at else None
            ),
            failure_stage=t.failure_stage,
            processing_updated_at=(
                t.processing_updated_at.isoformat()
                if t.processing_updated_at else None
            ),
            metrics=t.metrics,
            analysis=analysis_map.get(str(t.id)),
            media=media_map.get(str(t.id), []),
            tweet_type=t.tweet_type or "original",
            conversation_tweet_id=t.conversation_tweet_id,
            in_reply_to_tweet_id=t.in_reply_to_tweet_id,
            quoted_tweet_id=t.quoted_tweet_id,
            reposted_tweet_id=t.reposted_tweet_id,
            referenced_tweets=references_with_archived_media(t),
        )
        for t in rows
    ]
    return TweetListResponse(items=items, total=total)


@router.post("/import", response_model=TweetImportResponse)
def import_tweets_endpoint(
    request: TweetImportRequest,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    imported, skipped, _tweet_ids = import_tweets(
        db,
        request.tweets,
        request.blogger,
        return_ids=True,
    )
    return TweetImportResponse(imported=imported, skipped=skipped)


@router.get("/{tweet_id}/media/{asset_id}")
def get_tweet_media(
    tweet_id: UUID,
    asset_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    asset = db.execute(
        select(TweetMediaAsset).where(
            TweetMediaAsset.id == asset_id,
            TweetMediaAsset.tweet_id == tweet_id,
            TweetMediaAsset.status == "downloaded",
            TweetMediaAsset.object_key.is_not(None),
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Tweet media not found")

    content = TweetMediaStorage().load(asset.object_key)
    return Response(
        content=content,
        media_type=asset.content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )
