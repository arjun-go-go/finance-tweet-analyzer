from datetime import datetime

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


class BloggerListItem(BaseModel):
    handle: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    followers_count: int
    market_focus: list[str] | None = None
    credibility_score: float
    verified_count: int
    pending_count: int
    hit_rate: float | None = None
    verified: bool = False
    location: str | None = None


class TopTickerItem(BaseModel):
    ticker: str
    verified: int
    hit_rate: float


class BloggerDetail(BaseModel):
    handle: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    followers_count: int
    market_focus: list[str] | None = None
    profile_updated_at: datetime | None = None
    credibility_score: float
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
