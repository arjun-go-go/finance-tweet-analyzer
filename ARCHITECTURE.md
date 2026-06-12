# Finance Tweet Analyzer - 业务流程与架构详细说明

## 项目定位

金融推文分析平台：自动抓取 Twitter KOL 推文，通过多 Agent 流水线提取投资信号、评估风险、生成可验证预测，并提供对话式交互界面。

---

## 技术栈总览

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **后端框架** | FastAPI + Uvicorn | 异步 Web 框架 |
| **数据库** | PostgreSQL (psycopg3) | 主存储 + Advisory Lock + RLS |
| **ORM** | SQLAlchemy 2.0 (DeclarativeBase) | 类型安全 ORM |
| **迁移** | Alembic | 版本化数据库迁移 |
| **Agent 框架** | LangGraph (StateGraph + ToolNode) | 有状态多 Agent 编排 |
| **LLM 网关** | OpenRouter (OpenAI 兼容接口) | 统一多模型接入 |
| **Signal 模型** | `qwen/qwen3.7-max` (temp=0.1, 30s) | 高频分类/分析 |
| **Report 模型** | `anthropic/claude-opus-4.6` (temp=0.3, 120s) | 高质量生成/对话 |
| **任务队列** | Celery 5.6 + Redis (Broker) | 分布式异步任务 |
| **状态持久化** | langgraph-checkpoint-postgres | Agent 对话状态持久化 |
| **认证** | JWT (PyJWT + bcrypt) | 无状态身份验证 |
| **推文抓取** | curl_cffi (浏览器指纹模拟) | 免 API Key 抓取 |
| **追踪** | LangSmith | 全链路 Agent 追踪 |
| **日志** | Loguru | 结构化日志 |
| **前端** | Next.js + React + TypeScript | SPA 前端 |

---

## 系统架构图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (Next.js)                                │
│                      localhost:3000 / SSE EventSource                         │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ HTTP / SSE
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Application                                  │
│                                                                                │
│  ┌─────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐ │
│  │  Auth   │  │  Tweets  │  │  Analysis    │  │  Chat(SSE) │  │Dashboard │ │
│  │  API    │  │  API     │  │  API         │  │  API       │  │  API     │ │
│  └────┬────┘  └────┬─────┘  └──────┬───────┘  └─────┬──────┘  └────┬─────┘ │
│       │             │               │                │               │       │
│  ┌────┴─────────────┴───────────────┴────────────────┴───────────────┴────┐  │
│  │                     Middleware Layer                                     │  │
│  │   Rate Limiter ← Content Filter ← JWT Auth ← CORS ← Logging          │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────────┐
            ▼                  ▼                       ▼
┌─────────────────┐  ┌─────────────────┐   ┌──────────────────┐
│   Chat Agent    │  │   SQL Agent     │   │   Celery Worker  │
│  (LangGraph)    │  │  (LangGraph)    │   │                  │
│                 │  │                  │   │  ┌────────────┐  │
│  ReAct + Tools  │  │  NL→SQL→Exec    │   │  │ Supervisor │  │
│  ┌───────────┐  │  │  ┌───────────┐  │   │  │ (LangGraph)│  │
│  │ToolNode   │  │  │  │ AST Guard │  │   │  └─────┬──────┘  │
│  │ - Profile  │  │  │  │ - sqlglot │  │   │        │         │
│  │ - Tweets   │  │  │  │ - 白名单   │  │   │  ┌─────┴──────┐ │
│  │ - Analysis │  │  │  │ - READ ONLY│ │   │  │  Fan-out    │ │
│  │ - SQL Query│  │  │  └───────────┘  │   │  │ ┌────┐┌───┐│ │
│  └───────────┘  │  └─────────────────┘   │  │ │分析││风险││ │
└────────┬────────┘                         │  │ │Agent││Agent││ │
         │                                  │  │ └────┘└───┘│ │
         ▼                                  │  └────────────┘ │
┌─────────────────┐                         │        │         │
│  Checkpointer   │                         │        ▼         │
│  (PostgreSQL)   │                         │  ┌───────────┐  │
└─────────────────┘                         │  │Prediction │  │
                                            │  │  Agent    │  │
            ┌───────────────────────────────│──┴───────────┘  │
            ▼                               └──────────────────┘
