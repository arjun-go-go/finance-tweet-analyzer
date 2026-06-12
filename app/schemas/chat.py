import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================
# Conversation schemas
# ============================================================

class ConversationCreate(BaseModel):
    title: str | None = None
    metadata: dict = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    title: str | None = None
    metadata: dict | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    title: str | None
    status: str
    message_count: int
    total_tokens: int
    last_message_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    message_count: int
    last_message_at: datetime | None
    last_message_preview: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    next_cursor: str | None = None
    has_more: bool = False


# ============================================================
# Message schemas
# ============================================================

class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tool_calls: list[dict] | dict | None = None
    sequence: int
    token_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None = None
    has_more: bool = False


# ============================================================
# Chat request (modified)
# ============================================================

class ChatRequest(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    message: str
