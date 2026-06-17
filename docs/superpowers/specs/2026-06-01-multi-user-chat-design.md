# Multi-User Multi-Turn Chat — Design Spec

> Sub-spec of `finance-tweet-analyzer`. Upgrades the chat system from single-thread-per-user to a full enterprise-grade multi-session conversation platform.

## Goals

- 每个用户可创建、列出、切换、删除多个独立对话（类似 ChatGPT 左侧会话列表）
- 消息持久化：Checkpointer 管理 Agent 状态 + messages 镜像表支持查询/审计/导出
- 生产级可靠性：幂等、并发锁、断连恢复、超时保护
- 多层限流与安全控制
- 可观测性：结构化日志 + 审计

## Non-Goals

- 多租户（tenant_id）隔离 — 当前单租户，预留字段但不实现
- Redis 热层缓存 — 当前流量下 PG 直查足够，架构预留
- Cold storage 归档 — 预留接口但不实现自动归档
- WebSocket 替代 SSE — 保持现有 SSE 方案
- 前端实现 — 本 spec 仅覆盖后端 API

## Decisions

| Topic | Decision |
|---|---|
| 状态存储 | Checkpointer（Agent state）+ messages 表（镜像/审计） |
| 会话 ID | UUID v4，直接作为 LangGraph `thread_id` |
| 并发控制 | PG Advisory Lock per conversation |
| 消息幂等 | 客户端生成 `message_id`（UUID），服务端 UNIQUE 约束去重 |
| 标题生成 | 首轮消息完成后异步生成，LLM 摘要 |
| 限流 | per-user RPM（现有）+ per-session 并发 1 |
| 内容安全 | 预留 `content_filter` 中间件接口，初版不实现过滤规则 |
| 审计 | messages 表 + `audit_metadata` JSON 字段 |
| 分页 | Cursor-based pagination（基于 `created_at` + `id`） |
| SSE 断连 | Event ID = message sequence number，客户端 Last-Event-ID 重连 |

---

## §1 Data Model

### New table: `conversations`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | 同时作为 LangGraph thread_id |
| user_id | VARCHAR(128) INDEX | 会话所有者 |
| title | VARCHAR(256) NULL | 自动生成或用户自定义 |
| status | VARCHAR(16) DEFAULT 'active' | active / archived / deleted |
| message_count | INT DEFAULT 0 | 消息计数（冗余，加速列表查询） |
| total_tokens | INT DEFAULT 0 | 累计 token 消耗 |
| last_message_at | TIMESTAMP WITH TZ NULL | 最后一条消息时间 |
| metadata | JSONB DEFAULT '{}' | 扩展字段（model、preferences snapshot 等） |
| created_at | TIMESTAMP WITH TZ | server_default=now() |
| updated_at | TIMESTAMP WITH TZ | onupdate=now() |

Indexes:
- `ix_conversations_user_status` — (user_id, status) 列表查询
- `ix_conversations_user_updated` — (user_id, updated_at DESC) 排序

### New table: `messages`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | 客户端生成，幂等去重 |
| conversation_id | UUID FK → conversations.id INDEX | |
| user_id | VARCHAR(128) INDEX | 冗余，审计用 |
| role | VARCHAR(16) | human / ai / system / tool |
| content | TEXT | 消息正文 |
| tool_calls | JSONB NULL | AI 消息的工具调用记录 |
| tool_result | TEXT NULL | 工具返回结果 |
| token_count | INT DEFAULT 0 | 本条消息 token 估算 |
| sequence | INT | 会话内顺序号（单调递增） |
| parent_id | UUID NULL | 预留：支持 branching/regenerate |
| audit_metadata | JSONB DEFAULT '{}' | IP、User-Agent、trace_id 等 |
| created_at | TIMESTAMP WITH TZ | server_default=now() |

Indexes:
- `ix_messages_conv_seq` — (conversation_id, sequence) 主查询路径
- `uq_messages_id` — UNIQUE(id) 幂等保证

Constraints:
- `UNIQUE(conversation_id, sequence)` — 防止乱序

---

## §2 API Design

Base path: `/api/chat`

### 2.1 Conversation CRUD

#### `POST /api/chat/conversations`

创建新会话。

```json
// Request
{
    "user_id": "user_123",
    "title": null,           // 可选，null 则首轮自动生成
    "metadata": {}           // 可选
}
// Response 201
{
    "id": "uuid",
    "user_id": "user_123",
    "title": null,
    "status": "active",
    "message_count": 0,
    "created_at": "2026-06-01T10:00:00Z"
}
```

#### `GET /api/chat/conversations?user_id=xxx&status=active&limit=20&cursor=xxx`

列出用户会话，按 `updated_at DESC` 排序，cursor-based 分页。

```json
// Response 200
{
    "items": [
        {
            "id": "uuid",
            "title": "BTC 趋势分析",
            "status": "active",
            "message_count": 12,
            "last_message_at": "2026-06-01T10:30:00Z",
            "last_message_preview": "分析完成：共分析 5 条推文...",
            "created_at": "2026-06-01T10:00:00Z"
        }
    ],
    "next_cursor": "xxx",
    "has_more": true
}
```