┌──────────────────────────────────────────────────────────────┐
│                        PostgreSQL                              │
│  users │ bloggers │ tweets │ analysis_results │ predictions  │
│  conversations │ messages │ checkpoints                       │
└──────────────────────────────────────────────────────────────┘
            ▲
            │
┌───────────┴──────────┐        ┌──────────────────┐
│       Redis          │        │   Twitter/X      │
│  Celery Broker       │        │  (curl_cffi)     │
│  Distributed Locks   │        │  GraphQL API     │
│  Rate Limit Cache    │        └──────────────────┘
└──────────────────────┘
```

---

## 核心业务流程

### 流程一：用户对话 (Chat Flow)

```
用户发送消息
    │
    ▼
┌─────────────────────────────────────────┐
│ ① Rate Limit 检查 (滑动窗口, 60s/用户)    │
│ ② Content Filter (注入检测 + 长度限制)     │
│ ③ Idempotency 检查 (message_id 去重)     │
│ ④ Advisory Lock 加锁 (防并发)             │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ 保存 Human Message → messages 镜像表      │
│ 压缩检查 (>40条消息 → 摘要压缩)           │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         Chat Agent (LangGraph)           │
│                                          │
│  init_context → agent ↔ tools → prefs   │
│                                          │
│  Agent 决策循环:                          │
│   - 需要数据? → 调用 Tools               │
│   - 可以回答? → 生成响应                  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ SSE 流式推送事件:                         │
│  • tool_call: 工具调用通知               │
│  • token: 逐 token 流式响应              │
│  • done: 完成信号                        │
│  • error: 错误信息                       │
└─────────────────┬───────────────────────┘
                  │
                  ▼
保存 AI/Tool Messages → 释放 Advisory Lock
```

**Chat Agent 可用工具:**

| 工具 | 功能 | 熔断器 |
|------|------|--------|
| `fetch_and_save_profile` | 抓取 Twitter 用户画像 | `twitter_api` |
| `fetch_and_save_tweets` | 抓取最近推文(1-3页) | `twitter_api` |
| `preview_tweet_analysis` | 预览分析统计(需确认) | — |
| `confirm_tweet_analysis` | 提交 Celery 分析任务 | — |
| `query_database` | 自然语言查询数据库 | `sql_agent` |

---

### 流程二：推文分析 (Analysis Pipeline)

#### 触发方式

| 方式 | 入口 | 场景 |
|------|------|------|
| 对话触发 | Chat → `confirm_tweet_analysis` → Celery | 用户主动发起 |
| 定时触发 | Celery Beat → `auto_analysis_task` | 自动扫描待分析推文 |
| API 触发 | `POST /api/analysis/trigger` | 管理员手动触发 |

#### 执行流程

```
Celery Worker 接收任务
    │
    ▼
获取 Redis 分布式锁 (per-blogger)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│            Supervisor Agent (LangGraph)                │
│                                                        │
│  ① supervisor_classify                                │
│     - LLM 分类每条推文:                                │
│       investment / market_commentary /                 │
│       risk_warning / non_financial                     │
│     - 决定哪些需要深度分析/风险评估                      │
│                                                        │
│  ② Fan-out 并行 (LangGraph Send)                      │
│     ┌──────────────────┬──────────────────┐           │
│     │  Analysis Agent  │   Risk Agent     │           │
│     │                  │                  │           │
│     │  提取:           │  评估:           │           │
│     │  - 涉及标的      │  - 风险类别      │           │
│     │  - 情绪倾向      │  - 严重程度      │           │
│     │  - 投资周期      │  - 紧急程度      │           │
│     │  - 关键观点      │  - 关联标的      │           │
│     │  - 置信度        │  - 风险摘要      │           │
│     └────────┬─────────┴────────┬─────────┘           │
│              │                  │                      │
│  ③ supervisor_merge (Fan-in 合并)                     │
│              │                                         │
│  ④ supervisor_finalize                                │
│     - 生成 Ticker 汇总                                │
│     - 更新 tweet.status = "analyzed"                  │
│     - 写入 analysis_results                           │
│     - 标记 prediction_status = "pending"              │
└──────────────────────────────────────────────────────┘
    │
    ▼
