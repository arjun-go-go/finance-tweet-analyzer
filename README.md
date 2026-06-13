# Finance Tweet Analyzer

> **Production-grade AI Agent platform** for financial tweet analysis, built from 8 years of enterprise engineering experience and real-world multi-agent system deployment.

English | [中文](#中文文档)

---

## About This Project

This is not a tutorial demo. It is a **production-ready full-stack application** that distills my hands-on experience building enterprise AI Agent platforms for intelligence analysis and large-scale data processing pipelines.

### Author Background

**曹俊 (Cao Jun)** — Senior Python Engineer with 8 years of experience, specializing in:
- **LangGraph / LangChain** multi-agent system architecture (production deployments since 2024)
- **Agentic RAG** hybrid retrieval (Milvus + Elasticsearch + Reranker) — Faithfulness 0.91, Context Precision 0.85
- **Distributed data pipelines** — Scrapy-Redis + Kafka + Spark, 1M+ daily data ingestion
- **Anti-detection engineering** — Cloudflare / Akamai / TLS fingerprint bypass, 95%+ success rate

Previously built production-grade multi-agent intelligence analysis platforms at Hangzhou Sitake Information Security Technology Co., Ltd., handling 6 social platforms + 500+ overseas media sources.

---

## Production-Grade Features

### Multi-Agent Pipeline (LangGraph StateGraph)

Inspired by production intelligence analysis systems, the architecture uses **three-tier agent orchestration**:

| Agent | Role | Production Pattern |
|-------|------|-------------------|
| **Signal Agent** | Detect market signals from tweets | ReAct loop with tool calling |
| **Report Agent** | Generate structured research reports | Plan-and-Execute with Send fan-out |
| **Chat Agent** | Conversational Q&A with RAG | Supervisor routing + sub-agent tools |

**Engineering decisions from production:**
- **Middleware pipeline** for dynamic model routing (signal scoring → DeepSeek, generation → Claude), runtime prompt injection, and tool error interception
- **Circuit breaker pattern** — Tool failures are caught, retried with exponential backoff, and isolated to prevent cascading failures
- **Rate limiting per user** — RPM + token-per-day budgets with configurable hard limits

### Agentic RAG Engine

Built on lessons from deploying RAG at scale for intelligence analysis:

- **Hybrid retrieval** — ChromaDB semantic search + BM25 keyword search, merged via Reciprocal Rank Fusion (RRF)
- **Source-type quota reranking** — Ensures balanced evidence types (tweets, documents, analysis, structured data). Prevents the common production issue where one source type dominates top-K results
- **Multi-model reranker** — DashScope `qwen3-rerank` for production-quality relevance scoring
- **Context compression** — Evidence truncation by type (`tweet: 1000`, `document: 1000`, `analysis: 600`, `structured: 500`) to fit within context windows without losing critical information

### SSE Streaming Architecture

Production streaming design learned from real-time intelligence push systems:

- **Node-level streaming** — LangGraph `stream_mode="updates"` emits each node completion (intent parsing → retrieval → reranking → section generation → synthesis)
- **Incremental persistence** — Each completed section is written to PostgreSQL immediately. If the client disconnects, reconnecting yields a snapshot of current progress
- **Redis pub/sub bridge** — Celery workers publish progress to `report_stream:{id}` channels; SSE endpoint subscribes and forwards with 15s heartbeat keepalive

### Document Ingestion Pipeline

Production-grade document processing with enterprise deduplication:

- **Rich metadata extraction** — GNE (GeneralNewsExtractor) for news articles, with fallback to custom XPath/JSON-LD extractors for publish time (ISO 8601 normalized) and author names
- **Soft-delete + partial unique index** — PostgreSQL `WHERE status != 'deleted'` partial index allows failed documents to be re-submitted without unique constraint violations
- **Quota management** — Per-user document limits (200 docs / 500MB total) enforced at service layer before expensive embedding operations
- **ChromaDB metadata scrubbing** — Automatic filtering of non-primitive types (lists, dicts, None) before vector store writes, preventing runtime embedding failures

### Enterprise Security & Observability

- **JWT authentication** with refresh tokens, session isolation, and per-user token budgets
- **Request/response logging** with automatic redaction of sensitive keys (API keys, tokens, passwords)
- **Access log middleware** — Tracks user ID, latency, and path with proper async propagation (ContextVar + `request.state` fallback)
- **LangSmith tracing** — Full LangGraph execution traces for debugging production agent behavior

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                          │
│  (Incremental streaming UI / JWT auth / Report viewer)          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼─────────────────────────────────────┐
│                        FastAPI API Gateway                       │
│  (Rate limiting / Access logging / Auth middleware)             │
└───────────┬───────────────────────┬─────────────────────────────┘
            │                       │
┌───────────▼───────────┐  ┌────────▼────────┐
│   Chat Agent          │  │  Report Agent   │
│   (Supervisor)        │  │  (Plan-Exec)    │
└───────┬───────────────┘  └────────┬────────┘
        │                           │
        └───────────┬───────────────┘
                    │
        ┌───────────▼───────────────┐
        │      RAG Pipeline         │
        │  ┌─────────────────────┐  │
        │  │  Multi-Path Retrieval│  │
        │  │  ├── Tweet (Chroma) │  │
        │  │  ├── Document(BM25) │  │
        │  │  ├── Analysis       │  │
        │  │  └── Structured     │  │
        │  └──────────┬──────────┘  │
        │             │ RRF Fusion   │
        │  ┌──────────▼──────────┐  │
        │  │   Qwen Reranker     │  │
        │  │   (quota-balanced)  │  │
        │  └──────────┬──────────┘  │
        └─────────────┼─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    PostgreSQL + Redis     │
        │  (state + task queue)     │
        └───────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Production Rationale |
|-------|-----------|---------------------|
| API Framework | FastAPI + Pydantic v2 | Async-native, auto-generated OpenAPI docs |
| AI Engine | LangGraph + LangChain | StateGraph for complex conditional routing; Checkpointer for recovery |
| LLM Gateway | OpenRouter | Single endpoint for Claude / GPT / DeepSeek / Qwen with failover |
| Vector DB | ChromaDB | Zero-ops for single-node deployments; easy migration path to Milvus/Zilliz |
| Embeddings | DashScope `text-embedding-v4` | 1024-dim, production-grade Chinese/English bilingual |
| Retrieval | BM25 (rank-bm25) + Chroma semantic | Hybrid beats single-path in all RAGAS benchmarks |
| Reranker | DashScope `qwen3-rerank` | Cross-encoder precision after initial candidate retrieval |
| Task Queue | Celery + Redis | Battle-tested for async document ingestion and scheduled reports |
| Database | PostgreSQL + Alembic | JSONB for flexible report sections; partial indexes for soft-delete |
| Proxy | curl_cffi | TLS fingerprint impersonation for reliable Twitter API access |
| Frontend | Next.js 14 + TypeScript | App Router, Server Components, streaming SSR |

---

## Quick Start

### Prerequisites

- Python >= 3.10
- PostgreSQL >= 14
- Redis >= 6
- Node.js >= 18

### Backend

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer

# Install with uv
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your database, OpenRouter, and DashScope keys

# Run migrations
uv run alembic upgrade head

# Start API
uv run uvicorn app.main:app --reload

# Start Celery worker (another terminal)
uv run celery -A app.celery_app worker -l info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### Environment Variables (Key)

```bash
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/finance_tweets
OPENROUTER_API_KEY=sk-or-...
DASHSCOPE_API_KEY=sk-...
REDIS_URL=redis://localhost:6379/0
FEATURE_RAG_ENABLED=true
```

See `.env.example` for the complete list.

---

## Engineering Highlights

### From Enterprise Intelligence Platform Experience

1. **Supervisor Dynamic Routing** — Report agent uses `Send` fan-out to parallelize section generation. If one section fails, others continue; failed sections are surfaced with error metadata instead of silently dropped

2. **Context Compaction** — Chat agent implements summarization middleware that triggers at configurable token thresholds, preserving conversation history within budget limits

3. **HITL-Ready Architecture** — LangGraph `interrupt` nodes are reserved for critical decisions; Checkpointer persistence enables breakpoint resume (foundation laid, UI activation straightforward)

4. **Anti-Fragile Document Pipeline** — Failed ingestions are marked `failed` with error detail; user can retry after fixing the source. Partial unique index prevents duplicate re-submissions while allowing genuine retries

5. **Multi-Model Cost Optimization** — Configurable per-node model selection: fast/cheap models for classification and scoring; premium models for final generation

---

## Project Structure

```
finance-tweet-analyzer/
├── app/
│   ├── agents/              # LangGraph agents (chat, report, signal, self-query)
│   ├── api/                 # FastAPI routers (auth, chat, reports, documents, tracking)
│   ├── core/                # Config, JWT auth, access logging, rate limiting, middleware
│   ├── models/              # SQLAlchemy ORM models with JSONB support
│   ├── rag/                 # Full RAG pipeline: chunking, embeddings, retrievers, reranker, fusion
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic: reports, documents, tracking, Twitter
│   └── scheduler/           # Celery tasks: document ingestion, scheduled reports
├── frontend/                # Next.js 14 App Router application
├── alembic/                 # Database migrations (incremental schema evolution)
├── scripts/                 # Operational utilities (crawlers, eval scripts)
└── tests/                   # Unit tests for RAG components
```

---

## License

MIT

---

## 中文文档

> **企业级 AI Agent 平台**，用于金融推文分析。基于 8 年企业工程经验和真实多智能体系统部署沉淀。

### 关于本项目

这不是教程 Demo。这是一个**生产就绪的全栈应用**，凝结了我在企业情报分析和大规模数据处理流水线中的实战经验。

### 作者背景

**曹俊** — 高级 Python 工程师，8 年开发经验，专长领域：
- **LangGraph / LangChain** 多智能体系统架构（2024 年起生产环境部署）
- **Agentic RAG** 混合检索（Milvus + ES + Reranker）— Faithfulness 0.91，Context Precision 0.85
- **分布式数据流水线** — Scrapy-Redis + Kafka + Spark，日均百万级数据采集
- **反爬对抗** — Cloudflare / Akamai / TLS 指纹突破，成功率 95%+

曾在杭州司塔科信息安全技术有限公司主导企业级多智能体情报分析平台建设，覆盖 6 大社交平台 + 500+ 境外媒体源。

### 生产级特性

#### 多智能体流水线（LangGraph StateGraph）

借鉴生产情报分析系统架构，采用**三级智能体编排**：

| Agent | 职责 | 生产模式 |
|-------|------|---------|
| **信号 Agent** | 从推文检测市场信号 | ReAct 工具调用循环 |
| **报告 Agent** | 生成结构化研究报告 | Plan-and-Execute + Send 扇出 |
| **聊天 Agent** | 对话式问答 | Supervisor 路由 + 子智能体工具 |

**生产工程实践：**
- **Middleware 管线** — 动态模型路由（评分→DeepSeek，生成→Claude）、运行时 Prompt 注入、工具调用错误拦截
- **熔断器模式** — 工具失败自动捕获、指数退避重试、故障隔离防止级联失败
- **用户级速率限制** — RPM + 日 Token 预算，支持硬上限配置

#### Agentic RAG 引擎

基于大规模情报分析 RAG 部署经验：

- **混合检索** — ChromaDB 语义搜索 + BM25 关键词搜索，RRF 融合排序
- **source_type 配额重排序** — 保证证据类型均衡（推文、文档、分析、结构化数据），解决生产环境常见的一类源主导 Top-K 的问题
- **多模型重排序器** — DashScope `qwen3-rerank` 生产级相关性打分
- **上下文压缩** — 按类型截断（`tweet:1000`、`document:1000`、`analysis:600`、`structured:500`），在上下文窗口限制内保留关键信息

#### SSE 流式架构

来自实时情报推送系统的生产流式设计：

- **节点级流式** — LangGraph `stream_mode="updates"` 逐节点推送（意图解析→检索→重排序→章节生成→综合）
- **增量持久化** — 每个完成的章节立即写入 PostgreSQL。客户端断线重连后返回当前进度快照
- **Redis 发布订阅桥接** — Celery Worker 发布到 `report_stream:{id}` 频道；SSE 端点订阅并转发，15 秒心跳保活

#### 文档摄取流水线

企业级文档处理，含去重机制：

- **丰富元数据提取** — GNE 新闻正文提取，XPath/JSON-LD 后备提取发布时间（ISO 8601 标准化）和作者名
- **软删除 + 部分唯一索引** — PostgreSQL `WHERE status != 'deleted'` 部分索引，失败文档可重新提交而不违反唯一约束
- **配额管理** — 服务层强制用户级文档限制（200 文档 / 500MB 总量），避免昂贵的嵌入操作滥用
- **ChromaDB 元数据清洗** — 写入向量库前自动过滤非原始类型（列表、字典、None），防止运行时嵌入失败

#### 企业安全与可观测性

- **JWT 认证** — 支持刷新令牌、会话隔离、用户级 Token 预算
- **请求/响应日志** — 自动脱敏敏感字段（API key、token、密码）
- **访问日志中间件** — 追踪用户 ID、延迟、路径，支持异步传播（ContextVar + `request.state` 后备）
- **LangSmith 追踪** — 完整的 LangGraph 执行链路，便于生产环境 Agent 行为调试

### 快速开始

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer
uv sync
cp .env.example .env
# 编辑 .env 配置数据库和 API 密钥
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

前端：
```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000

### 工程亮点

1. **Supervisor 动态路由** — 报告 Agent 使用 `Send` 扇出并行生成章节。单章节失败不影响其他章节；失败章节带错误元数据展示

2. **上下文压缩** — 聊天 Agent 实现可配置 Token 阈值触发的 SummarizationMiddleware，在预算限制内保留对话历史

3. **HITL 就绪架构** — LangGraph `interrupt` 节点预留关键决策人工审核；Checkpointer 持久化支持断点续行

4. **抗脆弱文档流水线** — 摄取失败标记为 `failed` 并记录错误详情；用户修复源后可重试。部分唯一索引防止重复提交同时允许合法重试

5. **多模型成本优化** — 支持按节点配置模型选择：快速/廉价模型用于分类评分； premium 模型用于最终生成
