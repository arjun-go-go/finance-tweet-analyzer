import threading
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message


# ============================================================
# Advisory Lock helpers
# ============================================================

def _uuid_to_lock_keys(conversation_id: uuid.UUID) -> tuple[int, int]:
    hash_val = int(conversation_id.hex[:16], 16)
    key1 = (hash_val >> 32) & 0x7FFFFFFF
    key2 = hash_val & 0x7FFFFFFF
    return key1, key2


def acquire_conversation_lock(db: Session, conversation_id: uuid.UUID) -> bool:
    key1, key2 = _uuid_to_lock_keys(conversation_id)
    result = db.execute(
        select(func.pg_try_advisory_lock(key1, key2))
    ).scalar()
    return bool(result)


def release_conversation_lock(db: Session, conversation_id: uuid.UUID) -> None:
    key1, key2 = _uuid_to_lock_keys(conversation_id)
    db.execute(select(func.pg_advisory_unlock(key1, key2)))
    db.commit()


# ============================================================
# CRUD
# ============================================================

def create_conversation(
    db: Session,
    user_id: str,
    title: str | None = None,
    metadata: dict | None = None,
) -> Conversation:
    active_count = db.execute(
        select(func.count()).select_from(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.status == "active",
        )
    ).scalar()
    if active_count >= settings.max_sessions_per_user:
        raise ValueError(f"已达到最大会话数限制（{settings.max_sessions_per_user}）")

    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        metadata_=metadata or {},
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(
    db: Session,
    user_id: str,
    status: str = "active",
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[Conversation], str | None]:
    query = (
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.status == status)
        .order_by(Conversation.updated_at.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(Conversation.updated_at < cursor_dt)
        except ValueError:
            pass

    results = db.execute(query).scalars().all()
    has_more = len(results) > limit
    items = list(results[:limit])
    next_cursor = items[-1].updated_at.isoformat() if has_more and items else None
    return items, next_cursor


def get_conversation(
    db: Session, conversation_id: uuid.UUID, user_id: str
) -> Conversation | None:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        return None
    if conv.status == "deleted":
        return None
    return conv


def update_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    user_id: str,
    title: str | None = None,
    metadata: dict | None = None,
) -> Conversation | None:
    conv = get_conversation(db, conversation_id, user_id)
    if conv is None:
        return None
    if title is not None:
        conv.title = title
    if metadata is not None:
        conv.metadata_ = metadata
    db.commit()
    db.refresh(conv)
    return conv


def delete_conversation(
    db: Session, conversation_id: uuid.UUID, user_id: str
) -> bool:
    conv = get_conversation(db, conversation_id, user_id)
    if conv is None:
        return False
    conv.status = "deleted"
    db.commit()
    return True


# ============================================================
# Message operations
# ============================================================

def get_next_sequence(db: Session, conversation_id: uuid.UUID) -> int:
    max_seq = db.execute(
        select(func.max(Message.sequence)).where(
            Message.conversation_id == conversation_id
        )
    ).scalar()
    return (max_seq or 0) + 1


def save_message(
    db: Session,
    message_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_id: str,
    role: str,
    content: str,
    sequence: int,
    tool_calls: dict | None = None,
    tool_result: str | None = None,
    token_count: int = 0,
    audit_metadata: dict | None = None,
) -> Message:
    msg = Message(
        id=message_id,
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content,
        sequence=sequence,
        tool_calls=tool_calls,
        tool_result=tool_result,
        token_count=token_count,
        audit_metadata=audit_metadata or {},
    )
    db.add(msg)
    db.flush()
    return msg


def update_conversation_stats(
    db: Session, conversation_id: uuid.UUID, tokens: int = 0
) -> None:
    db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            message_count=Conversation.message_count + 1,
            total_tokens=Conversation.total_tokens + tokens,
            last_message_at=func.now(),
            updated_at=func.now(),
        )
    )


def check_message_exists(db: Session, message_id: uuid.UUID) -> Message | None:
    return db.execute(
        select(Message).where(Message.id == message_id)
    ).scalar_one_or_none()


def list_messages(
    db: Session,
    conversation_id: uuid.UUID,
    limit: int = 50,
    cursor: str | None = None,
    direction: str = "backward",
) -> tuple[list[Message], str | None]:
    query = select(Message).where(Message.conversation_id == conversation_id)

    if direction == "backward":
        query = query.order_by(Message.sequence.desc())
        if cursor:
            try:
                cursor_seq = int(cursor)
                query = query.where(Message.sequence < cursor_seq)
            except ValueError:
                pass
    else:
        query = query.order_by(Message.sequence.asc())
        if cursor:
            try:
                cursor_seq = int(cursor)
                query = query.where(Message.sequence > cursor_seq)
            except ValueError:
                pass

    query = query.limit(limit + 1)
    results = db.execute(query).scalars().all()
    has_more = len(results) > limit
    items = list(results[:limit])

    if direction == "backward":
        items = list(reversed(items))

    next_cursor = str(results[limit - 1].sequence) if has_more else None
    return items, next_cursor


def get_last_message_preview(
    db: Session, conversation_id: uuid.UUID
) -> str | None:
    msg = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "ai")
        .order_by(Message.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
    if msg and msg.content:
        return msg.content[:80]
    return None


# ============================================================
# Title generation (background)
# ============================================================

def generate_title_background(
    conversation_id: uuid.UUID, first_message: str
) -> None:
    def _run():
        from app.agents.llm import get_signal_llm

        try:
            llm = get_signal_llm()
            prompt = (
                "根据以下用户消息，生成一个不超过20字的中文对话标题（不要引号）：\n"
                f"{first_message[:200]}"
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            title = response.content.strip().strip("\"'""''")[:50]

            db = SessionLocal()
            try:
                db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(title=title)
                )
                db.commit()
                logger.info(
                    "[TitleGen] Generated: conv={} title={}",
                    conversation_id,
                    title,
                )
            finally:
                db.close()
        except Exception as e:
            logger.error("[TitleGen] Failed: conv={} err={}", conversation_id, e)

    threading.Thread(target=_run, daemon=True).start()
