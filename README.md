# Finance Tweet Analyzer

> Enterprise-grade financial tweet analysis platform powered by LangGraph multi-agent orchestration, hybrid RAG retrieval, and real-time SSE streaming.

English | [中文](#中文文档)

---

## Overview

A production-ready full-stack platform for financial intelligence analysis from social media. The system combines **LangGraph stateful agent pipelines**, **hybrid RAG retrieval** (semantic + keyword + rerank), and **async Celery task processing** to deliver structured research reports, conversational Q&A, and automated ticker tracking.

Built for scenarios requiring high-throughput data ingestion, multi-model LLM orchestration, fault-tolerant async processing, and real-time user-facing streaming.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Next.js 14 Frontend                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────┐  │
│  │Dashboard│ │  Chat   │ │Documents│ │ Reports │ │   Tracking   │  │
│  │(Overview│ │(SSE     │ │(Upload/ │ │(SSE     │ │(Subscriptions│  │
│  │+Trigger)│ │ Stream) │ │ Search) │ │ Stream) │ │  + Reports)  │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └──────┬───────┘  │
└───────┼───────────┼───────────┼───────────┼─────────────┼──────────┘
        │           │           │           │             │ HTTPS
┌───────▼───────────▼───────────▼───────────▼─────────────▼──────────┐
│                     FastAPI API Gateway                             │
│  JWT Auth · Rate Limiting · Access Logging · CORS · Health Check    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐  ┌──────────▼──────────┐  ┌──────▼──────┐
│  Chat Agent    │  │   Report Agent      │  │ Supervisor  │
│  (ReAct +      │  │  (Plan-Execute +    │  │ (Classify   │
│   ToolNode)    │  │   Send Fan-out)     │  │  → Route)   │
└───────┬────────┘  └──────────┬──────────┘  └──────┬──────┘
        │                      │                    │
        │         ┌────────────┴────────────────────┘
        │         │
        │  ┌──────▼──────────────────────────────────┐
        │  │           RAG Pipeline                   │
        │  │  ┌────────────────────────────────────┐  │
        │  │  │     Multi-Path Retrieval            │  │
        │  │  │  ┌─────────┐ ┌─────────┐          │  │
        │  │  │  │  Chroma │ │  BM25   │          │  │
        │  │  │  │(Semantic│ │(Keyword│          │  │
        │  │  │  │ Tweet   │ │ Tweet   │          │  │
        │  │  │  │ Document│ │ Document│          │  │
        │  │  │  │ Analysis│ │         │          │  │
        │  │  │  │Structured│ │        │          │  │
        │  │  │  └────┬────┘ └────┬────┘          │  │
        │  │  │       └─────┬─────┘                │  │
        │  │  │             ▼ RRF Fusion           │  │
        │  │  │     ┌───────────────┐              │  │
        │  │  │     │ Qwen Reranker │              │  │
        │  │  │     │(quota-balanced│              │  │
        │  │  │     │ + time-decay) │              │  │
        │  │  │     └───────┬───────┘              │  │
        │  │  └─────────────┼──────────────────────┘  │
        │  └────────────────┼─────────────────────────┘
        │                   │
        │  ┌────────────────┼────────────────┐
        │  │                │                │
┌───────▼──▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐
│   PostgreSQL    │  │   Redis    │  │  ChromaDB  │
│ (Relational +   │  │ (Celery    │  │  (Vector   │
│  JSONB Reports) │  │  Broker +  │  │   Store)   │
│                 │  │  Pub/Sub)  │  │            │
└─────────────────┘  └────────────┘  └────────────┘
```

---

## Core Subsystems

### 1. Multi-Agent Pipeline (LangGraph StateGraph)

The platform runs multiple specialized LangGraph agents, each designed for a specific workflow:

| Agent | Architecture | Responsibility |
|-------|-------------|----------------|
| **Report Agent** | Plan-and-Execute + `Send` fan-out | Generates structured ticker tracking reports with 5 parallel sections |
| **Chat Agent** | ReAct + ToolNode | Conversational Q&A with tool calling (blogger lookup, tweet search, document RAG, report generation) |
| **Supervisor** | Classification → conditional routing | Batch tweet classification (investment / market commentary / risk warning / non-financial) |
| **Analysis Agent** | Batch concurrency + blogger context injection | Extracts tickers, sentiment, horizon, and key points from tweets with credibility feedback loop |
| **Signal Agent** | Single-call structured output | Lightweight single-tweet analysis for real-time tool calls |
| **Self-Query Agent** | Intent parsing + query rewriting | Translates natural language into structured retrieval parameters |
| **SQL Agent** | Text-to-SQL with validation | Safely queries analytical data via structured SQL generation |
| **Risk Agent** | Structured risk assessment | Evaluates portfolio and market risk factors |

**Key production patterns:**
- **Middleware pipeline** — Dynamic model routing (fast/cheap for scoring, premium for generation), runtime prompt injection, tool error interception
- **Circuit breaker** — `@resilient_tool` decorator wraps each tool with exponential backoff retry + three-state circuit breaker (CLOSED → OPEN → HALF_OPEN). Prevents cascading failures when external APIs degrade
- **Token budget management** — Chat agent estimates context size before LLM calls; auto-trims history when exceeding limits
- **User isolation** — `user_id` propagated through `RunnableConfig` metadata across the entire agent graph

### 2. Report Generation System

The report agent executes a 7-stage pipeline orchestrated by LangGraph `StateGraph`:

```
parse_intent ──→ multi_retrieve (4 paths + BM25 in parallel)
                      │
                      ▼
              RRF fusion (reciprocal rank fusion, k=60)
                      │
                      ▼
              rerank (Qwen reranker + source_type quota + time decay)
                      │
                      ▼
              generate_section (5 chapters via Send fan-out)
                      │
                      ▼
              synthesize (consensus + recommendation)
```

**Report chapters** (each receives relevant evidence filtered by `source_type`):
1. **KOL Views** — Twitter sentiment and opinions from tracked bloggers
2. **Research Views** — Document and research paper insights
3. **News Updates** — Latest news and market developments
4. **Risk Alerts** — Risk factors and warning signals from analysis and structured data
5. **Historical Review** — Historical price action and pattern analysis

**Production resilience features:**
- **Node-level SSE streaming** — Each completed stage publishes to Redis `report_stream:{id}`; frontend subscribes via `EventSourceResponse` with 15s heartbeat
- **Incremental persistence** — Rerank results → DB citations; each section → DB `sections` JSONB merge; synthesis → final report status. Disconnect and reconnect yields snapshot of current progress
- **Section fault tolerance** — Failed sections carry `error` metadata instead of crashing the pipeline. Other sections continue normally
- **Global citation indexing** — Evidence numbered consistently across all sections; UI click scrolls to specific citation row
- **Source-type quota reranking** — Ensures balanced evidence distribution. Without this, tweets (typically 20+ of 30 fused results) would dominate top-8 reranked slots, starving structured data needed by the "Historical Review" chapter

### 3. RAG Engine

**Hybrid retrieval architecture:**

| Path | Method | Data Source |
|------|--------|-------------|
| Semantic (Tweet) | ChromaDB cosine similarity | Embedded tweet content |
| Semantic (Document) | ChromaDB cosine similarity | Embedded document chunks |
| Semantic (Analysis) | ChromaDB cosine similarity | Embedded analysis summaries |
| Structured | SQL query | PostgreSQL analysis results, predictions |
| Keyword | BM25 (rank-bm25) | Document chunks + tweet content |

**Pipeline flow:**
1. **Multi-path parallel retrieval** — 4 semantic paths + BM25 execute concurrently via `asyncio.gather`
2. **RRF fusion** — Reciprocal Rank Fusion (`k=60`) merges heterogeneous ranking scores into a unified sort. Handles the scale mismatch between vector cosine similarity and BM25 scores
3. **Time decay** — Recent documents receive a boost factor; prevents stale news from dominating
4. **Quota-balanced reranking** — DashScope `qwen3-rerank` scores all candidates, then `_apply_quota` enforces per-`source_type` minimums (tweet:4, document:3, analysis:2, structured:1) with global-score backfill for unfilled quotas
5. **Context truncation by type** — Evidence truncated according to type before prompt injection (`tweet:1000`, `document:1000`, `analysis:600`, `structured:500` chars)

**Document ingestion pipeline:**
- **Multi-format parsers** — PDF (pypdf), DOCX (python-docx), Markdown, Plain text, URL (curl_cffi + GNE news extraction + custom XPath/JSON-LD metadata extractors)
- **Metadata extraction** — Title, author (name only), publish time (ISO 8601 normalized), keywords. GNE fields take priority; custom extractors fill gaps
- **Soft-delete + partial unique index** — PostgreSQL `WHERE status != 'deleted'` partial index allows failed documents to be re-submitted without `UniqueViolation`
- **User quotas** — 200 documents / 500MB total per user, enforced before expensive embedding operations
- **ChromaDB metadata scrubbing** — `_scrub_meta()` filters non-primitive types (lists, dicts, None) before vector store writes, preventing runtime embedding failures

### 4. Conversational Chat System

Multi-user multi-turn chat with enterprise-grade controls:

- **ReAct + ToolNode** — Agent reasons step-by-step, calling tools: `fetch_blogger_profile`, `fetch_tweets`, `trigger_analysis`, `query_tweets`, `query_analyses`, `search_my_documents`, `generate_tracking_report`
- **SSE streaming** — Real-time token streaming via `sse-starlette`; supports `Last-Event-ID` reconnection
- **Conversation isolation** — Per-conversation advisory lock prevents concurrent agent execution on the same thread
- **Message idempotency** — Client-generated `message_id` deduplicates retries
- **Personalization** — User profile and preferences injected into system prompt; preferences auto-extracted after each conversation via background LLM call
- **Content filtering** — Middleware layer filters inappropriate inputs before reaching the agent
- **Rate limiting** — Per-user sliding window RPM counter (`TTLCache`); configurable token-per-day budgets

### 5. Analysis & Prediction Pipeline

Automated tweet analysis running on Celery workers:

- **Supervisor classification** — Incoming tweets classified into 4 categories: `investment`, `market_commentary`, `risk_warning`, `non_financial`. Non-financial tweets are skipped to save LLM costs
- **Blogger credibility feedback loop** — `analysis_agent` injects historical blogger context (win rate, sentiment distribution) into the prompt. LLM calibrates confidence based on KOL track record
- **Batch concurrency** — `asyncio.gather` parallelizes LLM calls across all tweets in a batch; total latency equals the slowest single call
- **Redis distributed locks** — `auto_analysis_task` acquires per-blogger locks to prevent duplicate analysis across multiple Celery workers
- **Prediction validation** — Automated prediction generation with scheduled verification against actual market outcomes

### 6. Tracking Subscription System

Users subscribe to stock/crypto tickers for automated report generation:

- **Subscription management** — Create / update / delete subscriptions with `daily` or `weekly` frequency
- **Quota enforcement** — Max 20 tracked tickers per user
- **Scheduled reports** — Celery beat triggers report generation at configured intervals (`next_run` computed for daily/weekly schedules)
- **Report history** — Full CRUD with pagination, ticker filtering

---

## API Endpoints

| Route | Description |
|-------|-------------|
| `POST /api/auth/register` | User registration |
| `POST /api/auth/login` | JWT login (access + refresh tokens) |
| `POST /api/auth/refresh` | Token refresh |
| `GET /api/auth/me` | Current user profile |
| `GET /api/dashboard/overview` | System overview stats |
| `GET /api/tweets` | Tweet listing |
| `GET /api/analyses` | Tweet analysis results (filter by blogger/sentiment) |
| `GET /api/signals` | Investment signal detection results |
| `GET /api/bloggers` | Blogger profiles and credibility scores |
| `GET /api/predictions` | Prediction records with verdict status |
| `POST /api/chat` | Conversational chat (SSE stream) |
| `GET /api/chat/conversations` | Conversation list with cursor pagination |
| `POST /api/documents/upload` | File upload (PDF/DOCX/MD/TXT) |
| `POST /api/documents/url` | URL ingestion |
| `POST /api/documents/paste` | Text paste ingestion |
| `GET /api/documents` | Document list |
| `POST /api/tracking` | Subscribe to ticker tracking |
| `GET /api/tracking` | List subscriptions |
| `POST /api/reports/generate` | Generate report (async, returns 202) |
| `GET /api/reports/{id}/stream` | SSE stream for report progress |
| `GET /api/reports/{id}` | Report detail |
| `GET /api/reports` | Report list with pagination |
| `GET /api/health` | Health check with circuit breaker status |

---

## Database Schema

**Core entities:**
- `User` / `UserProfile` / `UserPreference` — Authentication, profiles, and personalization
- `Blogger` — Financial KOL profiles with credibility metrics
- `Tweet` — Raw tweet content with `pending` / `analyzed` status tracking
- `AnalysisResult` — Structured analysis output (tweet_analysis, ticker_summary)
- `Prediction` — Forward-looking predictions with scheduled verification
- `Conversation` / `Message` — Chat history with compression and pagination
- `Document` / `DocChunk` — Uploaded documents with content hash deduplication
- `TrackedTicker` — User subscriptions with frequency and next-run scheduling
- `Report` — Generated reports with sections (JSONB), citations, and synthesis
- `AgentTrace` — Execution traces for observability

---

## Tech Stack

| Layer | Technology | Production Rationale |
|-------|-----------|---------------------|
| API Framework | FastAPI + Pydantic v2 | Async-native, auto OpenAPI docs, request validation |
| AI Engine | LangGraph + LangChain | StateGraph for conditional routing; Checkpointer for recovery |
| LLM Gateway | OpenRouter | Single endpoint for Claude / GPT / DeepSeek / Qwen with model failover |
| Vector DB | ChromaDB | Zero-ops for single-node; migration path to Milvus/Zilliz for scale |
| Embeddings | DashScope `text-embedding-v4` | 1024-dim, production-grade Chinese/English bilingual |
| Retrieval | BM25 (`rank-bm25`) + Chroma semantic | Hybrid beats single-path in recall benchmarks |
| Reranker | DashScope `qwen3-rerank` | Cross-encoder precision after initial candidate pool |
| Task Queue | Celery + Redis | `acks_late=True` for worker crash recovery; exponential backoff retries |
| Database | PostgreSQL + Alembic | JSONB for flexible report sections; partial indexes for soft-delete |
| HTTP Client | curl_cffi | TLS fingerprint impersonation for reliable Twitter API access |
| Frontend | Next.js 14 + TypeScript | App Router, streaming SSR, real-time SSE consumption |

---

## Deployment

### Prerequisites

- Python >= 3.10
- PostgreSQL >= 14
- Redis >= 6
- Node.js >= 18

### Backend

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your database, OpenRouter, and DashScope keys

# Run database migrations
uv run alembic upgrade head

# Start API server
uv run uvicorn app.main:app --reload

# Start Celery worker (separate terminal)
uv run celery -A app.celery_app worker -l info

# Start Celery beat for scheduled tasks (optional, separate terminal)
uv run celery -A app.celery_app beat -l info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### Environment Variables

Key variables (see `.env.example` for full list):

```bash
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/finance_tweets
OPENROUTER_API_KEY=sk-or-...
DASHSCOPE_API_KEY=sk-...
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
FEATURE_RAG_ENABLED=true
```

---

## Project Structure

```
finance-tweet-analyzer/
├── app/
│   ├── agents/              # LangGraph agents
│   │   ├── report_agent.py      # Report generation pipeline (7-stage StateGraph)
│   │   ├── chat_agent.py        # Conversational ReAct agent with tool chain
│   │   ├── supervisor.py        # Batch tweet classification router
│   │   ├── analysis_agent.py    # Batch tweet analysis with blogger context
│   │   ├── signal_agent.py      # Single-tweet structured analysis
│   │   ├── self_query_agent.py  # Intent parsing and query rewriting
│   │   ├── sql_agent.py         # Text-to-SQL with validation
│   │   ├── risk_agent.py        # Risk assessment
│   │   ├── prediction_agent.py  # Forward prediction generation
│   │   └── llm.py               # LLM initialization (OpenRouter gateway)
│   ├── api/                 # FastAPI routers
│   │   ├── auth.py              # JWT authentication
│   │   ├── chat.py              # SSE streaming chat
│   │   ├── reports.py           # Async report generation + SSE
│   │   ├── documents.py         # Document upload / URL / paste
│   │   ├── tracking.py          # Ticker subscription CRUD
│   │   ├── dashboard.py         # Overview statistics
│   │   ├── tweets.py            # Tweet management
│   │   ├── analysis.py          # Analysis results
│   │   ├── signals.py           # Signal detection results
│   │   ├── bloggers.py          # Blogger profiles
│   │   ├── predictions.py       # Prediction records
│   │   └── debug.py             # Debug endpoints
│   ├── core/                # Infrastructure
│   │   ├── config.py            # Pydantic Settings (env-driven)
│   │   ├── auth.py              # JWT encode/decode + dependency
│   │   ├── deps.py              # DB session + dependency injection
│   │   ├── logging.py           # Loguru configuration
│   │   ├── access_log.py        # Request/response middleware with PII redaction
│   │   ├── resilience.py        # Circuit breaker + retry decorator
│   │   └── tracing.py           # LangSmith initialization
│   ├── models/              # SQLAlchemy ORM models
│   ├── rag/                 # RAG pipeline
│   │   ├── chunking.py          # Document chunking strategies
│   │   ├── embeddings.py        # DashScope embedding client
│   │   ├── vector_store.py      # ChromaDB wrapper with metadata scrubbing
│   │   ├── retrievers/          # 5 retrieval implementations
│   │   ├── fusion.py            # RRF multi-path fusion
│   │   ├── reranker.py          # Qwen reranker + quota + time decay
│   │   ├── parsers/             # PDF / DOCX / URL / Markdown / Paste
│   │   ├── storage.py           # Local file storage abstraction
│   │   └── tokenizer.py         # Token counting utilities
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic layer
│   │   ├── report_service.py    # Report CRUD + sync generation
│   │   ├── report_streaming.py  # SSE pub/sub + incremental persistence
│   │   ├── document_service.py  # Document deduplication + quota
│   │   ├── tracking_service.py  # Subscription scheduling
│   │   ├── analysis_service.py  # Batch analysis orchestration
│   │   ├── conversation_service.py  # Chat session management
│   │   ├── blogger_context.py   # Credibility score aggregation
│   │   └── twitter_service.py   # Twitter API client (curl_cffi)
│   ├── scheduler/           # Celery tasks
│   │   ├── tasks.py             # auto_analysis, report_streaming, prediction
│   │   └── locks.py             # Redis distributed locks
│   └── middleware/          # Content filter, compression
├── frontend/                # Next.js 14 application
│   ├── src/app/             # App Router pages
│   │   ├── page.tsx             # Dashboard
│   │   ├── chat/page.tsx        # Conversational chat
│   │   ├── documents/page.tsx   # Document management
│   │   ├── reports/page.tsx     # Report list
│   │   ├── reports/[id]/page.tsx # Report detail (SSE)
│   │   ├── tracking/page.tsx    # Ticker subscriptions
│   │   └── retrieval-test/      # RAG retrieval testing
│   └── src/components/      # Reusable UI components
├── alembic/                 # Database migrations
├── scripts/                 # Operational utilities
├── tests/                   # Unit tests (RAG pipeline)
└── pyproject.toml           # Python dependencies
```

---

## License

MIT

---

## 中文文档

### 项目概述

企业级金融推文分析平台，基于 LangGraph 多智能体编排、混合 RAG 检索和异步 Celery 任务处理，提供结构化研究报告、对话式问答和自动标的追踪功能。

面向高吞吐量数据摄取、多模型 LLM 编排、容错异步处理和实时用户流式推送等生产场景构建。

### 系统架构

详见上方架构图。系统分层：
- **前端层**：Next.js 14 应用（Dashboard、Chat、Documents、Reports、Tracking）
- **API 网关层**：FastAPI（JWT 认证、速率限制、访问日志、CORS）
- **Agent 层**：多个 LangGraph StateGraph 智能体，分别负责报告生成、对话问答、批量分类、批量分析等
- **RAG 层**：多路并行检索 → RRF 融合 → Qwen 重排序 → 上下文截断
- **数据层**：PostgreSQL（关系数据 + JSONB 报告）+ Redis（Celery + Pub/Sub）+ ChromaDB（向量存储）

### 核心子系统

#### 1. 多智能体流水线

| 智能体 | 架构 | 职责 |
|--------|------|------|
| **报告 Agent** | Plan-and-Execute + Send 扇出 | 生成结构化标的追踪报告，5 章节并行生成 |
| **聊天 Agent** | ReAct + ToolNode | 对话式问答，支持博主查询、推文搜索、文档 RAG、报告生成等工具 |
| **Supervisor** | 分类 → 条件路由 | 批量推文四分类（投资信号/市场评论/风险预警/非金融），跳过非金融节省成本 |
| **分析 Agent** | 批量并发 + 博主画像注入 | 提取标的、情绪、周期、核心观点，可信度反馈闭环 |
| **信号 Agent** | 单条结构化输出 | 轻量级单条推文实时分析 |

**生产级模式：**
- **Middleware 管线** — 动态模型路由（评分用快模型，生成用强模型）、运行时 Prompt 注入、工具错误拦截
- **熔断器** — `@resilient_tool` 装饰器提供指数退避重试 + 三态熔断（CLOSED→OPEN→HALF_OPEN），防止外部 API 降级时级联故障
- **Token 预算管理** — 聊天 Agent 调用 LLM 前估算上下文大小，超限自动裁剪历史
- **用户隔离** — `user_id` 通过 `RunnableConfig` 元数据全链路透传

#### 2. 报告生成系统

报告 Agent 执行 7 阶段流水线：

```
意图解析 → 多路并行检索（4 路语义 + BM25）
              │
              ▼
        RRF 融合（k=60）
              │
              ▼
        重排序（Qwen + source_type 配额 + 时间衰减）
              │
              ▼
        章节生成（5 章节 Send 扇出并行）
              │
              ▼
        综合（共识判断 + 投资建议）
```

**5 个报告章节：**
1. **KOL 观点** — 博主推文情绪与观点
2. **研报观点** — 文档和研究资料洞察
3. **新闻动态** — 最新新闻和市场发展
4. **风险提示** — 风险因素和预警信号
5. **历史回顾** — 历史价格走势和模式分析

**生产级韧性设计：**
- **节点级 SSE 流式** — 每完成一个阶段通过 Redis `report_stream:{id}` 发布事件；前端通过 `EventSourceResponse` 订阅，15 秒心跳保活
- **增量持久化** — 重排序结果 → DB citations；每个章节 → DB `sections` JSONB 合并；综合 → 最终报告状态。断线重连返回当前进度快照
- **章节容错** — 失败章节携带 `error` 元数据，不阻塞整体流水线
- **全局引用编号** — 所有章节使用统一证据编号，UI 点击可滚动到具体引用行
- **source_type 配额重排序** — 保证证据类型均衡，避免推文（通常占 30 条中的 20+）独占 Top-8，导致结构化数据无法进入历史回顾章节

#### 3. RAG 引擎

**混合检索架构：**

| 路径 | 方法 | 数据源 |
|------|------|--------|
| 语义（推文） | ChromaDB 余弦相似度 | 嵌入后的推文内容 |
| 语义（文档） | ChromaDB 余弦相似度 | 嵌入后的文档分块 |
| 语义（分析） | ChromaDB 余弦相似度 | 嵌入后的分析摘要 |
| 结构化 | SQL 查询 | PostgreSQL 分析结果、预测记录 |
| 关键词 | BM25 | 文档分块 + 推文内容 |

**流水线：**
1. **多路并行检索** — 4 路语义 + BM25 通过 `asyncio.gather` 并发执行
2. **RRF 融合** — 倒数排名融合（`k=60`）将异构排序分数统一为单一排序
3. **时间衰减** — 近期文档获得 boost，防止过时新闻主导结果
4. **配额平衡重排序** — DashScope `qwen3-rerank` 全量打分后，按 source_type 配额分配（tweet:4, document:3, analysis:2, structured:1），未填满名额按全局分数补齐
5. **按类型上下文截断** — 证据按类型截断后注入 Prompt（tweet:1000, document:1000, analysis:600, structured:500 字符）

**文档摄取流水线：**
- **多格式解析器** — PDF（pypdf）、DOCX（python-docx）、Markdown、纯文本、URL（curl_cffi + GNE 新闻提取 + 自定义 XPath/JSON-LD 元数据提取）
- **元数据提取** — 标题、作者（仅名称）、发布时间（ISO 8601 标准化）、关键词。GNE 字段优先，自定义提取器补全
- **软删除 + 部分唯一索引** — PostgreSQL `WHERE status != 'deleted'` 部分索引，失败文档可重新提交
- **用户配额** — 每人 200 文档 / 500MB 总量，在昂贵嵌入操作前强制校验
- **ChromaDB 元数据清洗** — `_scrub_meta()` 过滤非原始类型（列表、字典、None），防止向量库写入失败

#### 4. 对话聊天系统

多用户多轮对话，企业级控制：

- **ReAct + ToolNode** — Agent 逐步推理，调用工具：`fetch_blogger_profile`、`fetch_tweets`、`trigger_analysis`、`query_tweets`、`query_analyses`、`search_my_documents`、`generate_tracking_report`
- **SSE 流式** — 通过 `sse-starlette` 实时推送 Token；支持 `Last-Event-ID` 断线重连
- **会话隔离** — 每会话咨询锁防止并发 Agent 执行
- **消息幂等性** — 客户端生成的 `message_id` 去重重试
- **个性化** — 用户档案和偏好注入系统 Prompt；每次对话后后台异步提取偏好更新
- **内容过滤** — 中间件层在 Agent 之前过滤不当输入
- **速率限制** — 每用户滑动窗口 RPM 计数器；可配置日 Token 预算

#### 5. 分析与预测流水线

Celery Worker 上运行的自动推文分析：

- **Supervisor 分类** — 推文分为 investment/market_commentary/risk_warning/non_financial 四类，非金融直接跳过节省 LLM 成本
- **博主可信度反馈闭环** — 分析 Agent 将博主历史画像（胜率、情绪分布）注入 Prompt，LLM 根据 KOL 历史表现校准置信度
- **批量并发** — `asyncio.gather` 并行化一批推文的所有 LLM 调用；总延迟等于最慢单条
- **Redis 分布式锁** — `auto_analysis_task` 按博主加锁，防止多 Worker 重复分析
- **预测验证** — 自动生成前瞻预测，定时验证与实际市场走势的吻合度

#### 6. 追踪订阅系统

用户订阅股票/加密货币标的，自动生成追踪报告：

- **订阅管理** — 创建/更新/删除，支持 daily/weekly 频率
- **配额限制** — 每用户最多 20 个追踪标的
- **定时报告** — Celery beat 按配置间隔触发报告生成
- **报告历史** — 完整 CRUD，支持分页和标的过滤

### 部署指南

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer
uv sync
cp .env.example .env
# 编辑 .env 配置数据库和 API 密钥
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Celery Worker：
```bash
uv run celery -A app.celery_app worker -l info
uv run celery -A app.celery_app beat -l info
```

前端：
```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000
