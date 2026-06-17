# Finance Tweet Analyzer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working MVP that imports tweets, runs a Signal Agent to extract trading signals, and displays results through a FastAPI backend + Next.js frontend.

**Architecture:** FastAPI backend with LangGraph Supervisor dispatching a Signal Agent. PostgreSQL stores tweets and analysis results. Next.js frontend shows dashboard and signals list. All LLM calls go through OpenRouter with local proxy.

**Tech Stack:** Python 3.10+ (uv), FastAPI, SQLAlchemy 2.0, Alembic, LangGraph, LangChain, PostgreSQL, Next.js (TypeScript), Tailwind CSS

---

## File Structure

```
finance-tweet-analyzer/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry, CORS, router mounting
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic Settings (DB URL, API keys, proxy)
│   │   └── deps.py               # Dependency injection (get_db session)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py               # SQLAlchemy Base, common columns
│   │   ├── tweet.py              # Tweet ORM model
│   │   ├── blogger.py            # Blogger ORM model
│   │   └── analysis.py           # AnalysisResult ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── tweet.py              # Pydantic request/response schemas for tweets
│   │   ├── signal.py             # Signal output schema
│   │   └── dashboard.py          # Dashboard response schema
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py             # Top-level APIRouter that includes sub-routers
│   │   ├── tweets.py             # POST /api/tweets/import
│   │   ├── analysis.py           # POST /api/analysis/trigger
│   │   ├── signals.py            # GET /api/signals
│   │   └── dashboard.py          # GET /api/dashboard/overview
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── llm.py                # LLM factory (OpenRouter + proxy config)
│   │   ├── signal_agent.py       # Signal extraction Agent
│   │   └── supervisor.py         # Supervisor StateGraph
│   └── services/
│       ├── __init__.py
│       ├── tweet_service.py      # Tweet import logic
│       └── analysis_service.py   # Trigger analysis, call supervisor
├── alembic/
│   ├── env.py
│   └── versions/                 # Migration files
├── alembic.ini
├── frontend/                     # Next.js app (created via create-next-app)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx          # Dashboard page
│   │   │   └── signals/
│   │   │       └── page.tsx      # Signals list page
│   │   ├── components/
│   │   │   ├── SignalCard.tsx
│   │   │   ├── DashboardStats.tsx
│   │   │   └── Navbar.tsx
│   │   └── lib/
│   │       └── api.ts            # Fetch helpers
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Fixtures: test DB, test client
│   ├── test_tweet_import.py
│   ├── test_signal_agent.py
│   └── test_analysis_api.py
├── scripts/
│   └── seed_tweets.py            # Seed sample tweet data for development
├── pyproject.toml                 # Added to root or separate — see Task 1
└── .env.example
```

---

### Task 1: Project Scaffolding + Configuration

**Files:**
- Create: `finance-tweet-analyzer/app/__init__.py`
- Create: `finance-tweet-analyzer/app/core/__init__.py`
- Create: `finance-tweet-analyzer/app/core/config.py`
- Create: `finance-tweet-analyzer/app/core/deps.py`
- Create: `finance-tweet-analyzer/.env.example`
- Create: `finance-tweet-analyzer/pyproject.toml`

- [ ] **Step 1: Create project directory and pyproject.toml**

```bash
mkdir -p finance-tweet-analyzer
cd finance-tweet-analyzer
```

Create `finance-tweet-analyzer/pyproject.toml`:

```toml
[project]
name = "finance-tweet-analyzer"
version = "0.1.0"
description = "Financial tweet analysis platform with LangGraph multi-agent orchestration"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy>=2.0.0",
    "psycopg[binary,pool]>=3.2.0",
    "alembic>=1.15.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
    "langchain>=1.2.15",
    "langchain-openai>=1.1.11",
    "langgraph>=0.4.0",
    "langgraph-checkpoint-memory>=0.1.0",
    "httpx>=0.28.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.25.0",
    "httpx>=0.28.0",
]
```

- [ ] **Step 2: Create .env.example**

Create `finance-tweet-analyzer/.env.example`:

```env
# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets

# OpenRouter LLM
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
HTTP_PROXY=http://127.0.0.1:1080

# Models
SIGNAL_MODEL=deepseek/deepseek-chat
REPORT_MODEL=anthropic/claude-sonnet-4-20250514
```

- [ ] **Step 3: Create config.py with Pydantic Settings**

Create `finance-tweet-analyzer/app/__init__.py` (empty file).
Create `finance-tweet-analyzer/app/core/__init__.py` (empty file).

Create `finance-tweet-analyzer/app/core/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    http_proxy: str = "http://127.0.0.1:1080"
    signal_model: str = "deepseek/deepseek-chat"
    report_model: str = "anthropic/claude-sonnet-4-20250514"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Create deps.py with DB session factory**

Create `finance-tweet-analyzer/app/core/deps.py`:

```python
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Install dependencies**

```bash
cd finance-tweet-analyzer
uv sync
```

- [ ] **Step 6: Commit**

```bash
git add finance-tweet-analyzer/
git commit -m "feat: scaffold finance-tweet-analyzer project with config"
```

---

### Task 2: Database Models + Alembic Migration

**Files:**
- Create: `finance-tweet-analyzer/app/models/__init__.py`
- Create: `finance-tweet-analyzer/app/models/base.py`
- Create: `finance-tweet-analyzer/app/models/tweet.py`
- Create: `finance-tweet-analyzer/app/models/blogger.py`
- Create: `finance-tweet-analyzer/app/models/analysis.py`
- Create: `finance-tweet-analyzer/alembic.ini`
- Create: `finance-tweet-analyzer/alembic/env.py`

- [ ] **Step 1: Create base model with common columns**

