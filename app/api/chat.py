"""Multi-user multi-turn chat API.

Enterprise features:
    - Conversation CRUD with cursor-based pagination
    - Per-conversation advisory lock (single concurrent agent execution)
    - Message idempotency via client-generated message_id
    - SSE Event IDs for reconnection support
    - Content filtering middleware
    - Message mirroring to messages table for audit/query
    - Auto title generation on first message
"""
import json
import time
import uuid

from cachetools import TTLCache
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from langchain_core.messages import AIMessageChunk, ToolMessage
from loguru import logger
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.agents.chat_agent import get_chat_agent
from app.agents.llm import get_report_llm
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.deps import SessionLocal, get_db
from app.memory.compression import compress_messages, should_compress
from app.middleware.content_filter import content_filter
from app.models.user import User
from app.services.trace_service import TraceCollector
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageListResponse,
    MessageResponse,
)
from app.services.conversation_service import (
    acquire_conversation_lock,
    check_message_exists,
    create_conversation,
    delete_conversation,
    generate_title_background,
    get_conversation,
    get_last_message_preview,
    get_next_sequence,
    list_conversations,
    list_messages,
    release_conversation_lock,
    save_message,
    update_conversation,
    update_conversation_stats,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================
# Rate limiting (per-user, sliding window)
# ============================================================

_rate_cache: TTLCache = TTLCache(maxsize=1000, ttl=60)


def _check_rate_limit(user_id: str) -> bool:
    now = time.time()
    timestamps = _rate_cache.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < 60]
    if len(timestamps) >= settings.rate_limit_rpm:
        return False
    timestamps.append(now)
    _rate_cache[user_id] = timestamps
    return True


# ============================================================
# Conversation CRUD
# ============================================================

