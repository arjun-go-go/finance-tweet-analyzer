import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserPreference(Base, TimestampMixin):
    """用户长期偏好记忆表。

    每行 = 一个用户的一类偏好。通过 (user_id, preference_type) 唯一约束保证幂等 upsert。
    value 用 JSONB 存储不同结构的偏好内容，schema 由 preference_type 决定。

    preference_type 取值:
        - watched_bloggers   : {"handles": ["qinbafrank", "LinQingV"]}
        - interested_tickers : {"tickers": ["BTC", "MRVL"]}
        - reply_style        : {"style": "concise" | "detailed"}
        - identity           : {"value": "量化交易员"}
        - investment_style   : {"value": "偏好半导体、短线"}
    """

    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "preference_type", name="uq_user_pref_type"),
        {"comment": "用户长期偏好记忆表，跨对话生效"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键 UUID",
    )
    user_id: Mapped[str] = mapped_column(
        String(128),
        index=True,
        default="default",
        comment="用户标识，单用户模式固定为 default，多用户时填实际 user_id",
    )
    preference_type: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="偏好类型：watched_bloggers/interested_tickers/reply_style/identity/investment_style",
    )
    value: Mapped[dict] = mapped_column(
        JSONB,
        comment="偏好内容，JSON 结构由 preference_type 决定",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="最近更新时间，每次 upsert 自动刷新",
    )
