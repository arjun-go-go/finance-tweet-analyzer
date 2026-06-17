# Finance Tweet Analyzer - Design Spec

## Overview

A comprehensive financial tweet analysis platform that scrapes Twitter/X posts from finance bloggers, performs multi-dimensional AI analysis (signal extraction, sentiment analysis, credibility scoring, market consensus), and presents results through a web dashboard.

## Goals

- **Primary**: Build a production-quality AI Agent platform that analyzes financial blogger tweets across crypto, US stocks, A-shares/HK stocks, and forex/commodities
- **Secondary**: Demonstrate LangGraph multi-agent orchestration depth for interview purposes
- **Development Rhythm**: MVP first (Signal Agent + basic frontend), iterate to add remaining agents

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Web Frontend (Next.js)                      │
├──────────────────────────────────────────────────────────────────┤
│                     FastAPI (REST + SSE)                           │
├──────────────────────────────────────────────────────────────────┤
│                     LangGraph Orchestration                        │
│                                                                    │
│  ┌───────────┐    ┌──────────────────────────────────────────┐   │
│  │ Scheduler │───▶│          Supervisor Agent                 │   │
│  └───────────┘    │   (routing + fan-out + aggregation)       │   │
│                    └──────┬──────┬──────┬──────┬──────────────┘   │
│                           │      │      │      │                   │
│                    ┌──────▼┐ ┌───▼───┐ ┌▼─────┐ ┌▼──────┐        │
│                    │Signal │ │Senti- │ │Credi-│ │Report │        │
│                    │Agent  │ │ment   │ │bility│ │Agent  │        │
│                    │       │ │Agent  │ │Agent │ │       │        │
│                    └───────┘ └───────┘ └──────┘ └───────┘        │
├──────────────────────────────────────────────────────────────────┤
│                       Data Layer                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │PostgreSQL│  │  Chroma  │  │  Redis   │  │  Crawler │         │
│  │(struct)  │  │ (vector) │  │(cache+   │  │(separate)│         │
│  │          │  │          │  │ schedule)│  │          │         │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

Crawler code is maintained separately; this project assumes tweet data arrives via import API or direct DB writes.

## Data Models

### PostgreSQL Tables

**tweets**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Internal ID |
| tweet_id | VARCHAR UNIQUE | Twitter original ID |
| author_handle | VARCHAR | Blogger handle |
| author_name | VARCHAR | Display name |
| content | TEXT | Tweet text |
| published_at | TIMESTAMP | Publish time |
| metrics | JSONB | likes/retweets/replies |
| media_urls | JSONB | Image/video links |
| raw_json | JSONB | Raw scraped data |
| status | VARCHAR | pending/analyzed/failed |
| created_at | TIMESTAMP | Import time |

**bloggers**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Internal ID |
| handle | VARCHAR UNIQUE | Twitter handle |
| name | VARCHAR | Display name |
| bio | TEXT | Profile bio |
| followers_count | INTEGER | Follower count |
| market_focus | VARCHAR[] | crypto/us_stock/a_stock/forex |
| credibility_score | FLOAT | 0-100, computed by Agent |
| total_predictions | INTEGER | Total predictions made |
| correct_predictions | INTEGER | Correct predictions |
| created_at | TIMESTAMP | First seen |

**analysis_results**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Internal ID |
| tweet_id | UUID FK | Reference to tweets |
| analysis_type | VARCHAR | signal/sentiment/credibility |
| result | JSONB | Structured Agent output |
| model_used | VARCHAR | Which LLM was used |
| confidence | FLOAT | 0-1 confidence score |
| batch_id | UUID | Batch identifier |
| created_at | TIMESTAMP | Analysis time |

**reports**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Internal ID |
| report_type | VARCHAR | daily/hourly/custom |
| market | VARCHAR | crypto/us_stock/a_stock/forex |
| summary | TEXT | Report text |
| signals_aggregated | JSONB | Aggregated signals |
| consensus_score | FLOAT | Agreement level |
| batch_id | UUID | Batch identifier |
| generated_at | TIMESTAMP | Generation time |

### Vector Store (Chroma, MVP; migrate to Milvus later)

- Collection: `tweet_embeddings`
- Metadata: author, market, published_at, tweet_id
- Purpose: semantic search for similar views, historical analogies

## Agent Design

### Supervisor Agent

**Role**: Receive tweet batch, route to sub-agents, aggregate results.

**State Schema**:
```python
class SupervisorState(TypedDict):
    tweets: list[dict]
    signals: list[dict]
    sentiments: list[dict]
    credibility_updates: list[dict]
    report: str | None
    current_step: str
```

**Routing Logic**:
1. Receive batch → Send fan-out to Signal Agent + Sentiment Agent (parallel)
2. Both complete → Trigger Credibility Agent (needs signal + sentiment as input)
3. Finally → Report Agent summarizes all results

### Signal Agent

**Input**: Tweet text
**Output**:
```json
{
  "ticker": "BTC",
  "direction": "long|short|neutral",
  "entry_price": 68000,
  "target_price": 72000,
  "stop_loss": 65000,
  "timeframe": "short_term|mid_term|long_term",
  "confidence": 0.8,
  "reasoning": "..."
}
```

