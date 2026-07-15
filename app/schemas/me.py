from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.blogger import BloggerListItem


class FollowResponse(BaseModel):
    id: str
    blogger_id: str
    created_at: datetime


class BookmarkResponse(BaseModel):
    id: str
    tweet_id: str
    created_at: datetime


class FollowedBloggerListResponse(BaseModel):
    items: list[BloggerListItem]
    total: int


class BookmarkedTweetItem(BaseModel):
    id: str
    tweet_id: str
    author_handle: str
    author_name: str
    content: str
    published_at: datetime
    status: str
    metrics: dict | None = None


class BookmarkedTweetListResponse(BaseModel):
    items: list[BookmarkedTweetItem]
    total: int


class AnalysisJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["tweet_analysis", "blogger_analysis"]
    target_id: UUID


class AnalysisJobResponse(BaseModel):
    id: str
    kind: str
    target_id: str
    status: str
    error_code: str | None = None
    error_summary: str | None = None
    reused_result: bool
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AnalysisJobListResponse(BaseModel):
    items: list[AnalysisJobResponse]
    total: int
