from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BloggerProfile(BaseModel):
    """Profile fields a caller can upsert (handle is the key)."""
    handle: str
    name: str = ""
    bio: str | None = None
    avatar_url: str | None = None
    followers_count: int = 0
    market_focus: list[str] | None = None
    twitter_user_id: str | None = None
    location: str | None = None
    tweets_count: int = 0
    following_count: int = 0
    favorites_count: int = 0
    joined_at: datetime | None = None
    verified: bool = False
    protected: bool = False
    profile_url: str | None = None


class BloggerOnboardRequest(BaseModel):
    handle: str


class BloggerOnboardResponse(BaseModel):
    id: str
    handle: str
    name: str
    avatar_url: str | None = None
    followed: bool
    fetch_enabled: bool
    initial_fetch_queued: bool


class BloggerListItem(BaseModel):
    id: str
    handle: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    followers_count: int
    market_focus: list[str] | None = None
    credibility_score: float
    score_status: str = "no_data"
    score_label: str = "暂无已验证预测"
    sample_confidence: float = 0.0
    raw_accuracy: float | None = None
    verified_samples: int = 0
    verified_count: int
    pending_count: int
    hit_rate: float | None = None
    verified: bool = False
    location: str | None = None
    fetch_enabled: bool = False
    last_fetched_at: datetime | None = None
    last_activity_at: datetime | None = None
    collected_tweets: int = 0
    analyzed_tweets: int = 0
    processing_tweets: int = 0
    failed_tweets: int = 0
    ingestion_stage: Literal["syncing", "analyzing", "ready", "attention", "paused"] = "syncing"


class BloggerIngestionStatus(BaseModel):
    handle: str
    stage: Literal["syncing", "analyzing", "ready", "attention", "paused"]
    message: str
    progress: int
    fetch_enabled: bool
    last_fetched_at: datetime | None = None
    last_activity_at: datetime | None = None
    collected_tweets: int = 0
    analyzed_tweets: int = 0
    processing_tweets: int = 0
    failed_tweets: int = 0


class TopTickerItem(BaseModel):
    ticker: str
    verified: int
    hit_rate: float


class BloggerDetail(BaseModel):
    id: str
    handle: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    followers_count: int
    market_focus: list[str] | None = None
    profile_updated_at: datetime | None = None
    credibility_score: float
    score_status: str = "no_data"
    score_label: str = "暂无已验证预测"
    sample_confidence: float = 0.0
    raw_accuracy: float | None = None
    verified_samples: int = 0
    verified_count: int
    pending_count: int
    hit_rate_overall: float | None = None
    hit_rate_by_sentiment: dict[str, float | None]
    top_tickers: list[TopTickerItem]
    recent_verified: list[dict]
    twitter_user_id: str | None = None
    location: str | None = None
    tweets_count: int = 0
    following_count: int = 0
    favorites_count: int = 0
    joined_at: datetime | None = None
    verified: bool = False
    protected: bool = False
    profile_url: str | None = None
    fetch_enabled: bool = False
    last_fetched_at: datetime | None = None


class BloggerRow(BaseModel):
    """Full Blogger row for upsert response."""
    handle: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    followers_count: int
    market_focus: list[str] | None = None
    profile_updated_at: datetime | None = None
    twitter_user_id: str | None = None
    location: str | None = None
    tweets_count: int = 0
    following_count: int = 0
    favorites_count: int = 0
    joined_at: datetime | None = None
    verified: bool = False
    protected: bool = False
    profile_url: str | None = None
