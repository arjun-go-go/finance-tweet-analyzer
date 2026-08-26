from typing import Literal

from pydantic import BaseModel, Field


InstrumentVerificationStatus = Literal[
    "verified",
    "unverified",
    "ambiguous",
    "unsupported",
    "invalid",
    "provider_unavailable",
    "manual_corrected",
]


class InstrumentProviderEvidence(BaseModel):
    provider: str
    status: Literal["matched", "no_match", "supporting_match", "unavailable", "not_applicable"]
    detail: str = ""


class InstrumentVerification(BaseModel):
    schema_version: str = "v1"
    status: InstrumentVerificationStatus
    reason_code: str
    reason: str
    is_verified: bool = False
    downstream_eligible: bool = False
    tradable: bool = False
    listing_status: str = "unverified"
    authoritative_source: str | None = None
    sources: list[str] = Field(default_factory=list)
    evidence: list[InstrumentProviderEvidence] = Field(default_factory=list)
    validated_at: str
