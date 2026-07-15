from datetime import datetime

from pydantic import BaseModel

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
