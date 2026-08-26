from datetime import datetime

from pydantic import BaseModel

from app.schemas.blogger import BloggerListItem


class FollowResponse(BaseModel):
    id: str
    blogger_id: str
    created_at: datetime


class FollowedBloggerListResponse(BaseModel):
    items: list[BloggerListItem]
    total: int