#### `GET /api/chat/conversations/{conversation_id}`

获取会话详情（不含消息列表，消息用独立端点）。

#### `PATCH /api/chat/conversations/{conversation_id}`

更新标题或 metadata。

```json
// Request
{
    "title": "新标题",
    "metadata": {"pinned": true}
}
```

#### `DELETE /api/chat/conversations/{conversation_id}`

软删除（status → deleted）。不物理删除 checkpointer 数据（支持恢复）。

---

### 2.2 Messages

#### `GET /api/chat/conversations/{conversation_id}/messages?limit=50&cursor=xxx&direction=backward`

获取会话消息历史。默认从最新往前翻页。

```json
// Response 200
{
    "items": [
        {
            "id": "msg_uuid",
            "role": "human",
            "content": "帮我分析 @elonmusk 最新推文",
            "tool_calls": null,
            "sequence": 1,
            "token_count": 25,
            "created_at": "2026-06-01T10:01:00Z"
        },
        {
            "id": "msg_uuid_2",
            "role": "ai",
            "content": "好的，我先获取博主资料...",
            "tool_calls": [{"name": "fetch_and_save_profile", "args": {"blogger_handle": "elonmusk"}}],
            "sequence": 2,
            "token_count": 80,
            "created_at": "2026-06-01T10:01:02Z"
        }
    ],
    "next_cursor": "xxx",
    "has_more": false
}
```

---

### 2.3 Chat (Modified)

#### `POST /api/chat`

发送消息并获取流式响应。**`conversation_id` 变为必填**。

```json
// Request
{
    "conversation_id": "uuid",       // 必填
    "message_id": "client_uuid",     // 必填，幂等键
    "user_id": "user_123",
    "message": "帮我分析 @elonmusk"
}
// Response: SSE stream (unchanged format)
```

**变更点**：
1. `conversation_id` 必填（前端先创建会话再发消息）
2. `message_id` 必填（幂等去重）
3. 移除 `history` 字段（历史由 checkpointer 管理）
4. SSE Event 增加 `id` 字段（sequence number，支持断连恢复）

---

## §3 并发控制与幂等

### 3.1 会话级并发锁

同一会话同一时刻只能有一个 Agent 执行。使用 PG Advisory Lock：

```python
def acquire_conversation_lock(conn, conversation_id: UUID) -> bool:
    """Non-blocking advisory lock. Returns True if acquired."""
    # Convert UUID to two int32 for pg_try_advisory_lock
    hash_val = int(conversation_id.hex[:16], 16)
    key1 = hash_val >> 32 & 0x7FFFFFFF
    key2 = hash_val & 0x7FFFFFFF
    result = conn.execute(
        "SELECT pg_try_advisory_lock(%s, %s)", [key1, key2]
    ).scalar()
    return result

def release_conversation_lock(conn, conversation_id: UUID):
    hash_val = int(conversation_id.hex[:16], 16)
    key1 = hash_val >> 32 & 0x7FFFFFFF
    key2 = hash_val & 0x7FFFFFFF
    conn.execute("SELECT pg_advisory_unlock(%s, %s)", [key1, key2])
```

客户端收到 409 Conflict 时应显示"上一条消息正在处理中"。

### 3.2 消息幂等

1. 客户端为每条消息生成 UUID（`message_id`）
2. 服务端先查 `messages` 表是否存在该 ID
3. 存在 → 返回已缓存的响应（不重新执行 Agent）
4. 不存在 → 正常执行，写入结果

```python
existing = db.execute(
    select(Message).where(Message.id == req.message_id)
).scalar_one_or_none()
if existing:
    # Return cached response from messages table
    return cached_response(existing.conversation_id, existing.sequence)
```

---

## §4 消息镜像同步

Agent 执行过程中，消息写入两个地方：

1. **Checkpointer** — LangGraph 自动管理（state snapshot）
2. **Messages 表** — 在 Agent 执行前后显式写入

```
用户消息到达
  → 写入 messages 表 (role=human, sequence=N)
  → 更新 conversations.message_count / last_message_at
  → 调用 agent.stream()
  → Agent 完成后提取 AI 回复
  → 写入 messages 表 (role=ai, sequence=N+1)
  → 如有 tool_calls，同步写入 (role=tool, sequence=N+2...)
```

**一致性保证**：
- 写入 messages 表和 checkpointer 在同一个请求内完成
- 如果 Agent 执行中断（超时/异常），human 消息已入库但无 AI 回复 — 客户端可据此判断需要重试
- Checkpointer 是 source of truth（Agent 状态恢复），messages 表是 query/audit 视图

---

## §5 自动标题生成

会话创建时 `title=NULL`。第一轮 AI 回复完成后，异步生成标题：

