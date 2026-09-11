from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"]
    note: str | None = None


class ExcludePredictionRequest(BaseModel):
    reason: str


class CorrectInstrumentRequest(BaseModel):
    symbol: str
    name: str
    asset_type: Literal["equity", "crypto", "commodity"]
    market: Literal["CN", "HK", "US", "CRYPTO", "COMMODITY"]
    reason: str
    context_terms: list[str] = Field(default_factory=list)


class ValidateInstrumentRequest(BaseModel):
    symbol: str
    name: str
    asset_type: Literal["equity", "crypto", "commodity"]
    market: Literal["CN", "HK", "US", "CRYPTO", "COMMODITY"]


class PredictionTweet(BaseModel):
    id: str
    content: str
    published_at: datetime | None = None


class PredictionItem(BaseModel):
    id: str
    blogger_handle: str | None = None
    ticker: str
    sentiment: str
    prediction_type: str
    target_spec: dict = Field(default_factory=dict)
    temporal_expression: str | None = None
    investment_horizon: str
    horizon_source: str
    time_confidence: float
    published_at: datetime | None = None
    verifiable_at: datetime | None = None
    verifier_type: str
    scoring_eligible: bool
    verification_policy_version: str
    verdict: str | None = None
    score: float | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    note: str | None = None
    instrument_snapshot: dict | None = None
    market_verification: dict | None = None
    tweet: PredictionTweet


VERDICT_TO_SCORE: dict[str, float] = {
    "correct": 1.0,
    "partial": 0.5,
    "incorrect": 0.0,
}
