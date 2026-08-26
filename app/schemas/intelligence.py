from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IntelligenceEvidence(BaseModel):
    source_type: str
    source_id: str
    author: str
    published_at: datetime
    excerpt: str
    source_url: str


class IntelligenceScoreBreakdown(BaseModel):
    relevance: int
    freshness: int
    confidence: int
    credibility: int
    risk: int
    corroboration: int
    quality_penalty: int
    total: int


class IntelligenceFeedItem(BaseModel):
    id: str
    kind: str
    title: str
    summary: str
    direction: str
    tickers: list[str]
    author: str
    confidence: float
    source_credibility: float
    importance_score: int
    score_breakdown: IntelligenceScoreBreakdown
    score_explanation: list[str]
    risk_factors: list[str]
    key_points: list[str]
    published_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    time_bucket: str
    lifecycle: str
    event_count: int
    match_reasons: list[str]
    feed_bucket: str
    corroboration_count: int
    evidence: IntelligenceEvidence
    supporting_evidence: list[IntelligenceEvidence]


class IntelligenceFeedContext(BaseModel):
    followed_bloggers: int
    tracked_tickers: int
    personalized: bool
    fallback_to_market: bool
    candidate_total: int
    personalized_candidates: int
    market_candidates: int
    window: str
    kind: str
    generated_at: datetime


class IntelligenceFeedResponse(BaseModel):
    items: list[IntelligenceFeedItem]
    total: int
    context: IntelligenceFeedContext


class IntelligenceDigestMetrics(BaseModel):
    signal_count: int
    personalized_count: int
    source_count: int
    ticker_count: int
    opinion_count: int
    news_count: int
    risk_count: int
    reversal_count: int
    corroborated_count: int


class IntelligenceDigestResponse(BaseModel):
    status: str
    title: str
    executive_summary: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    metrics: IntelligenceDigestMetrics
    highlights: list[IntelligenceFeedItem]
    attention: list[IntelligenceFeedItem]
    context: IntelligenceFeedContext
    methodology: str


class IntelligenceTweetDetail(BaseModel):
    id: str
    tweet_id: str
    author_handle: str
    author_name: str
    content: str
    published_at: datetime
    relationship: str
    tweet_type: str
    conversation_tweet_id: str | None = None
    in_reply_to_tweet_id: str | None = None
    quoted_tweet_id: str | None = None
    reposted_tweet_id: str | None = None
    referenced_tweets: list[dict] = Field(default_factory=list)
    source_url: str


class IntelligenceMediaDetail(BaseModel):
    id: str
    tweet_id: str
    width: int | None = None
    height: int | None = None
    content_type: str | None = None
    status: str
    error_detail: str | None = None
    analysis_status: str | None = None
    analysis: dict | None = None


class IntelligenceDetailResponse(BaseModel):
    item: IntelligenceFeedItem
    tweet: IntelligenceTweetDetail
    thread: list[IntelligenceTweetDetail]
    media: list[IntelligenceMediaDetail]
    analysis: dict
    instruments: list[dict]
    predictions: list[dict]
    audit: list[dict]


class IntelligenceCorrectionRequest(BaseModel):
    category: Literal[
        "author_attribution",
        "instrument",
        "direction",
        "context",
        "image",
        "other",
    ]
    note: str = Field(min_length=2, max_length=1000)


class IntelligenceCorrectionResponse(BaseModel):
    id: str
    topic_id: str
    category: str
    status: str
    created_at: datetime
