# Finance Tweet Analyzer

AI-powered finance tweet analysis platform with LangGraph multi-agent pipeline, RAG retrieval, and real-time SSE streaming.

English | [中文](#中文文档)

---

## Features

- **Multi-Agent Pipeline** — LangGraph orchestrates signal detection, report generation, and conversational chat agents
- **RAG Engine** — ChromaDB + DashScope embeddings + BM25 hybrid retrieval + Qwen reranker
- **Document Ingestion** — PDF / DOCX / URL / paste, with GNE news extraction and rich metadata
- **SSE Streaming** — Real-time node-level progress for chat and report generation
- **JWT Authentication** — Multi-user sessions with token budgets and rate limiting
- **Tracking Subscriptions** — Follow tickers, auto-schedule analysis reports
- **Next.js Frontend** — Modern React app with incremental streaming UI

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy, Alembic |
| AI Engine | LangGraph, LangChain, OpenRouter |
| Vector DB | ChromaDB |
| Embeddings | DashScope (text-embedding-v4) |
| Async Tasks | Celery + Redis |
| Database | PostgreSQL |
| Frontend | Next.js + TypeScript |
| Proxy | curl_cffi (TLS fingerprint impersonation) |

## Quick Start

### Prerequisites

- Python >= 3.10
- PostgreSQL
- Redis
- Node.js >= 18 (for frontend)

### 1. Clone & Setup

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer
```

### 2. Backend

```bash
# Install dependencies
uv sync

# Copy env and configure
# cp .env.example .env
# Edit .env with your database, API keys, etc.

# Run migrations
uv run alembic upgrade head

# Start services
uv run uvicorn app.main:app --reload
uv run celery -A app.celery_app worker -l info
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Environment Variables

See `.env.example` for all available options. Key ones:

```bash
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/finance_tweets
OPENROUTER_API_KEY=sk-or-...
DASHSCOPE_API_KEY=sk-...
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
FEATURE_RAG_ENABLED=true
```

## Architecture

```
Frontend (Next.js) ──→ FastAPI API
                              │
         ┌────────────────────┼────────────────────┐
         ↓                    ↓                    ↓
    Chat Agent       Report Agent          Signal Agent
    (LangGraph)      (LangGraph)           (LangGraph)
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ↓
                    RAG Pipeline
                    ├── Tweet Retriever
                    ├── Document Retriever
                    ├── Analysis Retriever
                    └── Structured Retriever
                              │
                    ┌─────────┴─────────┐
                    ↓                   ↓
              ChromaDB              BM25
              (semantic)         (keyword)
                    │                   │
                    └─────────┬─────────┘
                              ↓
                         Reranker (Qwen)
                              ↓
                    Report / Chat Response
```

## Project Structure

```
finance-tweet-analyzer/
├── app/
│   ├── agents/          # LangGraph agents (chat, report, signal)
│   ├── api/             # FastAPI routers
│   ├── core/            # Config, auth, logging, middleware
│   ├── models/          # SQLAlchemy models
│   ├── rag/             # RAG pipeline (chunking, embeddings, retrievers)
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   └── scheduler/       # Celery tasks
├── frontend/            # Next.js application
├── alembic/             # Database migrations
├── scripts/             # Utility scripts
└── tests/               # Unit tests
```

## Key Design Decisions

- **Node-level SSE** — Report generation streams each LangGraph node output, with incremental DB writes for resilience
- **Source-type quota rerank** — Ensures balanced evidence types (tweets, documents, analysis, structured data) in every report
- **Global citation indexing** — Evidence numbers are consistent across all report sections and clickable in the UI
- **Section fault tolerance** — Failed sections are flagged with error metadata instead of crashing the entire report
- **Soft-delete + partial unique index** — Documents can be re-submitted after failure without violating uniqueness

## License

MIT

---

## 中文文档

AI 驱动的金融推文分析平台，基于 LangGraph 多智能体流水线、RAG 检索增强生成和 SSE 实时流式推送。

### 核心功能

- **多智能体流水线** — LangGraph 编排信号检测、报告生成、对话聊天三大 Agent
- **RAG 引擎** — ChromaDB + DashScope 嵌入 + BM25 混合检索 + Qwen 重排序
- **文档摄取** — 支持 PDF / DOCX / URL / 粘贴，GNE 新闻正文提取 + 丰富元数据
- **SSE 流式推送** — 聊天和报告生成均支持节点级实时进度推送
- **JWT 认证** — 多用户会话，带 Token 预算和速率限制
- **追踪订阅** — 关注股票代码，定时自动生成分析追踪报告
- **Next.js 前端** — 现代化 React 应用，支持增量流式渲染

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

### 关键设计

- **节点级 SSE** — 报告生成按 LangGraph 节点逐步推送，增量写入数据库确保断线可恢复
- **source_type 配额重排序** — 保证每份报告的证据类型均衡（推文、文档、分析、结构化数据）
- **全局引用编号** — 所有章节使用统一的证据编号，UI 点击可跳转到具体引用
- **章节容错** — 失败章节标记错误元数据，不导致整份报告崩溃
- **软删除 + 部分唯一索引** — 失败文档可重新提交，不触发唯一性冲突
