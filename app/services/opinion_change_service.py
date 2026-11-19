"""Build a personal comparison feed from already-verified author stances."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.instrument_claim import InstrumentClaim
from app.models.tweet import Tweet
from app.models.tweet_media_asset import TweetMediaAsset
from app.models.user_blogger_follow import UserBloggerFollow
from app.services.instrument_claim_service import AUTHOR_STANCE_CLAIM_TYPES, AUTHOR_STANCE_DIRECTIONS
from app.services.tweet_service import latest_tweet_analysis_id

DISPLAY_DAYS = 7
COMPARISON_DAYS = 90
KNOWN_HORIZONS = {"short", "medium", "long"}
FACTOR_FIELDS = ("risk_factors", "catalysts", "invalidation_conditions")


def _in_source(lines: list, content: str) -> list[str]:
    text = " ".join(content.split()).casefold()
    return list(dict.fromkeys(
        line.strip() for line in lines
        if isinstance(line, str) and line.strip() and " ".join(line.split()).casefold() in text
    ))


def _new_factors(claim: InstrumentClaim, tweet: Tweet, prior: InstrumentClaim, previous: Tweet) -> list[str]:
    # Literal evidence only. Paraphrased model summaries should not trigger an update.
    old = {" ".join(line.split()).casefold() for field in FACTOR_FIELDS for line in getattr(prior, field) or [] if isinstance(line, str)}
    original = " ".join(previous.content.split()).casefold()
    factors = _in_source(
        [line for field in FACTOR_FIELDS for line in getattr(claim, field) or []],
        tweet.content,
    )
    return [
        line for line in factors
        if len(line) >= 4 and (key := " ".join(line.split()).casefold()) not in old and key not in original
    ][:3]


def _snapshot(claim: InstrumentClaim, tweet: Tweet) -> dict:
    evidence = _in_source(claim.evidence or [], tweet.content)[:3]
    quote_index = tweet.content.find(evidence[0]) if evidence else -1
    start = max(0, quote_index - 100) if quote_index >= 600 else 0
    excerpt = tweet.content[start:start + 600]
    return {
        "tweet_id": str(tweet.id),
        "source_id": tweet.tweet_id,
        "author_handle": tweet.author_handle,
        "author_name": tweet.author_name or tweet.author_handle,
        "published_at": tweet.published_at.isoformat(),
        "excerpt": ("…" if start else "") + excerpt + ("…" if start + 600 < len(tweet.content) else ""),
        "direction": claim.direction,
        "thesis": claim.thesis[:400],
        "evidence": evidence,
        "media_evidence": (claim.media_evidence or [])[:3],
        "media": [],
    }


def list_opinion_changes(db: Session, user_id: UUID) -> dict:
    followed = db.scalars(
        select(func.lower(Blogger.handle)).join(UserBloggerFollow, UserBloggerFollow.blogger_id == Blogger.id)
        .where(UserBloggerFollow.user_id == user_id)
    ).all()
    response = {"items": [], "followed_count": len(followed), "display_days": DISPLAY_DAYS, "comparison_days": COMPARISON_DAYS}
    if not followed:
        return response

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(InstrumentClaim, Tweet).select_from(Tweet)
        .join(AnalysisResult, AnalysisResult.id == latest_tweet_analysis_id())
        .join(InstrumentClaim, InstrumentClaim.analysis_result_id == AnalysisResult.id)
        .where(
            func.lower(Tweet.author_handle).in_(followed),
            Tweet.published_at.between(now - timedelta(days=COMPARISON_DAYS), now),
            Tweet.tweet_type != "retweet",
            InstrumentClaim.downstream_eligible.is_(True),
            InstrumentClaim.performance_eligible.is_(True),
            InstrumentClaim.opinion_source == "author",
            InstrumentClaim.sponsor_relation.in_(("none", "unrelated")),
            InstrumentClaim.claim_type.in_(AUTHOR_STANCE_CLAIM_TYPES),
            InstrumentClaim.direction.in_(AUTHOR_STANCE_DIRECTIONS),
        )
        .options(load_only(Tweet.id, Tweet.tweet_id, Tweet.published_at, Tweet.author_handle, Tweet.author_name, Tweet.content))
        .order_by(Tweet.published_at, Tweet.id, InstrumentClaim.confidence.desc(), InstrumentClaim.claim_index)
    ).all()
    per_tweet = defaultdict(list)
    for claim, tweet in rows:
        market = (claim.instrument_snapshot.get("market") or "").upper()
        if not market:
            continue
        identity = (tweet.author_handle.lower(), market, claim.instrument_symbol, claim.instrument_snapshot.get("asset_type") or "")
        per_tweet[tweet.id, identity, claim.horizon].append((claim, tweet))

    previous_by_key = {}
    seen = set()
    changes = []
    display_since = now - timedelta(days=DISPLAY_DAYS)
    for (_, identity, horizon), opinions in per_tweet.items():
        key = (identity, horizon)
        first = identity not in seen
        seen.add(identity)
        if len({claim.direction for claim, _ in opinions}) > 1:
            previous_by_key.pop(key, None)
            continue

        claim, tweet = opinions[0]
        previous = previous_by_key.get(key) if horizon in KNOWN_HORIZONS else None
        previous_by_key[key] = (claim, tweet)
        if tweet.published_at < display_since:
            continue

        kind = "first_opinion" if first else None
        factors = []
        if previous and previous[1].published_at < tweet.published_at:
            if previous[0].direction != claim.direction:
                kind = "direction_changed"
            elif factors := _new_factors(claim, tweet, *previous):
                kind = "new_evidence"
        if kind:
            changes.append({
                "id": str(claim.id), "kind": kind, "symbol": claim.instrument_symbol,
                "market": identity[1], "horizon": horizon, "new_factors": factors,
                "current": _snapshot(claim, tweet),
                "previous": _snapshot(*previous) if previous else None,
            })

    items = list(reversed(changes[-40:]))
    snapshots = [source for item in items for source in (item["current"], item["previous"]) if source]
    if snapshots:
        by_tweet = defaultdict(list)
        for asset in db.scalars(select(TweetMediaAsset).where(
            TweetMediaAsset.tweet_id.in_({UUID(source["tweet_id"]) for source in snapshots}),
            TweetMediaAsset.status == "downloaded",
            TweetMediaAsset.object_key.is_not(None),
        ).order_by(TweetMediaAsset.created_at)).all():
            by_tweet[str(asset.tweet_id)].append({
                "id": str(asset.id), "width": asset.width, "height": asset.height, "content_type": asset.content_type,
            })
        for source in snapshots:
            source["media"] = by_tweet[source["tweet_id"]][:4]
    response["items"] = items
    return response