Create `finance-tweet-analyzer/app/models/__init__.py`:

```python
from app.models.base import Base
from app.models.tweet import Tweet
from app.models.blogger import Blogger
from app.models.analysis import AnalysisResult

__all__ = ["Base", "Tweet", "Blogger", "AnalysisResult"]
```

Create `finance-tweet-analyzer/app/models/base.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 2: Create Tweet model**

Create `finance-tweet-analyzer/app/models/tweet.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tweet(Base, TimestampMixin):
    __tablename__ = "tweets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tweet_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    author_handle: Mapped[str] = mapped_column(String(128), index=True)
    author_name: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict | None] = mapped_column(JSONB, default=None)
    media_urls: Mapped[dict | None] = mapped_column(JSONB, default=None)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
```

- [ ] **Step 3: Create Blogger model**

Create `finance-tweet-analyzer/app/models/blogger.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Blogger(Base, TimestampMixin):
    __tablename__ = "bloggers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    handle: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    market_focus: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=None)
    credibility_score: Mapped[float] = mapped_column(Float, default=50.0)
    total_predictions: Mapped[int] = mapped_column(Integer, default=0)
    correct_predictions: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 4: Create AnalysisResult model**

Create `finance-tweet-analyzer/app/models/analysis.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AnalysisResult(Base, TimestampMixin):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tweet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tweets.id"), index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(32), index=True)
    result: Mapped[dict] = mapped_column(JSONB)
    model_used: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
```

- [ ] **Step 5: Initialize Alembic**

```bash
cd finance-tweet-analyzer
uv run alembic init alembic
```

Then edit `finance-tweet-analyzer/alembic.ini` — replace the `sqlalchemy.url` line:

```ini
sqlalchemy.url = postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets
```

Replace `finance-tweet-analyzer/alembic/env.py` with:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: Generate and run migration**

```bash
cd finance-tweet-analyzer
uv run alembic revision --autogenerate -m "initial tables: tweets, bloggers, analysis_results"
uv run alembic upgrade head
```

Expected: Tables `tweets`, `bloggers`, `analysis_results` created in PostgreSQL.

- [ ] **Step 7: Commit**

```bash
git add finance-tweet-analyzer/app/models/ finance-tweet-analyzer/alembic/ finance-tweet-analyzer/alembic.ini
git commit -m "feat: add database models and initial migration"
```

---

### Task 3: Pydantic Schemas + Tweet Import API

**Files:**
- Create: `finance-tweet-analyzer/app/schemas/__init__.py`
- Create: `finance-tweet-analyzer/app/schemas/tweet.py`
- Create: `finance-tweet-analyzer/app/services/__init__.py`
- Create: `finance-tweet-analyzer/app/services/tweet_service.py`
- Create: `finance-tweet-analyzer/app/api/__init__.py`
- Create: `finance-tweet-analyzer/app/api/router.py`
- Create: `finance-tweet-analyzer/app/api/tweets.py`
- Create: `finance-tweet-analyzer/app/main.py`
- Create: `finance-tweet-analyzer/tests/__init__.py`
- Create: `finance-tweet-analyzer/tests/conftest.py`
- Create: `finance-tweet-analyzer/tests/test_tweet_import.py`

- [ ] **Step 1: Write the failing test for tweet import**

Create `finance-tweet-analyzer/tests/__init__.py` (empty).