释放 Redis 分布式锁
```

---

### 流程三：预测生成 (Prediction Pipeline)

```
Celery Beat 定时触发 prediction_batch_task (每5分钟)
    │
    ▼
查询 prediction_status = "pending" 的分析结果
    │
    ▼
┌──────────────────────────────────────────────┐
│         Prediction Agent                      │
│                                               │
│  ① 标的聚合 (Ticker Aggregation)             │
│     - 相同标的多条分析 → 合并                  │
│     - 计算共识: strong_buy/buy/neutral/       │
│       sell/strong_sell                        │
│                                               │
│  ② 预测生成                                   │
│     - 设定验证时间窗口:                        │
│       short=7d, medium=30d, long=180d         │
│     - 去重: 24h 内同(博主,标的,情绪)只保留一条  │
│                                               │
│  ③ 写入 predictions 表                        │
│     - prediction_status → "done"              │
└──────────────────────────────────────────────┘
```

**共识评级算法:**
```
bullish_ratio = 看多分析数 / 总分析数

≥ 0.7 → strong_buy
≥ 0.5 → buy
bearish_ratio ≥ 0.7 → strong_sell
bearish_ratio ≥ 0.5 → sell
其他 → neutral
```

---

### 流程四：自然语言查询 (SQL Agent)

```
用户: "粉丝最多的博主是谁?"
    │
    ▼
┌──────────────────────────────────────────────────────┐
│              SQL Agent (LangGraph)                     │
│                                                        │
│  ① sql_classify (意图分类)                             │
│     - data_query: 数据查询 → 继续                     │
│     - out_of_scope: 超范围 → 直接拒绝                  │
│                                                        │
│  ② generate_sql                                       │
│     - 注入时间锚点 (解决 LLM 日期幻觉)                  │
│     - CoT 推理生成 SQL                                │
│     - 重试策略: 前2次用 signal_llm, 第3次升级 report_llm │
│                                                        │
│  ③ validate_sql (AST 安全验证)                         │
│     - sqlglot 解析 → 检查表名白名单                    │
│     - 阻止: INSERT/UPDATE/DELETE/DROP/ALTER            │
│     - 自动追加 LIMIT 20                               │
│                                                        │
│  ④ execute_sql                                        │
│     - SET TRANSACTION READ ONLY                       │
│     - SET LOCAL statement_timeout = '5000ms'          │
│     - SET LOCAL app.current_user_id (RLS)             │
│     - 执行查询 → 格式化为表格返回                      │
└──────────────────────────────────────────────────────┘
```

**SQL Agent 安全层 (纵深防御):**

```
┌─────────────────────────────────────────┐
│ Layer 1: 意图分类 (out_of_scope 直接拒绝) │
├─────────────────────────────────────────┤
│ Layer 2: 表白名单 (sqlglot AST 解析)      │
│  仅允许: bloggers, tweets, predictions,   │
│         analysis_results                  │
├─────────────────────────────────────────┤
│ Layer 3: 操作阻止 (禁止写/删/改)          │
├─────────────────────────────────────────┤
│ Layer 4: 自动 LIMIT 20                   │
├─────────────────────────────────────────┤
│ Layer 5: READ ONLY 事务                   │
├─────────────────────────────────────────┤
│ Layer 6: statement_timeout 5s            │
├─────────────────────────────────────────┤
│ Layer 7: Row-Level Security (RLS)        │
└─────────────────────────────────────────┘
```

---

## 企业级容错设计

### 1. 熔断器 (Circuit Breaker)

**三态状态机:**

```
CLOSED ──(失败≥5次)──→ OPEN ──(60s后)──→ HALF_OPEN
   ↑                                        │
   └──── 探针成功 ──────────────────────────┘
         探针失败 → 回到 OPEN
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `failure_threshold` | 5 | 触发熔断的连续失败次数 |
| `recovery_timeout` | 60s | 熔断后恢复等待时间 |
| `half_open_max_calls` | 1 | 半开状态探针请求数 |

