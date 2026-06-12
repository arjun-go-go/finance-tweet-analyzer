from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VerifyRequest(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"]
    note: str | None = None


class PredictionTweet(BaseModel):
    id: str
    content: str
    published_at: datetime | None = None


class PredictionItem(BaseModel):
    id: str
    ticker: str
    sentiment: str
    investment_horizon: str
    published_at: datetime | None = None
    verifiable_at: datetime | None = None
    verdict: str | None = None
    score: float | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    note: str | None = None
    tweet: PredictionTweet


VERDICT_TO_SCORE: dict[str, float] = {
    "correct": 1.0,
    "partial": 0.5,
    "incorrect": 0.0,
}
