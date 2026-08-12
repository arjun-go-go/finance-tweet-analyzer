from datetime import datetime

from pydantic import BaseModel


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