**每个外部依赖独立熔断器:** `twitter_api`, `sql_agent` 各自独立。

### 2. 指数退避重试

```
attempt 1 → 失败 → 等待 1s
attempt 2 → 失败 → 等待 2s
attempt 3 → 失败 → record_failure() → 返回降级文本
```

### 3. 内容注入检测

| 规则 | 防御场景 |
|------|----------|
| `ignore (all )?previous instructions` | 经典 Prompt Injection |
| `you are now (a\|an) ` | 角色劫持 |
| `system\s*prompt\s*:` | System Prompt 泄露 |
| `<\s*/?\s*system\s*>` | XML 标签注入 |
| 长度 > 10000 字符 | 资源耗尽攻击 |

### 4. Advisory Lock (会话级分布式锁)

```
UUID → hash → (key1: int32, key2: int32)
pg_try_advisory_lock(key1, key2)  -- 非阻塞
pg_advisory_unlock(key1, key2)    -- 显式释放
```

- 防止同一会话并发执行 Agent
- 失败返回 HTTP 409 而非阻塞等待
- 绑定独立 DB Session，业务 commit 不会意外释放
- 进程崩溃时 PostgreSQL 自动清理

### 5. 分布式锁 (Redis)

- Celery 任务使用 Redis 锁防止同一博主重复分析
- 保证同一时刻只有一个 Worker 处理同一博主的推文

---

## 数据模型

### ER 关系图

```
┌──────────┐       ┌──────────────┐       ┌────────────────┐
│  User    │1────N│ Conversation │1────N│    Message      │
│          │       │              │       │ (audit mirror)  │
└──────────┘       └──────────────┘       └────────────────┘

┌──────────┐       ┌──────────────┐       ┌────────────────┐
│ Blogger  │1────N│    Tweet     │1────N│ AnalysisResult  │
│          │       │              │       │                 │
└──────────┘       └──────────────┘       └───────┬────────┘
                                                   │
                                                   │1
                                                   │
                                                   │N
                                            ┌──────┴───────┐
                                            │  Prediction  │
                                            └──────────────┘
```

### 核心表结构

| 表 | 主要字段 | 说明 |
|---|---|---|
| `users` | id, email, username, password_hash, status | 用户账号 |
| `bloggers` | handle, twitter_user_id, credibility_score, total/correct_predictions | Twitter KOL 画像 |
| `tweets` | tweet_id, author_handle, content, published_at, metrics(JSONB), status | 原始推文 |
| `analysis_results` | tweet_id, analysis_type, result(JSONB), model_used, confidence, prediction_status | 分析结果 |
| `predictions` | blogger_handle, ticker, sentiment, investment_horizon, verifiable_at, verdict, score | 可验证预测 |
| `conversations` | user_id, title, status, message_count, total_tokens | 对话会话 |
| `messages` | conversation_id, role, content, tool_calls(JSONB), sequence | 消息审计 |

### 状态流转

**Tweet Status:**
```
pending → analyzed
```

**Prediction Status (on AnalysisResult):**
```
pending → done / skipped / failed
```

**Prediction Verdict:**
```
(null) → correct / partial / incorrect  (人工或自动验证)
```

**Conversation Status:**
```
active → archived → deleted
```

---

## 双模型策略

