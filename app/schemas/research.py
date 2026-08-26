from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ResearchTopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    research_question: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default="deep", pattern="^(quick|deep)$")
    tickers: list[str] = []
    source_scope: list[str] = []
    time_range: str = "1w"
    conversation_id: UUID | None = None


class ResearchEvidenceCreate(BaseModel):
    evidence_key: str
    source_type: str
    source_id: str
    tickers: list[str] = []
    author: str = ""
    published_at: datetime | None = None
    excerpt: str
    source_url: str = ""
    sentiment: str = ""
    verification_status: str = "indexed"
    relevance_score: float = 0.0
    metadata: dict = {}


class ResearchConclusionCreate(BaseModel):
    conclusion: str
    thesis: str = ""
    counter_evidence: str = ""
    risks: list = []
    evidence_keys: list[str] = []
    confidence: float = Field(default=0.0, ge=0, le=1)


class ResearchMonitorUpdate(BaseModel):
    enabled: bool
    frequency: str = Field(default="weekly", pattern="^(daily|weekly)$")


class ResearchTopicResponse(BaseModel):
    id: UUID
    user_id: UUID
    conversation_id: UUID | None
    title: str
    research_question: str
    mode: str
    status: str
    tickers: list[str]
    source_scope: list[str]
    time_range: str
    current_conclusion: str | None
    monitor_enabled: bool
    monitor_frequency: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ResearchWorkspaceResponse(BaseModel):
    topic: ResearchTopicResponse
    evidence: list[dict]
    conclusions: list[dict]