**Tools**: extract_tickers (NER), parse_price_levels, query_similar_signals (vector search)

### Sentiment Agent

**Input**: Tweet text
**Output**:
```json
{
  "overall_sentiment": "bullish|bearish|neutral",
  "intensity": 0.75,
  "market": "crypto|us_stock|a_stock|forex",
  "topics": ["BTC", "ETF"],
  "emotion": "excited|fearful|calm|uncertain",
  "urgency": "high|medium|low"
}
```

**Tools**: classify_sentiment (LLM structured output), detect_urgency (signal word detection)

### Credibility Agent

**Input**: Current analysis results + blogger history
**Output**:
```json
{
  "blogger_handle": "@crypto_guru",
  "updated_score": 72,
  "accuracy_30d": 0.65,
  "hit_rate_by_market": {"crypto": 0.7, "us_stock": 0.6},
  "style_tags": ["short_term", "technical_analysis"],
  "risk_flag": false
}
```

**Tools**: query_history (PG), calculate_accuracy, update_credibility

### Report Agent

**Input**: Aggregated results from all sub-agents
**Output**: Structured Chinese-language market report

**Tools**: aggregate_signals, detect_consensus, generate_report

### Model Allocation

| Agent | Model | Reason |
|-------|-------|--------|
| Supervisor | DeepSeek | Lightweight routing |
| Signal Agent | DeepSeek | Structured extraction, fast+cheap |
| Sentiment Agent | DeepSeek | Classification task |
| Credibility Agent | DeepSeek | Data computation + simple judgment |
| Report Agent | Claude | High-quality generation, complex reasoning |

All models accessed via OpenRouter unified gateway.

## API Design

```
POST /api/tweets/import              — Bulk import tweets (crawler calls this)
POST /api/analysis/trigger           — Manually trigger analysis batch
GET  /api/analysis/stream/{batch_id} — SSE stream analysis progress

GET  /api/signals                    — Signal list (filter: market/ticker/time)
GET  /api/sentiments                 — Sentiment list
GET  /api/bloggers                   — Blogger list + credibility ranking
GET  /api/bloggers/{handle}          — Blogger detail + history
GET  /api/reports                    — Report list
GET  /api/reports/{id}               — Report detail

GET  /api/dashboard/overview         — Dashboard aggregated data
```

## Frontend (Next.js)

MVP: 4 pages

| Page | Content |
|------|---------|
| Dashboard | Today's signal overview, sentiment heatmap, active bloggers |
| Signals | Signal stream list, filter by market/direction |
| Bloggers | Blogger leaderboard, click for detail |
| Reports | Market consensus report timeline |

## Project Structure

```
finance-tweet-analyzer/
├── app/                        # FastAPI backend
│   ├── api/                   # Route handlers
│   │   ├── tweets.py
│   │   ├── analysis.py
│   │   ├── signals.py
│   │   ├── bloggers.py
│   │   ├── reports.py
│   │   └── dashboard.py
│   ├── agents/                # LangGraph Agent definitions
│   │   ├── supervisor.py
│   │   ├── signal_agent.py
│   │   ├── sentiment_agent.py
│   │   ├── credibility_agent.py
│   │   └── report_agent.py
│   ├── models/                # SQLAlchemy + Pydantic models
│   │   ├── db.py
│   │   ├── tweet.py
│   │   ├── blogger.py
│   │   ├── analysis.py
│   │   └── report.py
│   ├── services/              # Business logic
│   │   ├── tweet_service.py
│   │   └── analysis_service.py
│   ├── scheduler/             # Scheduled tasks (APScheduler)
│   │   └── tasks.py
│   ├── core/                  # Config, dependencies
│   │   ├── config.py
│   │   └── deps.py
│   └── main.py
├── frontend/                  # Next.js frontend
├── scripts/                   # Data import utilities
├── alembic/                   # Database migrations
├── tests/
└── pyproject.toml
```

## Data Flow

```
Crawler writes tweets (status=pending)
  → Scheduler scans pending tweets (hourly)
  → Batch sent to Supervisor
  → Fan-out: Signal Agent + Sentiment Agent (parallel)
  → Credibility Agent (depends on signal + sentiment)
  → Report Agent (aggregates all)
  → Results written to analysis_results
  → Report written to reports
  → tweets.status updated to "analyzed"
```

## MVP Scope (Phase 1)

1. Data import API (POST /api/tweets/import)
2. Signal Agent only (extract trading signals from tweets)
3. Basic Supervisor (simplified routing, no fan-out yet)
4. Signal list API + Dashboard overview API
5. Simple Next.js frontend (Dashboard + Signals page)
6. PostgreSQL + basic Chroma setup
7. Manual trigger (no scheduler yet)

## Future Iterations

- Phase 2: Add Sentiment Agent, enable parallel fan-out
- Phase 3: Add Credibility Agent, blogger scoring
- Phase 4: Add Report Agent, market consensus reports
- Phase 5: Scheduler automation, SSE progress streaming
- Phase 6: Milvus migration, advanced vector search