```
┌─────────────────────────────────────────────────────────┐
│                    OpenRouter Gateway                     │
│                                                          │
│  ┌─────────────────────┐  ┌───────────────────────────┐ │
│  │  Signal LLM         │  │  Report LLM               │ │
│  │  qwen/qwen3.7-max   │  │  anthropic/claude-opus    │ │
│  │                     │  │                           │ │
│  │  temp=0.1, 30s      │  │  temp=0.3, 120s           │ │
│  │                     │  │                           │ │
│  │  用途:              │  │  用途:                    │ │
│  │  - 推文分类          │  │  - 用户对话               │ │
│  │  - 投资信号提取      │  │  - 报告生成               │ │
│  │  - 风险评估          │  │  - SQL 生成(重试降级)     │ │
│  │  - SQL 意图分类      │  │  - 标题生成               │ │
│  │  - 情绪判断          │  │  - 消息压缩摘要           │ │
│  └─────────────────────┘  └───────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**SQL Agent 模型升级策略:**
```
第 1-2 次重试 → signal_llm (快速, 低成本)
第 3 次重试   → report_llm (高质量, 兜底)
```

---

## 消息记忆管理

### Checkpointer (长期状态)
- 基于 `langgraph-checkpoint-postgres`
- 以 `thread_id` (conversation_id) 为键持久化完整图状态
- 支持 SSE 断连后恢复执行

### Message Compression (上下文窗口管理)
```
消息数 > 40 (COMPRESSION_THRESHOLD)
    │
    ▼
分割: older_messages + recent_10
    │
    ▼
LLM 摘要 older_messages → SystemMessage(summary)
    │
    ▼