```python
async def generate_title(conversation_id: UUID, first_message: str):
    """Background task: generate conversation title from first message."""
    llm = get_signal_llm()  # 轻量模型即可
    prompt = f"根据以下用户消息，生成一个不超过20字的中文对话标题（不要引号）：\n{first_message[:200]}"
    response = llm.invoke([HumanMessage(content=prompt)])
    title = response.content.strip()[:50]
    
    db = SessionLocal()
    try:
        db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title)
        )
        db.commit()
    finally:
        db.close()
```

触发条件：`conversation.message_count == 0`（首轮消息）。

---

## §6 SSE 断连恢复

### Event ID 机制

每个 SSE event 携带 `id` 字段 = `{conversation_id}:{sequence}:{chunk_index}`：

```
id: conv_uuid:3:0
event: token
data: {"content": "好的"}

id: conv_uuid:3:1
event: token
data: {"content": "，我来"}

id: conv_uuid:3:done
event: done
data: {}
```

### 客户端重连

1. 客户端断连后携带 `Last-Event-ID` header 重连
2. 服务端解析 sequence + chunk_index
3. 如果 AI 回复已完成（messages 表有完整记录）→ 直接返回完整回复
4. 如果 Agent 仍在执行 → 返回 `event: reconnecting` 提示稍后重试

```python
@router.post("")
def chat_endpoint(req: ChatRequest, last_event_id: str | None = Header(None)):
    if last_event_id:
        return handle_reconnection(req.conversation_id, last_event_id)
    # ... normal flow
```

---

## §7 限流与预算

### 多层限流

```python
class RateLimiter:
    """Per-user rate limiting with sliding window."""
    
    limits = {
        "rpm": 30,              # requests per minute
        "tpd": 500_000,         # tokens per day
        "concurrent": 1,        # max concurrent requests per session
        "sessions": 50,         # max active sessions per user
    }
```

### Token 预算

| 级别 | 阈值 | 动作 |
|------|------|------|
| per_turn | 100K | trim_messages（现有） |
| per_session | 500K 累计 | 强制压缩旧消息 |
| per_user_day | 2M | 降级到轻量模型（signal_model）|
| per_user_day | 5M | 拒绝请求，返回 429 |

存储：`conversations.total_tokens` 累加；日预算用 Redis 或内存 TTLCache（当前规模足够）。

---

## §8 内容安全管线

预留中间件接口，初版仅做基础检查：

```python
class ContentFilter:
    """Pluggable content safety pipeline."""
    
    def check_input(self, message: str, user_id: str) -> FilterResult:
        """Check user input before Agent execution."""
        # Phase 1: 基础检查
        if len(message) > 10000:
            return FilterResult(blocked=True, reason="消息过长")
        if self._detect_prompt_injection(message):
            return FilterResult(blocked=True, reason="检测到异常输入")
        return FilterResult(blocked=False)
    
    def check_output(self, response: str) -> FilterResult:
        """Check Agent output before sending to client."""
        return FilterResult(blocked=False)  # Phase 2 实现
```

---

## §9 审计与可观测性

### 审计字段

`messages.audit_metadata` 存储：

```json
{
    "ip": "192.168.1.1",
    "user_agent": "Mozilla/5.0...",
    "trace_id": "langsmith_run_id",
    "latency_ms": 2300,
    "model_used": "anthropic/claude-opus-4.6",
    "tokens_in": 1200,
    "tokens_out": 450
}
```

### 结构化日志

所有 chat 请求携带：
- `trace_id` — LangSmith run ID
- `user_id`
- `conversation_id`
- `message_id`
- `latency_ms`
- `status` (success / error / timeout / rate_limited)

---

## §10 文件结构变更

```
finance-tweet-analyzer/app/
├── api/
│   └── chat.py                    # Modified: conversation CRUD + chat endpoint refactor
├── models/
│   ├── conversation.py            # New: Conversation ORM
│   └── message.py                 # New: Message ORM
├── schemas/
│   └── chat.py                    # New: Request/Response Pydantic models
├── services/
│   └── conversation_service.py    # New: CRUD + title generation + lock management
├── middleware/
│   └── content_filter.py          # New: Content safety pipeline (stub)
└── memory/
    ├── checkpointer.py            # Unchanged
    └── compression.py             # Minor: integrate with conversation token budget
```

Alembic migration: 1 new file creating `conversations` + `messages` tables.

---

## §11 接口权限校验

所有 API 端点校验 `user_id` 所有权：

```python
def verify_conversation_ownership(db, conversation_id: UUID, user_id: str):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user_id:
        raise HTTPException(404, "会话不存在")
    if conv.status == "deleted":
        raise HTTPException(410, "会话已删除")
    return conv
```

---

## §12 会话生命周期

```
创建 (active) → 使用中 (active, message_count++) 
             → 手动归档 (archived) → 恢复 (active)
             → 软删除 (deleted) → 30天后物理清理

自动归档条件（预留，不实现）：
- 超过 30 天无新消息
- 累计 token 超过 per_session 预算
```