Create `finance-tweet-analyzer/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

Create `finance-tweet-analyzer/tests/test_tweet_import.py`:

```python
def test_import_tweets_success(client):
    payload = {
        "tweets": [
            {
                "tweet_id": "1234567890",
                "author_handle": "@crypto_whale",
                "author_name": "Crypto Whale",
                "content": "BTC looks ready to break 70k. Loading spot here with target 75k.",
                "published_at": "2026-05-26T10:30:00Z",
                "metrics": {"likes": 500, "retweets": 120},
            }
        ]
    }
    response = client.post("/api/tweets/import", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["imported"] == 1
    assert data["skipped"] == 0


def test_import_tweets_dedup(client):
    tweet = {
        "tweet_id": "1234567890",
        "author_handle": "@crypto_whale",
        "author_name": "Crypto Whale",
        "content": "BTC long signal",
        "published_at": "2026-05-26T10:30:00Z",
    }
    client.post("/api/tweets/import", json={"tweets": [tweet]})
    response = client.post("/api/tweets/import", json={"tweets": [tweet]})
    data = response.json()
    assert data["imported"] == 0
    assert data["skipped"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_tweet_import.py -v
```

Expected: FAIL — `app.main` module not found.

- [ ] **Step 3: Create Pydantic schemas**

Create `finance-tweet-analyzer/app/schemas/__init__.py` (empty).

Create `finance-tweet-analyzer/app/schemas/tweet.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class TweetImportItem(BaseModel):
    tweet_id: str
    author_handle: str
    author_name: str = ""
    content: str
    published_at: datetime
    metrics: dict | None = None
    media_urls: dict | None = None
    raw_json: dict | None = None


class TweetImportRequest(BaseModel):
    tweets: list[TweetImportItem]


class TweetImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = []
```

- [ ] **Step 4: Create tweet service**

Create `finance-tweet-analyzer/app/services/__init__.py` (empty).

Create `finance-tweet-analyzer/app/services/tweet_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blogger import Blogger
from app.models.tweet import Tweet
from app.schemas.tweet import TweetImportItem


def import_tweets(db: Session, items: list[TweetImportItem]) -> tuple[int, int]:
    imported = 0
    skipped = 0

    for item in items:
        exists = db.execute(
            select(Tweet).where(Tweet.tweet_id == item.tweet_id)
        ).scalar_one_or_none()

        if exists:
            skipped += 1
            continue

        tweet = Tweet(
            tweet_id=item.tweet_id,
            author_handle=item.author_handle,
            author_name=item.author_name,
            content=item.content,
            published_at=item.published_at,
            metrics=item.metrics,
            media_urls=item.media_urls,
            raw_json=item.raw_json,
            status="pending",
        )
        db.add(tweet)

        _ensure_blogger(db, item.author_handle, item.author_name)
        imported += 1

    db.commit()
    return imported, skipped


def _ensure_blogger(db: Session, handle: str, name: str) -> None:
    exists = db.execute(
        select(Blogger).where(Blogger.handle == handle)
    ).scalar_one_or_none()

    if not exists:
        db.add(Blogger(handle=handle, name=name))
```

- [ ] **Step 5: Create API route and main app**

Create `finance-tweet-analyzer/app/api/__init__.py` (empty).

Create `finance-tweet-analyzer/app/api/tweets.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.tweet import TweetImportRequest, TweetImportResponse
from app.services.tweet_service import import_tweets

router = APIRouter(prefix="/api/tweets", tags=["tweets"])


@router.post("/import", response_model=TweetImportResponse)
def import_tweets_endpoint(
    request: TweetImportRequest,
    db: Session = Depends(get_db),
):
    imported, skipped = import_tweets(db, request.tweets)
    return TweetImportResponse(imported=imported, skipped=skipped)
```

Create `finance-tweet-analyzer/app/api/router.py`:

```python
from fastapi import APIRouter

from app.api.tweets import router as tweets_router

api_router = APIRouter()
api_router.include_router(tweets_router)
```

Create `finance-tweet-analyzer/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router

app = FastAPI(title="Finance Tweet Analyzer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_tweet_import.py -v
```

Expected: 2 tests PASS.

Note: SQLite doesn't support PostgreSQL-specific types (JSONB, UUID, ARRAY). If tests fail on type issues, modify `conftest.py` to use conditional type mappings or switch to a test PostgreSQL database. For simplicity in MVP, add this to `conftest.py` before the engine creation:

```python
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

If SQLite type issues persist, replace test DB with a real PostgreSQL test database using `DATABASE_URL` env var override in tests.

- [ ] **Step 7: Commit**

```bash
git add finance-tweet-analyzer/app/ finance-tweet-analyzer/tests/
git commit -m "feat: add tweet import API with deduplication"
```

---

### Task 4: LLM Factory + Signal Agent

**Files:**
- Create: `finance-tweet-analyzer/app/agents/__init__.py`
- Create: `finance-tweet-analyzer/app/agents/llm.py`
- Create: `finance-tweet-analyzer/app/agents/signal_agent.py`
- Create: `finance-tweet-analyzer/app/schemas/signal.py`
- Create: `finance-tweet-analyzer/tests/test_signal_agent.py`

- [ ] **Step 1: Write the failing test for signal extraction**

Create `finance-tweet-analyzer/tests/test_signal_agent.py`:

```python
from app.agents.signal_agent import extract_signal_from_tweet


def test_signal_output_structure():
    """Test that signal agent returns properly structured output."""
    tweet_content = "BTC breaking 70k resistance. Entry 69500, target 75000, stop 67000. Short term swing."
    result = extract_signal_from_tweet(tweet_content, author_handle="@test_trader")

    assert "ticker" in result
    assert "direction" in result
    assert result["direction"] in ("long", "short", "neutral")
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1


def test_signal_no_signal_tweet():
    """Test that non-signal tweets return neutral with low confidence."""
    tweet_content = "Good morning everyone! Hope you have a great day."
    result = extract_signal_from_tweet(tweet_content, author_handle="@random_user")

    assert result["direction"] == "neutral"
    assert result["confidence"] < 0.3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_signal_agent.py -v
```

Expected: FAIL — `app.agents.signal_agent` not found.

- [ ] **Step 3: Create LLM factory**

Create `finance-tweet-analyzer/app/agents/__init__.py` (empty).

Create `finance-tweet-analyzer/app/agents/llm.py`:

```python
import httpx
from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_signal_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.signal_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        max_tokens=2048,
        temperature=0.1,
        timeout=30,
        http_client=httpx.Client(proxy=settings.http_proxy),
    )


def get_report_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.report_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        max_tokens=4096,
        temperature=0.3,
        timeout=60,
        http_client=httpx.Client(proxy=settings.http_proxy),
    )
```

- [ ] **Step 4: Create signal output schema**

Create `finance-tweet-analyzer/app/schemas/signal.py`:

```python
from pydantic import BaseModel, Field


class SignalOutput(BaseModel):
    ticker: str = Field(description="Trading symbol, e.g. BTC, AAPL, ETH")
    direction: str = Field(description="long, short, or neutral")
    entry_price: float | None = Field(default=None, description="Entry price if mentioned")
    target_price: float | None = Field(default=None, description="Target price if mentioned")
    stop_loss: float | None = Field(default=None, description="Stop loss price if mentioned")
    timeframe: str = Field(default="unknown", description="short_term, mid_term, long_term, or unknown")
    confidence: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(default="", description="Brief reasoning in Chinese")
```

- [ ] **Step 5: Implement Signal Agent**

Create `finance-tweet-analyzer/app/agents/signal_agent.py`:

```python
from langchain_core.prompts import ChatPromptTemplate

from app.agents.llm import get_signal_llm
from app.schemas.signal import SignalOutput

SIGNAL_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的金融交易信号提取分析师。

从推文中提取交易信号，输出结构化JSON。规则：
1. ticker: 识别提到的交易标的（BTC、ETH、AAPL等）。如果没有明确标的，填 "UNKNOWN"
2. direction: 判断是看多(long)、看空(short)还是中性(neutral)
3. entry_price/target_price/stop_loss: 如果推文中提到具体价格，填入数字；否则填 null
4. timeframe: 根据上下文判断是短线(short_term)、中线(mid_term)、长线(long_term)，不确定填 unknown
5. confidence: 你对这个信号判断的置信度(0-1)。如果推文不包含任何交易信号，置信度应低于0.3，direction设为neutral
6. reasoning: 用中文简要说明判断依据

注意：很多推文不包含交易信号（如日常闲聊、新闻转发），这时confidence应该很低。"""),
    ("human", "博主: {author_handle}\n推文内容: {content}")
])


def extract_signal_from_tweet(content: str, author_handle: str) -> dict:
    llm = get_signal_llm()
    structured_llm = llm.with_structured_output(SignalOutput)
    chain = SIGNAL_EXTRACTION_PROMPT | structured_llm
    result = chain.invoke({"content": content, "author_handle": author_handle})
    return result.model_dump()
```

- [ ] **Step 6: Run tests**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_signal_agent.py -v
```

Expected: PASS (requires valid OpenRouter API key in .env and network access).

Note: If running without API access, these tests will fail. For CI, mock the LLM call. For local dev with a real key, they should pass.

- [ ] **Step 7: Commit**

```bash
git add finance-tweet-analyzer/app/agents/ finance-tweet-analyzer/app/schemas/signal.py finance-tweet-analyzer/tests/test_signal_agent.py
git commit -m "feat: implement Signal Agent with structured output"
```

---

### Task 5: Supervisor StateGraph

**Files:**
- Create: `finance-tweet-analyzer/app/agents/supervisor.py`
- Create: `finance-tweet-analyzer/app/services/analysis_service.py`
- Create: `finance-tweet-analyzer/tests/test_analysis_api.py`

- [ ] **Step 1: Write the failing test for analysis service**

Create `finance-tweet-analyzer/tests/test_analysis_api.py`:

```python
def test_trigger_analysis(client):
    # First import a tweet
    payload = {
        "tweets": [
            {
                "tweet_id": "signal_tweet_001",
                "author_handle": "@btc_analyst",
                "author_name": "BTC Analyst",
                "content": "BTC突破70000阻力位，入场69500，目标75000，止损67000。短线波段。",
                "published_at": "2026-05-26T10:30:00Z",
            }
        ]
    }
    client.post("/api/tweets/import", json=payload)

    # Trigger analysis
    response = client.post("/api/analysis/trigger")
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] is not None
    assert data["analyzed"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_analysis_api.py -v
```

Expected: FAIL — no `/api/analysis/trigger` endpoint.

- [ ] **Step 3: Implement Supervisor StateGraph**

Create `finance-tweet-analyzer/app/agents/supervisor.py`:

```python
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.agents.signal_agent import extract_signal_from_tweet


class SupervisorState(TypedDict):
    tweets: list[dict]
    signals: list[dict]
    current_index: int


def process_signals(state: SupervisorState) -> dict:
    signals = []
    for tweet in state["tweets"]:
        signal = extract_signal_from_tweet(
            content=tweet["content"],
            author_handle=tweet["author_handle"],
        )
        signal["tweet_id"] = tweet["id"]
        signals.append(signal)
    return {"signals": signals}


def build_supervisor_graph() -> StateGraph:
    graph = StateGraph(SupervisorState)
    graph.add_node("extract_signals", process_signals)
    graph.add_edge(START, "extract_signals")
    graph.add_edge("extract_signals", END)
    return graph.compile()


supervisor = build_supervisor_graph()
```

- [ ] **Step 4: Implement analysis service**

Create `finance-tweet-analyzer/app/services/analysis_service.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.supervisor import supervisor
from app.models.analysis import AnalysisResult
from app.models.tweet import Tweet


def trigger_analysis(db: Session) -> tuple[str, int]:
    batch_id = uuid.uuid4()

    pending_tweets = db.execute(
        select(Tweet).where(Tweet.status == "pending").limit(50)
    ).scalars().all()

    if not pending_tweets:
        return str(batch_id), 0

    tweet_dicts = [
        {
            "id": str(t.id),
            "content": t.content,
            "author_handle": t.author_handle,
        }
        for t in pending_tweets
    ]

    result = supervisor.invoke({
        "tweets": tweet_dicts,
        "signals": [],
        "current_index": 0,
    })

    for signal in result["signals"]:
        analysis = AnalysisResult(
            tweet_id=uuid.UUID(signal.pop("tweet_id")),
            analysis_type="signal",
            result=signal,
            model_used="deepseek/deepseek-chat",
            confidence=signal.get("confidence", 0.0),
            batch_id=batch_id,
        )
        db.add(analysis)

    for tweet in pending_tweets:
        tweet.status = "analyzed"

    db.commit()
    return str(batch_id), len(pending_tweets)
```

- [ ] **Step 5: Create analysis API endpoint**

Create `finance-tweet-analyzer/app/api/analysis.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.services.analysis_service import trigger_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class TriggerResponse(BaseModel):
    batch_id: str
    analyzed: int


@router.post("/trigger", response_model=TriggerResponse)
def trigger_analysis_endpoint(db: Session = Depends(get_db)):
    batch_id, analyzed = trigger_analysis(db)
    return TriggerResponse(batch_id=batch_id, analyzed=analyzed)
```

Update `finance-tweet-analyzer/app/api/router.py`:

```python
from fastapi import APIRouter

from app.api.tweets import router as tweets_router
from app.api.analysis import router as analysis_router

api_router = APIRouter()
api_router.include_router(tweets_router)
api_router.include_router(analysis_router)
```

- [ ] **Step 6: Run tests**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_analysis_api.py -v
```

Expected: PASS (with real API key) or controlled failure (without key — mock for CI).

- [ ] **Step 7: Commit**

```bash
git add finance-tweet-analyzer/app/agents/supervisor.py finance-tweet-analyzer/app/services/analysis_service.py finance-tweet-analyzer/app/api/analysis.py finance-tweet-analyzer/app/api/router.py finance-tweet-analyzer/tests/test_analysis_api.py
git commit -m "feat: add Supervisor graph and analysis trigger API"
```

---

### Task 6: Signals List + Dashboard API

**Files:**
- Create: `finance-tweet-analyzer/app/api/signals.py`
- Create: `finance-tweet-analyzer/app/api/dashboard.py`
- Create: `finance-tweet-analyzer/app/schemas/dashboard.py`

- [ ] **Step 1: Write failing test for signals list**

Add to `finance-tweet-analyzer/tests/test_analysis_api.py`:

```python
def test_get_signals_empty(client):
    response = client.get("/api/signals")
    assert response.status_code == 200
    data = response.json()
    assert data["signals"] == []
    assert data["total"] == 0


def test_get_dashboard_overview(client):
    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_tweets" in data
    assert "pending_tweets" in data
    assert "total_signals" in data
    assert "recent_signals" in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_analysis_api.py::test_get_signals_empty -v
```

Expected: FAIL — 404, no route.

- [ ] **Step 3: Create dashboard schema**

Create `finance-tweet-analyzer/app/schemas/dashboard.py`:

```python
from pydantic import BaseModel


class DashboardOverview(BaseModel):
    total_tweets: int
    pending_tweets: int
    analyzed_tweets: int
    total_signals: int
    total_bloggers: int
    recent_signals: list[dict]
```

- [ ] **Step 4: Implement signals endpoint**

Create `finance-tweet-analyzer/app/api/signals.py`:

```python
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.analysis import AnalysisResult
from app.models.tweet import Tweet

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalItem(BaseModel):
    id: str
    tweet_id: str
    author_handle: str
    content: str
    signal: dict
    confidence: float
    created_at: str


class SignalsResponse(BaseModel):
    signals: list[SignalItem]
    total: int


@router.get("", response_model=SignalsResponse)
def list_signals(
    market: str | None = Query(None),
    direction: str | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    query = (
        select(AnalysisResult, Tweet)
        .join(Tweet, AnalysisResult.tweet_id == Tweet.id)
        .where(AnalysisResult.analysis_type == "signal")
        .order_by(AnalysisResult.created_at.desc())
    )

    if direction:
        query = query.where(AnalysisResult.result["direction"].astext == direction)

    count_query = select(func.count()).select_from(
        select(AnalysisResult)
        .where(AnalysisResult.analysis_type == "signal")
        .subquery()
    )
    total = db.execute(count_query).scalar() or 0

    rows = db.execute(query.limit(limit).offset(offset)).all()

    signals = [
        SignalItem(
            id=str(ar.id),
            tweet_id=str(ar.tweet_id),
            author_handle=tw.author_handle,
            content=tw.content,
            signal=ar.result,
            confidence=ar.confidence,
            created_at=ar.created_at.isoformat() if ar.created_at else "",
        )
        for ar, tw in rows
    ]

    return SignalsResponse(signals=signals, total=total)
```

- [ ] **Step 5: Implement dashboard endpoint**

Create `finance-tweet-analyzer/app/api/dashboard.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.analysis import AnalysisResult
from app.models.blogger import Blogger
from app.models.tweet import Tweet
from app.schemas.dashboard import DashboardOverview

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def get_overview(db: Session = Depends(get_db)):
    total_tweets = db.execute(select(func.count(Tweet.id))).scalar() or 0
    pending_tweets = db.execute(
        select(func.count(Tweet.id)).where(Tweet.status == "pending")
    ).scalar() or 0
    analyzed_tweets = db.execute(
        select(func.count(Tweet.id)).where(Tweet.status == "analyzed")
    ).scalar() or 0
    total_signals = db.execute(
        select(func.count(AnalysisResult.id)).where(
            AnalysisResult.analysis_type == "signal"
        )
    ).scalar() or 0
    total_bloggers = db.execute(select(func.count(Blogger.id))).scalar() or 0

    recent_query = (
        select(AnalysisResult)
        .where(AnalysisResult.analysis_type == "signal")
        .order_by(AnalysisResult.created_at.desc())
        .limit(5)
    )
    recent = db.execute(recent_query).scalars().all()
    recent_signals = [
        {"id": str(r.id), "result": r.result, "confidence": r.confidence}
        for r in recent
    ]

    return DashboardOverview(
        total_tweets=total_tweets,
        pending_tweets=pending_tweets,
        analyzed_tweets=analyzed_tweets,
        total_signals=total_signals,
        total_bloggers=total_bloggers,
        recent_signals=recent_signals,
    )
```

- [ ] **Step 6: Register new routers**

Update `finance-tweet-analyzer/app/api/router.py`:

```python
from fastapi import APIRouter

from app.api.tweets import router as tweets_router
from app.api.analysis import router as analysis_router
from app.api.signals import router as signals_router
from app.api.dashboard import router as dashboard_router

api_router = APIRouter()
api_router.include_router(tweets_router)
api_router.include_router(analysis_router)
api_router.include_router(signals_router)
api_router.include_router(dashboard_router)
```

- [ ] **Step 7: Run tests**

```bash
cd finance-tweet-analyzer
uv run pytest tests/test_analysis_api.py -v
```

Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add finance-tweet-analyzer/app/api/ finance-tweet-analyzer/app/schemas/dashboard.py finance-tweet-analyzer/tests/
git commit -m "feat: add signals list and dashboard overview APIs"
```

---

### Task 7: Seed Script for Development

**Files:**
- Create: `finance-tweet-analyzer/scripts/seed_tweets.py`

- [ ] **Step 1: Create seed script with sample tweets**

Create `finance-tweet-analyzer/scripts/seed_tweets.py`:

```python
"""Seed sample tweet data for development and demo."""
import httpx

SAMPLE_TWEETS = [
    {
        "tweet_id": "seed_001",
        "author_handle": "@btc_master",
        "author_name": "BTC大师",
        "content": "BTC突破70000关键阻力位，放量上攻。建议入场69500，目标75000，止损67000。短线波段机会。",
        "published_at": "2026-05-26T08:00:00Z",
        "metrics": {"likes": 1200, "retweets": 350},
    },
    {
        "tweet_id": "seed_002",
        "author_handle": "@eth_whale",
        "author_name": "以太坊巨鲸",
        "content": "ETH/BTC汇率见底反弹，ETH有望补涨。目前3800附近建仓，看4500。",
        "published_at": "2026-05-26T09:15:00Z",
        "metrics": {"likes": 800, "retweets": 200},
    },
    {
        "tweet_id": "seed_003",
        "author_handle": "@stock_tiger",
        "author_name": "美股之虎",
        "content": "NVDA财报超预期，AI算力需求持续爆发。回调到950可以接，中线目标1200。",
        "published_at": "2026-05-26T10:00:00Z",
        "metrics": {"likes": 2000, "retweets": 500},
    },
    {
        "tweet_id": "seed_004",
        "author_handle": "@forex_pro",
        "author_name": "外汇达人",
        "content": "美元指数走弱，非美货币全线反弹。EUR/USD看涨至1.12，当前1.085入场。",
        "published_at": "2026-05-26T11:30:00Z",
        "metrics": {"likes": 600, "retweets": 150},
    },
    {
        "tweet_id": "seed_005",
        "author_handle": "@btc_master",
        "author_name": "BTC大师",
        "content": "今天天气真好，带孩子去公园了。周末愉快！",
        "published_at": "2026-05-26T14:00:00Z",
        "metrics": {"likes": 300, "retweets": 20},
    },
    {
        "tweet_id": "seed_006",
        "author_handle": "@a_share_king",
        "author_name": "A股之王",
        "content": "贵州茅台跌破1600支撑位，短期看空。但长期价值投资者可以在1500附近分批建仓。",
        "published_at": "2026-05-26T09:45:00Z",
        "metrics": {"likes": 1500, "retweets": 400},
    },
    {
        "tweet_id": "seed_007",
        "author_handle": "@crypto_degen",
        "author_name": "加密赌狗",
        "content": "SOL生态太火了！BONK下一个100x！梭哈！🚀🚀🚀",
        "published_at": "2026-05-26T12:00:00Z",
        "metrics": {"likes": 5000, "retweets": 2000},
    },
    {
        "tweet_id": "seed_008",
        "author_handle": "@macro_view",
        "author_name": "宏观视角",
        "content": "美联储6月大概率暂停加息，风险资产短期利好。但通胀粘性依然存在，下半年不确定性大。整体中性偏多。",
        "published_at": "2026-05-26T07:30:00Z",
        "metrics": {"likes": 3000, "retweets": 800},
    },
]

API_BASE = "http://localhost:8000"


def seed():
    response = httpx.post(
        f"{API_BASE}/api/tweets/import",
        json={"tweets": SAMPLE_TWEETS},
        timeout=10,
    )
    print(f"Import result: {response.json()}")

    response = httpx.post(f"{API_BASE}/api/analysis/trigger", timeout=120)
    print(f"Analysis result: {response.json()}")


if __name__ == "__main__":
    seed()
```

- [ ] **Step 2: Test the seed script (manual, requires running server)**

```bash
cd finance-tweet-analyzer
# Terminal 1: start the server
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2: run seed
uv run python scripts/seed_tweets.py
```

Expected: Tweets imported, analysis triggered, signals generated.

- [ ] **Step 3: Commit**

```bash
git add finance-tweet-analyzer/scripts/
git commit -m "feat: add seed script with sample financial tweets"
```

---

### Task 8: Next.js Frontend Setup

**Files:**
- Create: `finance-tweet-analyzer/frontend/` (via create-next-app)
- Create: `finance-tweet-analyzer/frontend/src/lib/api.ts`
- Create: `finance-tweet-analyzer/frontend/src/components/Navbar.tsx`

- [ ] **Step 1: Initialize Next.js project**

```bash
cd finance-tweet-analyzer
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --no-import-alias
```

When prompted, select defaults (Yes to all). This creates the Next.js app with TypeScript + Tailwind + App Router.

- [ ] **Step 2: Create API helper**

Create `finance-tweet-analyzer/frontend/src/lib/api.ts`:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchDashboard() {
  const res = await fetch(`${API_BASE}/api/dashboard/overview`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

export async function fetchSignals(params?: {
  direction?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.direction) searchParams.set("direction", params.direction);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));

  const url = `${API_BASE}/api/signals?${searchParams.toString()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch signals");
  return res.json();
}

export async function triggerAnalysis() {
  const res = await fetch(`${API_BASE}/api/analysis/trigger`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to trigger analysis");
  return res.json();
}
```

- [ ] **Step 3: Create Navbar component**

Create `finance-tweet-analyzer/frontend/src/components/Navbar.tsx`:

```typescript
import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="bg-gray-900 text-white px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link href="/" className="text-xl font-bold">
          📊 Finance Tweet Analyzer
        </Link>
        <div className="flex gap-6">
          <Link href="/" className="hover:text-blue-400">
            Dashboard
          </Link>
          <Link href="/signals" className="hover:text-blue-400">
            Signals
          </Link>
        </div>
      </div>
    </nav>
  );
}
```

- [ ] **Step 4: Update root layout**

Replace `finance-tweet-analyzer/frontend/src/app/layout.tsx`:

```typescript
import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "Finance Tweet Analyzer",
  description: "AI-powered financial tweet analysis platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50 min-h-screen">
        <Navbar />
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add finance-tweet-analyzer/frontend/
git commit -m "feat: scaffold Next.js frontend with Navbar and API helpers"
```

---

### Task 9: Dashboard Page

**Files:**
- Create: `finance-tweet-analyzer/frontend/src/components/DashboardStats.tsx`
- Modify: `finance-tweet-analyzer/frontend/src/app/page.tsx`

- [ ] **Step 1: Create DashboardStats component**

Create `finance-tweet-analyzer/frontend/src/components/DashboardStats.tsx`:

```typescript
interface StatsProps {
  totalTweets: number;
  pendingTweets: number;
  analyzedTweets: number;
  totalSignals: number;
  totalBloggers: number;
}

export default function DashboardStats({
  totalTweets,
  pendingTweets,
  analyzedTweets,
  totalSignals,
  totalBloggers,
}: StatsProps) {
  const stats = [
    { label: "总推文数", value: totalTweets, color: "bg-blue-500" },
    { label: "待分析", value: pendingTweets, color: "bg-yellow-500" },
    { label: "已分析", value: analyzedTweets, color: "bg-green-500" },
    { label: "交易信号", value: totalSignals, color: "bg-purple-500" },
    { label: "博主数", value: totalBloggers, color: "bg-pink-500" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      {stats.map((stat) => (
        <div key={stat.label} className="bg-white rounded-lg shadow p-4">
          <div className={`w-2 h-2 rounded-full ${stat.color} mb-2`} />
          <p className="text-2xl font-bold">{stat.value}</p>
          <p className="text-sm text-gray-500">{stat.label}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create Dashboard page**

Replace `finance-tweet-analyzer/frontend/src/app/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import DashboardStats from "@/components/DashboardStats";
import { fetchDashboard, triggerAnalysis } from "@/lib/api";

interface DashboardData {
  total_tweets: number;
  pending_tweets: number;
  analyzed_tweets: number;
  total_signals: number;
  total_bloggers: number;
  recent_signals: Array<{
    id: string;
    result: Record<string, unknown>;
    confidence: number;
  }>;
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);

  const loadData = async () => {
    try {
      const result = await fetchDashboard();
      setData(result);
    } catch (e) {
      console.error("Failed to load dashboard:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleTrigger = async () => {
    setAnalyzing(true);
    try {
      const result = await triggerAnalysis();
      alert(`分析完成！处理了 ${result.analyzed} 条推文`);
      loadData();
    } catch (e) {
      alert("分析触发失败");
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) return <p className="text-center py-10">加载中...</p>;
  if (!data) return <p className="text-center py-10 text-red-500">加载失败</p>;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button
          onClick={handleTrigger}
          disabled={analyzing}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {analyzing ? "分析中..." : "触发分析"}
        </button>
      </div>

      <DashboardStats
        totalTweets={data.total_tweets}
        pendingTweets={data.pending_tweets}
        analyzedTweets={data.analyzed_tweets}
        totalSignals={data.total_signals}
        totalBloggers={data.total_bloggers}
      />

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">最近信号</h2>
        {data.recent_signals.length === 0 ? (
          <p className="text-gray-500">暂无信号数据</p>
        ) : (
          <div className="space-y-3">
            {data.recent_signals.map((signal) => (
              <div
                key={signal.id}
                className="border rounded p-3 flex justify-between items-center"
              >
                <div>
                  <span className="font-mono font-bold">
                    {(signal.result as any).ticker || "UNKNOWN"}
                  </span>
                  <span
                    className={`ml-2 px-2 py-0.5 rounded text-xs ${
                      (signal.result as any).direction === "long"
                        ? "bg-green-100 text-green-800"
                        : (signal.result as any).direction === "short"
                        ? "bg-red-100 text-red-800"
                        : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {(signal.result as any).direction}
                  </span>
                </div>
                <span className="text-sm text-gray-500">
                  置信度: {(signal.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify it renders**

```bash
cd finance-tweet-analyzer/frontend
npm run dev
```

Open `http://localhost:3000` — should show dashboard with stats (all zeros if no data).

- [ ] **Step 4: Commit**

```bash
git add finance-tweet-analyzer/frontend/src/
git commit -m "feat: implement Dashboard page with stats and recent signals"
```

---

### Task 10: Signals List Page

**Files:**
- Create: `finance-tweet-analyzer/frontend/src/components/SignalCard.tsx`
- Create: `finance-tweet-analyzer/frontend/src/app/signals/page.tsx`

- [ ] **Step 1: Create SignalCard component**

Create `finance-tweet-analyzer/frontend/src/components/SignalCard.tsx`:

```typescript
interface SignalCardProps {
  authorHandle: string;
  content: string;
  signal: {
    ticker: string;
    direction: string;
    entry_price: number | null;
    target_price: number | null;
    stop_loss: number | null;
    timeframe: string;
    confidence: number;
    reasoning: string;
  };
  createdAt: string;
}

export default function SignalCard({
  authorHandle,
  content,
  signal,
  createdAt,
}: SignalCardProps) {
  const directionColor =
    signal.direction === "long"
      ? "border-green-400 bg-green-50"
      : signal.direction === "short"
      ? "border-red-400 bg-red-50"
      : "border-gray-300 bg-gray-50";

  return (
    <div className={`border-l-4 rounded-lg shadow p-4 ${directionColor}`}>
      <div className="flex justify-between items-start mb-2">
        <div>
          <span className="font-bold text-lg">{signal.ticker}</span>
          <span
            className={`ml-2 px-2 py-0.5 rounded text-xs font-semibold ${
              signal.direction === "long"
                ? "bg-green-200 text-green-900"
                : signal.direction === "short"
                ? "bg-red-200 text-red-900"
                : "bg-gray-200 text-gray-900"
            }`}
          >
            {signal.direction.toUpperCase()}
          </span>
          <span className="ml-2 text-xs text-gray-500">{signal.timeframe}</span>
        </div>
        <span className="text-sm text-gray-500">
          {(signal.confidence * 100).toFixed(0)}%
        </span>
      </div>

      <p className="text-sm text-gray-700 mb-2">{content}</p>

      <div className="flex gap-4 text-xs text-gray-600 mb-2">
        {signal.entry_price && <span>入场: {signal.entry_price}</span>}
        {signal.target_price && <span>目标: {signal.target_price}</span>}
        {signal.stop_loss && <span>止损: {signal.stop_loss}</span>}
      </div>

      {signal.reasoning && (
        <p className="text-xs text-gray-500 italic">{signal.reasoning}</p>
      )}

      <div className="flex justify-between items-center mt-2 pt-2 border-t">
        <span className="text-xs text-gray-500">{authorHandle}</span>
        <span className="text-xs text-gray-400">
          {new Date(createdAt).toLocaleString("zh-CN")}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create Signals page**

Create `finance-tweet-analyzer/frontend/src/app/signals/page.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import SignalCard from "@/components/SignalCard";
import { fetchSignals } from "@/lib/api";

interface SignalItem {
  id: string;
  tweet_id: string;
  author_handle: string;
  content: string;
  signal: {
    ticker: string;
    direction: string;
    entry_price: number | null;
    target_price: number | null;
    stop_loss: number | null;
    timeframe: string;
    confidence: number;
    reasoning: string;
  };
  confidence: number;
  created_at: string;
}

export default function SignalsPage() {
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const loadSignals = async (direction?: string) => {
    setLoading(true);
    try {
      const result = await fetchSignals({
        direction: direction || undefined,
        limit: 20,
      });
      setSignals(result.signals);
      setTotal(result.total);
    } catch (e) {
      console.error("Failed to load signals:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSignals(filter);
  }, [filter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">交易信号 ({total})</h1>
        <div className="flex gap-2">
          {["", "long", "short", "neutral"].map((dir) => (
            <button
              key={dir}
              onClick={() => setFilter(dir)}
              className={`px-3 py-1 rounded text-sm ${
                filter === dir
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 text-gray-700 hover:bg-gray-300"
              }`}
            >
              {dir === "" ? "全部" : dir === "long" ? "做多" : dir === "short" ? "做空" : "中性"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-center py-10">加载中...</p>
      ) : signals.length === 0 ? (
        <p className="text-center py-10 text-gray-500">暂无信号数据</p>
      ) : (
        <div className="grid gap-4">
          {signals.map((item) => (
            <SignalCard
              key={item.id}
              authorHandle={item.author_handle}
              content={item.content}
              signal={item.signal}
              createdAt={item.created_at}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify frontend renders**

```bash
cd finance-tweet-analyzer/frontend
npm run dev
```

Open `http://localhost:3000/signals` — should show empty state or signals if seeded.

- [ ] **Step 4: Commit**

```bash
git add finance-tweet-analyzer/frontend/src/
git commit -m "feat: implement Signals list page with filtering"
```

---

### Task 11: End-to-End Integration Test

**Files:**
- No new files — this task verifies the full pipeline works.

- [ ] **Step 1: Ensure PostgreSQL is running with the database created**

```bash
psql -U postgres -c "CREATE DATABASE finance_tweets;" 2>/dev/null || echo "DB already exists"
```

- [ ] **Step 2: Run migrations**

```bash
cd finance-tweet-analyzer
uv run alembic upgrade head
```

- [ ] **Step 3: Start the backend**

```bash
cd finance-tweet-analyzer
uv run uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 4: Seed data and trigger analysis**

```bash
cd finance-tweet-analyzer
uv run python scripts/seed_tweets.py
```

Expected output:
```
Import result: {'imported': 8, 'skipped': 0, 'errors': []}
Analysis result: {'batch_id': '...', 'analyzed': 8}
```

- [ ] **Step 5: Verify API responses**

```bash
curl http://localhost:8000/api/dashboard/overview | python -m json.tool
curl http://localhost:8000/api/signals | python -m json.tool
```

Expected: Dashboard shows 8 tweets analyzed, signals list shows extracted signals.

- [ ] **Step 6: Start frontend and verify UI**

```bash
cd finance-tweet-analyzer/frontend
npm run dev
```

Open `http://localhost:3000`:
- Dashboard: shows stats (8 total tweets, 0 pending, 8 analyzed, N signals)
- Signals page: shows signal cards with ticker, direction, prices, reasoning

- [ ] **Step 7: Commit any fixes from integration testing**

```bash
git add -A finance-tweet-analyzer/
git commit -m "fix: integration test fixes"
```

---

## Summary

| Task | Description | Key Deliverable |
|------|-------------|-----------------|
| 1 | Project scaffolding | pyproject.toml, config, deps |
| 2 | Database models | SQLAlchemy models + Alembic migration |
| 3 | Tweet import API | POST /api/tweets/import with dedup |
| 4 | Signal Agent | LLM structured output extraction |
| 5 | Supervisor graph | LangGraph StateGraph + analysis trigger |
| 6 | Signals + Dashboard API | GET endpoints for frontend |
| 7 | Seed script | Sample data for development |
| 8 | Frontend setup | Next.js + Tailwind + API helpers |
| 9 | Dashboard page | Stats overview + recent signals |
| 10 | Signals page | Filterable signal card list |
| 11 | Integration test | Full pipeline verification |
