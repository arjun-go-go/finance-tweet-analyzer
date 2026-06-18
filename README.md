# Finance Tweet Analyzer

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org)
[![LangChain](https://img.shields.io/badge/LangChain-1.3+-purple.svg)](https://github.com/langchain-ai/langchain)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Enterprise-grade financial tweet analysis platform — LangGraph multi-agent orchestration, hybrid RAG retrieval, and real-time SSE streaming.

English | [中文简介](#中文简介)

---

## Features

- **8 LangGraph Agents** — Report, Chat, Supervisor, Analysis, Signal, Self-Query, SQL, Risk — each with specialized architecture (ReAct, Plan-and-Execute, Send fan-out)
- **5-Path Hybrid RAG** — Semantic (ChromaDB) + BM25 keyword + Structured SQL → RRF fusion → Qwen reranker with source-type quota balancing
- **Real-time SSE Streaming** — Chat tokens and report progress streamed via Redis pub/sub with incremental DB persistence
- **Async Task Processing** — Celery + Redis with distributed locks, circuit breakers, and exponential backoff retries
- **Multi-format Document Ingestion** — PDF, DOCX, Markdown, URL (GNE extraction), plain text — with metadata extraction and ChromaDB embedding
- **Cross-session Memory** — mem0 long-term memory + LangGraph checkpointing for personalized conversations
- **YAML/Jinja2 Prompt Registry** — 9 YAML files with versioning and template variables, centralized in `prompts/`
- **Production Resilience** — JWT startup validation, connection pool, health check (DB/Redis/ChromaDB), prompt injection defense (15 CN/EN patterns), token budget management

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     Next.js Frontend                           │
│   Dashboard · Chat(SSE) · Documents · Reports(SSE) · Tracking │
└──────────────────────────────┬────────────────────────────────┘
                               │ HTTPS
┌──────────────────────────────▼────────────────────────────────┐
│                    FastAPI API Gateway                          │
│       JWT Auth · Rate Limiting · CORS · Health Check           │
└──────────────────────────────┬────────────────────────────────┘
                               │
    ┌──────────────┬───────────▼──────────┬───────────────┐
    │ Chat Agent   │ Report Agent         │ Supervisor    │
    │ (ReAct)      │ (Plan-Execute+Send)  │ (Classify)    │
    └──────┬───────┴──────┬───────────────┴───────┬───────┘
           │              │                       │
           └──────┬───────┘                       │
                  │                               │
        ┌─────────▼───────────────────────────────┘
        │            RAG Pipeline                  │
        │  5-Path Retrieval → RRF → Rerank        │
        │  (quota-balanced + time-decay)           │
        └─────────┬───────────────────────────────┘
                  │
    ┌─────────────▼────────────┬──────────────┐
    │ PostgreSQL              │ Redis         │ ChromaDB
    │ (Relational + JSONB)    │ (Celery+Pub)  │ (Vectors)
    └─────────────────────────┴──────────────┘
```

---

## Agents

| Agent | Architecture | Purpose |
|-------|-------------|---------|
| Report | Plan-and-Execute + `Send` fan-out | 5-section structured ticker reports (KOL, Research, News, Risk, History) |
| Chat | ReAct + ToolNode | Multi-turn Q&A with 7 tools (blogger, tweets, documents, reports) |
| Supervisor | Classification → routing | 4-category tweet filter (investment, commentary, risk, non-financial) |
| Analysis | Batch concurrency + blogger context | Ticker/sentiment extraction with credibility feedback loop |
| Signal | Single-call structured output | Lightweight real-time tweet analysis |
| Self-Query | Intent parsing + rewriting | NL → structured retrieval parameters |
| SQL | Text-to-SQL with validation | Safe analytical data queries |
| Risk | Structured assessment | 6-category risk taxonomy evaluation |

---

## RAG Pipeline

```
Query Intent → Self-Query Agent
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
  ChromaDB         BM25          SQL
  (3 semantic    (keyword      (structured
   paths)         path)          path)
    │               │               │
    └───────┬───────┘───────────────┘
            │
            ▼  RRF Fusion (k=60)
            │
            ▼  Qwen Reranker
            │  (quota: tweet:4, doc:3, analysis:2, structured:1)
            │  + time-decay + min-score threshold
            │
            ▼  Context → Agent Prompt
```

---

## Quick Start

### Prerequisites

- Python 3.12+, PostgreSQL 14+, Redis 6+, Node.js 18+

### Backend

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer

uv sync

cp .env.example .env
# Edit .env — set DATABASE_URL, OPENROUTER_API_KEY, DASHSCOPE_API_KEY, JWT_SECRET_KEY

uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Celery worker (separate terminal, Windows uses --pool=solo)
uv run celery -A app.celery_app worker -l info --pool=solo

# Celery beat for scheduled tasks (optional)
uv run celery -A app.celery_app beat -l info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

---

## Environment Variables

Key variables (see `.env.example` for full list):

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection (psycopg v3 driver) |
| `OPENROUTER_API_KEY` | Yes | LLM gateway — single endpoint for Claude/GPT/DeepSeek/Qwen |
| `DASHSCOPE_API_KEY` | Yes | Embeddings (text-embedding-v4) + Reranker (qwen3-rerank) |
| `JWT_SECRET_KEY` | Yes | HS256 signing key (validated at startup, rejects empty) |
| `REDIS_URL` | Yes | Redis for Celery broker + result backend |
| `CELERY_BROKER_URL` | Yes | Celery broker (typically redis://localhost:6379/1) |
| `FEATURE_RAG_ENABLED` | No | Enable/disable RAG pipeline (default: true) |
| `SCHEDULER_ENABLED` | No | Enable/disable APScheduler (default: false) |

---

## Project Structure

```
finance-tweet-analyzer/
├── app/
│   ├── agents/         # 8 LangGraph agents + LLM factory
│   ├── api/            # FastAPI routers (auth, chat, reports, documents, tracking...)
│   ├── core/           # Config, auth, deps, resilience, logging, tracing
│   ├── models/         # SQLAlchemy ORM (15 models)
│   ├── rag/            # 5-path retrieval, fusion, reranker, parsers, embeddings
│   ├── memory/         # mem0 client, compression, preferences, checkpointer
│   ├── prompts/        # YAML/Jinja2 loader
│   ├── schemas/        # Pydantic request/response schemas
│   ├── services/       # Business logic layer
│   ├── scheduler/      # Celery tasks + distributed locks
│   └── middleware/     # Content filter (prompt injection defense)
├── prompts/            # 9 YAML prompt files (versioned, Jinja2 templates)
├── frontend/           # Next.js 15 + React 19 + TypeScript + Tailwind
│   ├── src/app/        # 14+ App Router pages
│   └── src/components/ # 16 reusable UI components
├── alembic/            # 12 database migrations
├── scripts/            # Twitter crawler, seed data, reset, evaluation
├── tests/              # Unit (RAG, agents, memory) + integration (documents API)
└── pyproject.toml      # Python dependencies (uv-managed)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Pydantic v2 |
| AI Engine | LangGraph + LangChain |
| LLM Gateway | OpenRouter (Claude / GPT / DeepSeek / Qwen) |
| Embeddings | DashScope text-embedding-v4 (1024-dim) |
| Reranker | DashScope qwen3-rerank |
| Vector DB | ChromaDB |
| Keyword | PostgreSQL tsvector (BM25) |
| Task Queue | Celery + Redis |
| Database | PostgreSQL + Alembic (psycopg v3) |
| Memory | mem0 + LangGraph Checkpointer |
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind |
| Prompt Mgmt | YAML + Jinja2 Registry |

---

## API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/register` / `login` / `refresh` | JWT auth flow |
| `POST /api/chat` | SSE streaming chat |
| `POST /api/reports/generate` | Async report generation (202) |
| `GET /api/reports/{id}/stream` | SSE report progress |
| `POST /api/documents/upload` / `url` / `paste` | Document ingestion |
| `POST /api/tracking` | Ticker subscription (daily/weekly) |
| `GET /api/bloggers` / `analyses` / `predictions` / `signals` | Data query endpoints |
| `GET /api/health` | Health check (DB + Redis + ChromaDB + circuits) |

Full interactive docs at `/docs` (Swagger UI) when server is running.

---

## License

MIT

---

## 中文简介

企业级金融推文分析平台，基于 LangGraph 8 智能体编排、5 路混合 RAG 检索和 Celery 异步任务处理。

核心能力：结构化研究报告生成（5 章节 Send 扇出并行）、对话式问答（ReAct + 7 工具）、推文自动分类与分析、标的追踪订阅、多格式文档摄取、跨会话记忆、SSE 实时流式推送。

技术栈：FastAPI + LangGraph + OpenRouter + DashScope + ChromaDB + PostgreSQL + Redis + Celery + Next.js 15 + YAML/Jinja2 Prompt Registry。

生产级设计：熔断器 + 指数退避重试、JWT 启动校验、连接池、分布式锁（Lua 脚本所有权校验）、Prompt 注入防御（15 中英文模式）、Token 预算管理、配额平衡重排序、增量持久化 + 断线重连。
