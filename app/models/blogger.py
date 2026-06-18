import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Blogger(Base, TimestampMixin):
    __tablename__ = "bloggers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    handle: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(512), default=None)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    market_focus: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=None)
    credibility_score: Mapped[float] = mapped_column(Float, default=50.0)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0)
    correct_predictions: Mapped[float] = mapped_column(Float, default=0.0)
    profile_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    twitter_user_id: Mapped[str | None] = mapped_column(
        String(64), index=True, default=None
    )
    location: Mapped[str | None] = mapped_column(String(256), default=None)
    tweets_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    favorites_count: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_url: Mapped[str | None] = mapped_column(String(512), default=None)
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    fetch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
