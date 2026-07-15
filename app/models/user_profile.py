import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserProfile(Base, TimestampMixin):
    """用户客观事实档案表（一行一用户）。

    与 user_preferences 区别：
        - user_profile     : 客观事实，基本不变（名字、生日、职业、所在地）
        - user_preferences : 主观偏好，频繁变动（关注谁、看好什么、回复风格）

    设计要点：
        - user_id 作为唯一标识（主键候选键），必须来自认证用户 UUID
        - 所有字段可空，逐步收集
        - 列式结构便于 JOIN 与索引；新增稳定字段用 ALTER TABLE
        - 临时性、实验性字段仍走 user_preferences 的 JSONB
    """

    __tablename__ = "user_profile"
    __table_args__ = ({"comment": "用户客观事实档案，跨对话长期记忆"},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键 UUID",
    )
    user_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        comment="用户标识，唯一约束保证一行一用户",
    )
    name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="真实姓名"
    )
    nickname: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="昵称/网名"
    )
    occupation: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="职业/身份，如 量化交易员/散户/基金经理",
    )
    birthday: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="生日"
    )
    location: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="所在地"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="最近更新时间",
    )