最终上下文: [SystemMessage(摘要)] + recent_10
```

### User Profile & Preferences
- `init_context_node`: 启动时加载用户画像和偏好 (避免 N+1 查询)
- `extract_preferences_node`: 对话结束后异步提取隐式偏好

---

## API 路由总览

| 路由前缀 | 方法 | 端点 | 认证 | 说明 |
|----------|------|------|------|------|
| `/api/auth` | POST | `/register` | 无 | 用户注册 |
| `/api/auth` | POST | `/login` | 无 | 用户登录 |
| `/api/auth` | POST | `/refresh` | Refresh Token | 刷新 Access Token |
| `/api/auth` | GET | `/me` | Access Token | 获取当前用户信息 |
| `/api/tweets` | GET | `/` | Access Token | 推文列表(分页/过滤) |
| `/api/tweets` | POST | `/import` | Access Token | 批量导入推文 |
| `/api/analysis` | POST | `/trigger` | Access Token | 触发全量分析 |
| `/api/analysis` | POST | `/blogger/{handle}` | Access Token | 分析指定博主 |
| `/api/analysis` | POST | `/bloggers` | Access Token | 批量博主分析 |
| `/api/signals` | GET | `/analyses` | Access Token | 分析结果列表 |
| `/api/signals` | GET | `/ticker-summaries` | Access Token | 标的汇总 |
| `/api/bloggers` | GET | `/` | Access Token | 博主列表 |
| `/api/predictions` | GET | `/` | Access Token | 预测列表 |
| `/api/dashboard` | GET | `/overview` | Access Token | 仪表板概览 |
| `/api/chat` | POST | `/` | Access Token | SSE 流式对话 |
| `/api/chat` | POST | `/conversations` | Access Token | 创建会话 |
| `/api/chat` | GET | `/conversations` | Access Token | 会话列表(游标分页) |
| `/api/chat` | GET | `/conversations/{id}` | Access Token | 获取单个会话 |
| `/api/chat` | PATCH | `/conversations/{id}` | Access Token | 更新会话 |
| `/api/chat` | DELETE | `/conversations/{id}` | Access Token | 删除会话 |
| `/api/chat` | GET | `/conversations/{id}/messages` | Access Token | 消息历史 |
| `/api/health` | GET | `/` | 无 | 健康检查 + 熔断器状态 |

---

## 目录结构

```
finance-tweet-analyzer/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口, lifespan 生命周期
│   ├── celery_app.py              # Celery 应用 + Beat 调度配置
│   │
│   ├── core/                      # 基础设施层
│   │   ├── config.py             # pydantic-settings 统一配置
│   │   ├── database.py           # SQLAlchemy engine/session
│   │   ├── deps.py               # FastAPI 依赖注入
│   │   ├── auth.py               # JWT 认证中间件
│   │   ├── resilience.py         # 熔断器 + 指数退避
│   │   ├── logging.py            # Loguru 配置
│   │   └── tracing.py            # LangSmith 追踪设置
│   │
│   ├── api/                       # API 路由层
│   │   ├── router.py             # 路由聚合
│   │   ├── auth.py               # 认证端点
│   │   ├── tweets.py             # 推文端点
│   │   ├── analysis.py           # 分析端点
│   │   ├── signals.py            # 信号/汇总端点
│   │   ├── dashboard.py          # 仪表板端点
│   │   ├── bloggers.py           # 博主端点
│   │   ├── predictions.py        # 预测端点
│   │   └── chat.py               # 对话端点 (SSE)
│   │
│   ├── models/                    # 数据模型层 (SQLAlchemy ORM)
│   │   ├── base.py               # DeclarativeBase + TimestampMixin
│   │   ├── user.py               # 用户
│   │   ├── blogger.py            # 博主
│   │   ├── tweet.py              # 推文
│   │   ├── analysis.py           # 分析结果
│   │   ├── prediction.py         # 预测
│   │   ├── conversation.py       # 会话
│   │   └── message.py            # 消息 (审计镜像)
│   │
│   ├── schemas/                   # DTO 层 (Pydantic)
│   │   └── chat.py               # 对话相关请求/响应模型
│   │
│   ├── services/                  # 业务逻辑层
│   │   ├── auth_service.py       # 认证业务
│   │   ├── tweet_service.py      # 推文 CRUD
│   │   ├── twitter_service.py    # Twitter 抓取 (curl_cffi)
│   │   ├── blogger_service.py    # 博主管理
│   │   ├── analysis_service.py   # 分析编排
│   │   ├── prediction_service.py # 预测管理
│   │   ├── conversation_service.py # 会话 CRUD + Advisory Lock
│   │   └── trace_service.py      # Agent 追踪记录
│   │
│   ├── agents/                    # Agent 层 (LangGraph)
│   │   ├── llm.py                # 双模型工厂
│   │   ├── chat_agent.py         # 对话 Agent (ReAct)
│   │   ├── supervisor.py         # 批量分析编排器
│   │   ├── analysis_agent.py     # 投资信号提取
│   │   ├── risk_agent.py         # 风险评估
│   │   ├── prediction_agent.py   # 预测生成
│   │   ├── signal_agent.py       # (Legacy) 单条推文分析
│   │   └── sql_agent.py          # 自然语言 → SQL
│   │
│   ├── memory/                    # 记忆管理层
│   │   ├── checkpointer.py       # PostgresSaver 设置
│   │   ├── compression.py        # 消息历史摘要压缩
│   │   ├── profile.py            # 用户画像加载
│   │   └── preferences.py        # 用户偏好提取
│   │
│   ├── middleware/                # 中间件层
│   │   └── content_filter.py     # 内容注入检测 + 长度限制
│   │
│   └── scheduler/                 # 调度层
│       ├── __init__.py            # start/stop scheduler
│       ├── tasks.py               # Celery 任务定义
│       └── locks.py               # Redis 分布式锁
│
├── alembic/                       # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── frontend/                      # Next.js 前端
│   └── src/
│       ├── app/chat/page.tsx     # 聊天页面 (多会话侧边栏)
│       └── lib/api.ts            # API 客户端
│
├── alembic.ini                    # Alembic 配置
├── pyproject.toml                 # Python 依赖
└── .env                           # 环境变量
```

---

## 关键设计模式

| 模式 | 实现 | 目的 |
|------|------|------|
| **Two-Phase Tool** | preview + confirm | 防止意外触发昂贵操作 |
| **Circuit Breaker** | `@resilient_tool` | 外部依赖故障隔离 |
| **Fan-out / Fan-in** | Supervisor + Send | 并行分析提升吞吐 |
| **Defense in Depth** | SQL 7层安全 | 防止 SQL 注入/数据泄露 |
| **Advisory Lock** | pg_try_advisory_lock | 会话级并发控制 |
| **Distributed Lock** | Redis | 跨 Worker 任务去重 |
| **Message Compression** | LLM Summarize | 长对话上下文管理 |
| **Dual Model** | Signal + Report | 成本/质量平衡 |
| **SSE Reconnection** | Last-Event-ID | 断连恢复 |
| **Idempotency** | Client message_id | 消息去重 |
| **Cursor Pagination** | updated_at / sequence | 高性能分页 |
| **Background Title** | threading.Thread | 非阻塞标题生成 |