@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation_endpoint(
    req: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        conv = create_conversation(db, str(current_user.id), req.title, req.metadata)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return conv


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations_endpoint(
    status: str = Query("active"),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, next_cursor = list_conversations(db, str(current_user.id), status, limit, cursor)

    response_items = []
    for conv in items:
        preview = get_last_message_preview(db, conv.id)
        response_items.append(
            ConversationListItem(
                id=conv.id,
                title=conv.title,
                status=conv.status,
                message_count=conv.message_count,
                last_message_at=conv.last_message_at,
                last_message_preview=preview,
                created_at=conv.created_at,
            )
        )

    return ConversationListResponse(
        items=response_items,
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id, str(current_user.id))
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation_endpoint(
    conversation_id: uuid.UUID,
    req: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = update_conversation(db, conversation_id, str(current_user.id), req.title, req.metadata)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    success = delete_conversation(db, conversation_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")


# ============================================================
# Messages history
# ============================================================

@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_messages_endpoint(
    conversation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    direction: str = Query("backward"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id, str(current_user.id))
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    items, next_cursor = list_messages(db, conversation_id, limit, cursor, direction)
    return MessageListResponse(
        items=[MessageResponse.model_validate(m) for m in items],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


# ============================================================
# Chat endpoint (SSE streaming)
# ============================================================

TOOL_LABELS = {
    "fetch_and_save_profile": "正在获取博主资料...",
    "fetch_and_save_tweets": "正在采集推文...",
    "trigger_tweet_analysis": "正在提交分析任务...",
    "query_database": "正在查询数据库...",
}


@router.post("")
def chat_endpoint(
    req: ChatRequest,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user.id)
    conversation_id = req.conversation_id
    message_id = req.message_id

    logger.info(
        "Chat request: user={} conv={} msg_id={}",
        user_id,
        conversation_id,
        message_id,
    )

    # Rate limit
    if not _check_rate_limit(user_id):
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁（限制: {settings.rate_limit_rpm} 次/分钟）",
        )

    # Verify conversation ownership
    conv = get_conversation(db, conversation_id, user_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Content filter
    filter_result = content_filter.check_input(req.message, user_id)
    if filter_result.blocked:
        raise HTTPException(status_code=400, detail=filter_result.reason)

    # Idempotency check
    existing = check_message_exists(db, message_id)
    if existing:
        return _handle_cached_response(db, conversation_id, existing.sequence)

    # Advisory lock — dedicated session that lives for the generator's lifetime
    lock_session = SessionLocal()
    if not acquire_conversation_lock(lock_session, conversation_id):
        lock_session.close()
        raise HTTPException(status_code=409, detail="该会话正在处理中，请稍后再试")

    # SSE reconnection
    if last_event_id:
        release_conversation_lock(lock_session, conversation_id)
        lock_session.close()
        return _handle_reconnection(db, conversation_id, last_event_id)

    # Save human message to mirror table
    seq = get_next_sequence(db, conversation_id)
    human_token_count = len(req.message) // 4
    save_message(
        db,
        message_id=message_id,
        conversation_id=conversation_id,
        user_id=user_id,
        role="human",
        content=req.message,
        sequence=seq,
        token_count=human_token_count,
    )
    is_first_message = conv.message_count == 0
    update_conversation_stats(db, conversation_id, tokens=human_token_count)
    db.commit()

    # Trigger title generation on first message
    if is_first_message:
        generate_title_background(conversation_id, req.message)

    # Prepare agent invocation
    agent = get_chat_agent()
    thread_id = str(conversation_id)
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {"user_id": user_id, "thread_id": thread_id, "current_message": req.message},
        "run_name": f"chat:{user_id}",
        "recursion_limit": settings.agent_recursion_limit,
    }

    # Compression check
    if agent.checkpointer is not None:
        try:
            state = agent.get_state(config)
            existing_messages = (
                state.values.get("messages", []) if state.values else []
            )
            if existing_messages and should_compress(existing_messages):
                compressed = compress_messages(existing_messages, get_report_llm())
                agent.update_state(config, {"messages": compressed})
                logger.info("[Chat] Compressed messages for thread {}", thread_id)
        except Exception as e:
            logger.warning("[Chat] State check failed: {}", e)

    input_data = {"messages": [("human", req.message)]}
    emitted_tools: set = set()
    chunk_index = [0]
    ai_content_parts: list[str] = []
    ai_tool_calls: list[dict] = []
    tool_results: list[dict] = []
    trace_collector = TraceCollector(conversation_id=conversation_id)

    def event_generator():
        start_time = time.perf_counter()
        tool_start_times: dict[str, float] = {}
        try:
            for stream_mode, chunk in agent.stream(
                input_data, stream_mode=["updates", "messages"], config=config
            ):
                if stream_mode == "updates":
                    for node_name, node_output in chunk.items():
                        if node_name == "tools":
                            yield {
                                "id": f"{conversation_id}:{seq + 1}:{chunk_index[0]}",
                                "event": "tool_call",
                                "data": json.dumps(
                                    {"tools": ["tools"], "label": "正在执行工具..."},
                                    ensure_ascii=False,
                                ),
                            }
                            chunk_index[0] += 1

                            msgs = node_output.get("messages", [])
                            for tool_msg in msgs:
                                if isinstance(tool_msg, ToolMessage):
                                    t_name = tool_msg.name or "unknown"
                                    t_start = tool_start_times.pop(t_name, start_time)
                                    latency = int((time.perf_counter() - t_start) * 1000)
                                    is_error = tool_msg.status == "error" if hasattr(tool_msg, "status") else False

                                    tool_results.append({
                                        "name": t_name,
                                        "content": tool_msg.content,
                                    })

                                    trace_collector.add(
                                        node_name="tools",
                                        tool_name=t_name,
                                        output=tool_msg.content,
                                        status="error" if is_error else "success",
                                        latency_ms=latency,
                                        error_detail=tool_msg.content if is_error else None,
                                    )

                elif stream_mode == "messages":
                    msg, metadata = chunk
                    if not isinstance(msg, AIMessageChunk):
                        continue
                    node = metadata.get("langgraph_node", "")
                    if node != "agent":
                        continue

                    if hasattr(msg, "tool_call_chunks") and msg.tool_call_chunks:
                        for tc in msg.tool_call_chunks:
                            tool_name = tc.get("name", "")
                            if tool_name and tool_name not in emitted_tools:
                                emitted_tools.add(tool_name)
                                tool_start_times[tool_name] = time.perf_counter()
                                tc_args = tc.get("args", {})
                                ai_tool_calls.append(
                                    {"name": tool_name, "args": tc_args}
                                )
                                trace_collector.add(
                                    node_name="agent",
                                    tool_name=tool_name,
                                    input={"args": tc_args} if isinstance(tc_args, dict) else {"args_raw": str(tc_args)},
                                    status="initiated",
                                )
                                label = TOOL_LABELS.get(
                                    tool_name, f"正在调用 {tool_name}..."
                                )
                                yield {
                                    "id": f"{conversation_id}:{seq + 1}:{chunk_index[0]}",
                                    "event": "tool_call",
                                    "data": json.dumps(
                                        {"tools": [tool_name], "label": label},
                                        ensure_ascii=False,
                                    ),
                                }
                                chunk_index[0] += 1
                        continue

                    if msg.content:
                        ai_content_parts.append(msg.content)
                        yield {
                            "id": f"{conversation_id}:{seq + 1}:{chunk_index[0]}",
                            "event": "token",
                            "data": json.dumps(
                                {"content": msg.content}, ensure_ascii=False
                            ),
                        }
                        chunk_index[0] += 1

            # Save AI response and tool messages to mirror table
            ai_content = "".join(ai_content_parts)
            ai_token_count = len(ai_content) // 4
            ai_msg_id = uuid.uuid4()
            mirror_db = SessionLocal()
            try:
                # Save tool results as tool-role messages
                tool_seq = seq + 1
                for tr in tool_results:
                    tool_seq += 1
                    save_message(
                        mirror_db,
                        message_id=uuid.uuid4(),
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="tool",
                        content=tr["content"][:4096] if tr["content"] else "",
                        sequence=tool_seq,
                        tool_calls={"name": tr["name"]},
                        token_count=len(tr.get("content", "")) // 4,
                    )

                # Save final AI response
                ai_seq = tool_seq + 1 if tool_results else seq + 1
                save_message(
                    mirror_db,
                    message_id=ai_msg_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="ai",
                    content=ai_content,
                    sequence=ai_seq,
                    tool_calls=ai_tool_calls if ai_tool_calls else None,
                    token_count=ai_token_count,
                    audit_metadata={
                        "latency_ms": int(
                            (time.perf_counter() - start_time) * 1000
                        ),
                        "model_used": settings.report_model,
                        "tokens_out": ai_token_count,
                    },
                )
                update_conversation_stats(
                    mirror_db, conversation_id, tokens=ai_token_count
                )
                mirror_db.commit()
            except Exception as e:
                logger.error("[Chat] Mirror save failed: {}", e)
                mirror_db.rollback()
            finally:
                mirror_db.close()

            # Record final agent response trace
            trace_collector.add(
                node_name="agent",
                message_id=ai_msg_id,
                output={"content_length": len(ai_content), "tool_calls_count": len(ai_tool_calls)},
                status="success",
                latency_ms=int((time.perf_counter() - start_time) * 1000),
            )
            trace_collector.flush()

            yield {
                "id": f"{conversation_id}:{ai_seq}:done",
                "event": "done",
                "data": "{}",
            }
            logger.info(
                "Chat completed: user={} conv={} latency={}ms",
                user_id,
                conversation_id,
                int((time.perf_counter() - start_time) * 1000),
            )

        except Exception as e:
            error_msg = str(e)
            is_recursion = "recursion" in error_msg.lower() or "GraphRecursionError" in type(e).__name__

            if is_recursion:
                logger.warning("[Chat] Recursion limit hit: user={} conv={}", user_id, conversation_id)
                # Graceful degradation: ask LLM to summarize from the current
                # checkpoint state without granting it any more tools.
                recovery_text = ""
                try:
                    state = agent.get_state(config)
                    history = state.values.get("messages", []) if state.values else []
                    closing_prompt = (
                        "你之前已多次调用工具但未能完成用户请求。请基于已有的工具结果，"
                        "用简洁中文给出一段直接回答用户的最终回复：1) 概述已查到的信息；"
                        "2) 说明缺失或失败的部分；3) 建议用户如何细化提问。不要再请求调用任何工具。"
                    )
                    closing_msgs = list(history) + [
                        {"role": "system", "content": closing_prompt}
                    ]
                    recovery_resp = get_report_llm().invoke(closing_msgs)
                    recovery_text = recovery_resp.content or ""
                except Exception as rec_err:
                    logger.error("[Chat] Recovery summarize failed: {}", rec_err)

                if not recovery_text:
                    recovery_text = (
                        "抱歉，本次请求涉及的工具调用过多，已自动停止。"
                        "请尝试拆分为更具体的小问题再问一次。"
                    )

                # Mirror the recovery answer as a normal AI message.
                ai_msg_id = uuid.uuid4()
                ai_seq = seq + 1
                mirror_db = SessionLocal()
                try:
                    save_message(
                        mirror_db,
                        message_id=ai_msg_id,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        role="ai",
                        content=recovery_text,
                        sequence=ai_seq,
                        tool_calls=None,
                        token_count=len(recovery_text) // 4,
                        audit_metadata={
                            "latency_ms": int((time.perf_counter() - start_time) * 1000),
                            "model_used": settings.report_model,
                            "recovery": "recursion_limit",
                        },
                    )
                    update_conversation_stats(
                        mirror_db, conversation_id, tokens=len(recovery_text) // 4
                    )
                    mirror_db.commit()
                except Exception as mirror_err:
                    logger.error("[Chat] Recovery mirror save failed: {}", mirror_err)
                    mirror_db.rollback()
                finally:
                    mirror_db.close()

                trace_collector.add(
                    node_name="agent",
                    message_id=ai_msg_id,
                    status="degraded",
                    latency_ms=int((time.perf_counter() - start_time) * 1000),
                    error_detail="recursion_limit_recovered",
                )
                trace_collector.flush()

                yield {
                    "id": f"{conversation_id}:{ai_seq}:msg",
                    "event": "message",
                    "data": json.dumps(
                        {"content": recovery_text, "message_id": str(ai_msg_id)},
                        ensure_ascii=False,
                    ),
                }
                yield {
                    "id": f"{conversation_id}:{ai_seq}:done",
                    "event": "done",
                    "data": "{}",
                }
            else:
                logger.error("Chat error: user={} err={}", user_id, e)
                trace_collector.add(
                    node_name="agent",
                    status="error",
                    latency_ms=int((time.perf_counter() - start_time) * 1000),
                    error_detail=error_msg,
                )
                trace_collector.flush()
                yield {
                    "event": "error",
                    "data": json.dumps({"error": error_msg}, ensure_ascii=False),
                }
        finally:
            try:
                release_conversation_lock(lock_session, conversation_id)
            except Exception:
                pass
            finally:
                try:
                    lock_session.close()
                except Exception:
                    pass

    return EventSourceResponse(event_generator())


# ============================================================
# Helpers
# ============================================================


def _handle_cached_response(
    db: Session, conversation_id: uuid.UUID, human_seq: int
):
    """Return cached AI response for idempotent replay."""
    items, _ = list_messages(
        db, conversation_id, limit=5, cursor=str(human_seq), direction="forward"
    )
    ai_msgs = [m for m in items if m.role == "ai"]
    if not ai_msgs:
        raise HTTPException(status_code=202, detail="消息已接收，响应生成中")

    ai_msg = ai_msgs[0]

    def replay_generator():
        yield {
            "id": f"{conversation_id}:{ai_msg.sequence}:0",
            "event": "token",
            "data": json.dumps({"content": ai_msg.content}, ensure_ascii=False),
        }
        yield {
            "id": f"{conversation_id}:{ai_msg.sequence}:done",
            "event": "done",
            "data": "{}",
        }

    return EventSourceResponse(replay_generator())


def _handle_reconnection(
    db: Session, conversation_id: uuid.UUID, last_event_id: str
):
    """Handle SSE reconnection via Last-Event-ID."""
    try:
        parts = last_event_id.split(":")
        seq = int(parts[1]) if len(parts) >= 2 else 0
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid Last-Event-ID")

    items, _ = list_messages(
        db, conversation_id, limit=10, cursor=str(seq - 1), direction="forward"
    )
    ai_msgs = [m for m in items if m.role == "ai" and m.sequence >= seq]

    if not ai_msgs:

        def waiting_generator():
            yield {
                "event": "reconnecting",
                "data": json.dumps(
                    {"status": "processing"}, ensure_ascii=False
                ),
            }

        return EventSourceResponse(waiting_generator())

    ai_msg = ai_msgs[0]

    def reconnect_generator():
        yield {
            "id": f"{conversation_id}:{ai_msg.sequence}:0",
            "event": "token",
            "data": json.dumps({"content": ai_msg.content}, ensure_ascii=False),
        }
        yield {
            "id": f"{conversation_id}:{ai_msg.sequence}:done",
            "event": "done",
            "data": "{}",
        }

    return EventSourceResponse(reconnect_generator())
