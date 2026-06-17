# Plan 1 — RAG Infrastructure & Document Ingestion

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-06-05-rag-document-tracking-design.md`

**Goal:** Stand up the RAG foundation for finance-tweet-analyzer — DB schema for documents, embedding/rerank/vector-store abstractions, file & URL parsers, chunking strategies, repository layer with forced `user_id` isolation, document REST API (upload / paste / url / list / get / delete / status), and Celery `ingest_document_task`. After this plan executes, an authenticated user can ingest a document and have its chunks searchable in the `user_documents` Chroma collection.

**Out of scope (deferred to later plans):** signal-library async embedding hooks, Self-Query, multi-retrieve, RRF, Rerank, Report Agent, tracking subscriptions, Beat schedules beyond ingest, frontend pages, Milvus adapter.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, Celery 5.6, Chroma (`chromadb` + `langchain-chroma`), DashScope (`dashscope`), `pypdf`, `python-docx`, `trafilatura`, pytest, httpx.

---

## File Structure

```
finance-tweet-analyzer/
├── app/
│   ├── core/
│   │   └── config.py                              # Modified: RAG + quota + DashScope settings + feature flag
│   ├── models/
│   │   ├── __init__.py                            # Modified: register Document, DocChunk
│   │   ├── document.py                            # New
│   │   └── doc_chunk.py                           # New
│   ├── schemas/
│   │   └── document.py                            # New
│   ├── rag/
│   │   ├── __init__.py                            # New
│   │   ├── embeddings.py                          # New: DashScope embedder + content-hash cache
│   │   ├── vector_store.py                        # New: factory + Chroma adapter (LangChain VectorStore)
│   │   ├── chunking.py                            # New: document/tweet/analysis chunker
│   │   ├── repository.py                          # New: UserDocumentRepository (forced user_id filter)
│   │   ├── storage.py                             # New: DocumentStorage (local disk)
│   │   └── parsers/
│   │       ├── __init__.py                        # New
│   │       ├── pdf_parser.py                      # New
│   │       ├── docx_parser.py                     # New
│   │       ├── markdown_parser.py                 # New
│   │       ├── url_parser.py                      # New (trafilatura + SSRF guard)
│   │       └── paste_parser.py                    # New
│   ├── services/
│   │   └── document_service.py                    # New: quota check, dedupe, status orchestration
│   ├── api/
│   │   ├── documents.py                           # New: 7 endpoints
│   │   └── router.py                              # Modified: include documents_router
│   ├── scheduler/
│   │   └── tasks.py                               # Modified: add ingest_document_task
│   └── celery_app.py                              # Modified: route "ingest" queue
├── alembic/versions/
│   └── 0008_documents.py                          # New migration (documents + doc_chunks)
├── tests/
│   ├── unit/rag/
│   │   ├── test_chunking.py                       # New
│   │   ├── test_repository.py                     # New (security: forced filter)
│   │   ├── test_embeddings_cache.py               # New
│   │   ├── test_vector_store_factory.py           # New
│   │   ├── test_url_parser_ssrf.py                # New
│   │   └── test_pdf_parser.py                     # New
│   ├── unit/services/
│   │   └── test_document_service.py               # New (quota + dedupe)
│   └── integration/
│       └── test_documents_api.py                  # New (upload→celery sync→search)
├── pyproject.toml                                 # Modified: add chromadb, langchain-chroma, dashscope, pypdf, python-docx, trafilatura, tiktoken
└── .env.example                                   # Modified: DashScope key + chroma path placeholders
```

---

## Conventions used in this plan

- All new tables follow the SQLAlchemy 2.0 `Mapped[]` pattern (mirror `app/models/conversation.py`).
- All new code lives under typed modules; no broad `from x import *`.
- Every Celery task uses `bind=True`, `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=3`, plus `acks_late=True`.
- DashScope and Chroma calls go through `@resilient_tool` (existing decorator in `app.core.resilience`) wherever they reach the network.
- Tests use the existing PG `conftest.py` (`postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets_test`) and a per-test temp dir for Chroma.
- `traced_node` from `app.services.trace_service` wraps each Celery ingest stage so traces show up in `agent_traces` and LangSmith.

---

### Task 1: Configuration & Dependencies

**Files:**
- Modify: `pyproject.toml` (repo root, monorepo-shared)
- Modify: `finance-tweet-analyzer/app/core/config.py`
- Create: `finance-tweet-analyzer/.env.example`

- [ ] **Step 1: Add Python dependencies**

Most RAG deps already exist at the root `pyproject.toml`: `chromadb>=1.0.0`, `langchain-chroma>=1.1.0`, `dashscope>=1.20.0`, `pypdf>=6.10.2`, `python-docx>=1.2.0`, `pymilvus>=2.6.0`, `langchain-text-splitters>=1.1.2`. Append only the missing ones to `[project.dependencies]`:

```toml
"trafilatura>=1.12.0",
"tiktoken>=0.7.0",
```

Run `uv sync` (verification only — no commit).

- [ ] **Step 2: Extend `Settings` with RAG block**

In `app/core/config.py` add (preserving existing fields):

```python
# ----- RAG / Vector store -----
vector_backend: str = "chroma"               # 'chroma' | 'milvus'
chroma_persist_dir: str = "./chroma_db"

# ----- Embedding -----
embedding_provider: str = "dashscope"
dashscope_api_key: str = ""
embedding_model: str = "text-embedding-v3"
embedding_dim: int = 1024
embedding_batch_size: int = 32
embedding_timeout_sec: float = 30.0

# ----- Chunking -----
chunk_size_document: int = 800
chunk_overlap_document: int = 100
chunk_size_analysis: int = 500
chunk_size_tweet: int = 0                    # 0 == do not split

# ----- Document quotas -----
max_documents_per_user: int = 200
max_document_size_mb: int = 20
max_total_size_mb_per_user: int = 500
allowed_file_extensions: list[str] = [".pdf", ".docx", ".md", ".txt"]

# ----- URL parsing -----
url_fetch_timeout_sec: int = 15
url_blocked_hosts: list[str] = [
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "169.254.169.254",  # cloud metadata
]

# ----- Storage -----
document_storage_root: str = "./uploads"

# ----- Feature flag -----
feature_rag_enabled: bool = False
```

- [ ] **Step 3: Create `.env.example`**

The repo currently only has the real `.env` (with secrets) under `finance-tweet-analyzer/`. Create a new `finance-tweet-analyzer/.env.example` that mirrors all keys from `.env` but with placeholder values, and append the new RAG block:

```
# RAG / Vector store
VECTOR_BACKEND=chroma
CHROMA_PERSIST_DIR=./chroma_db

# DashScope (embedding + rerank)
DASHSCOPE_API_KEY=your-dashscope-key

# Storage
DOCUMENT_STORAGE_ROOT=./uploads

# Feature flag
FEATURE_RAG_ENABLED=false
```

Do **not** put real keys.

---

### Task 2: ORM Models — Document & DocChunk

**Files:**
- Create: `finance-tweet-analyzer/app/models/document.py`
- Create: `finance-tweet-analyzer/app/models/doc_chunk.py`
- Modify: `finance-tweet-analyzer/app/models/__init__.py`

- [ ] **Step 1: Create `Document` model** (mirrors `Conversation` style)

```python
import uuid
from datetime import date, datetime

from sqlalchemy import CHAR, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    chunk_count: Mapped[int] = mapped_column(Integer, server_default="0")
    file_size_bytes: Mapped[int] = mapped_column(Integer, server_default="0")
    tickers: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    publish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_documents_user_status", "user_id", "status"),
        UniqueConstraint("user_id", "content_hash", name="uq_documents_user_hash"),
    )
```

- [ ] **Step 2: Create `DocChunk` model**

```python
import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_doc_chunks_document", "document_id"),
        Index("ix_doc_chunks_hash", "content_hash"),
    )
```

- [ ] **Step 3: Register in `models/__init__.py`**

Add `from app.models.document import Document` and `from app.models.doc_chunk import DocChunk`, plus their entries in `__all__`.

---

### Task 3: Alembic Migration `0008_documents`

**Files:**
- Create: `finance-tweet-analyzer/alembic/versions/0008_documents.py`

- [ ] **Step 1: Generate migration skeleton**

Use `0007_agent_traces.py` as a template. Set:

```python
revision: str = "0008_documents"
down_revision: str | None = "0007_agent_traces"
```

- [ ] **Step 2: Implement `upgrade()`**

Create both tables with the columns from Task 2 plus indexes:

```python
op.create_table(
    "documents",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("users.id"), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("source_type", sa.String(20), nullable=False),
    sa.Column("source_uri", sa.Text, nullable=True),
    sa.Column("content_hash", sa.CHAR(64), nullable=False),
    sa.Column("char_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("chunk_count", sa.Integer, server_default="0"),
    sa.Column("file_size_bytes", sa.Integer, server_default="0"),
    sa.Column("tickers", postgresql.JSONB, server_default="[]", nullable=False),
    sa.Column("publish_date", sa.Date, nullable=True),
    sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    sa.Column("error_detail", sa.Text, nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)
op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])
op.create_unique_constraint("uq_documents_user_hash", "documents", ["user_id", "content_hash"])
op.create_index("ix_documents_tickers", "documents", ["tickers"], postgresql_using="gin")
```

(Identical pattern for `doc_chunks` with `ondelete="CASCADE"` on its FK and the two indexes.)

- [ ] **Step 3: Implement `downgrade()`** dropping both tables in reverse order, dropping indexes first.

- [ ] **Step 4: Smoke-test**

```
cd finance-tweet-analyzer
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

---

### Task 4: Pydantic Schemas

**Files:**
- Create: `finance-tweet-analyzer/app/schemas/document.py`

- [ ] **Step 1: Define request/response models**

```python
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class DocumentPasteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=2_000_000)
    tickers: list[str] = Field(default_factory=list, max_length=20)
    publish_date: date | None = None


class DocumentUrlRequest(BaseModel):
    url: HttpUrl
    title: str | None = Field(default=None, max_length=500)
    tickers: list[str] = Field(default_factory=list, max_length=20)


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    source_type: str
    status: str
    char_count: int
    chunk_count: int
    tickers: list[str]
    publish_date: date | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: str
    chunk_count: int
    error_detail: str | None
```

---

### Task 5: Document Storage Abstraction

**Files:**
- Create: `finance-tweet-analyzer/app/rag/storage.py`

- [ ] **Step 1: Implement local-disk `DocumentStorage`**

```python
from pathlib import Path
from uuid import UUID


class DocumentStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: UUID, document_id: UUID, ext: str) -> Path:
        d = self.root / str(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{document_id}{ext}"

    def save(self, user_id: UUID, document_id: UUID, content: bytes, ext: str) -> str:
        p = self._path(user_id, document_id, ext)
        p.write_bytes(content)
        return str(p)

    def load(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def delete(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)
```

The interface is intentionally minimal so a future S3/MinIO adapter can be swapped in.

---

### Task 6: Parsers

**Files:**
- Create: `finance-tweet-analyzer/app/rag/parsers/__init__.py`
- Create: `finance-tweet-analyzer/app/rag/parsers/{pdf,docx,markdown,url,paste}_parser.py`

Each parser exposes a single function returning a `ParsedDocument` dataclass:

```python
@dataclass
class ParsedDocument:
    text: str
    metadata: dict       # may include {"title": str, "publish_date": date|None, "source_uri": str}
```

- [ ] **Step 1: PDF parser** — `pypdf.PdfReader` over bytes, page join with `\n`, strip control chars. Empty text raises `ParserError("PDF appears empty or scanned")`.

- [ ] **Step 2: DOCX parser** — `docx.Document(io.BytesIO(...))`, concatenate paragraph + table cell text.

- [ ] **Step 3: Markdown / TXT parser** — UTF-8 decode bytes; strip BOM; pass through.

- [ ] **Step 4: URL parser with SSRF guard**

```python
def fetch_url(url: str, blocked_hosts: list[str], timeout: int) -> ParsedDocument:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ParserError("Only http/https URLs are allowed")
    host = parsed.hostname or ""
    if host.lower() in blocked_hosts or _is_private_ip(host):
        raise ParserError(f"Host {host} is blocked (SSRF guard)")
    raw = requests.get(url, timeout=timeout, allow_redirects=True)
    raw.raise_for_status()
    text = trafilatura.extract(raw.text, include_comments=False) or ""
    if not text.strip():
        raise ParserError("URL extraction returned empty content")
    return ParsedDocument(text=text, metadata={"source_uri": url, ...})
```

`_is_private_ip(host)` resolves the host with `socket.gethostbyname` and checks against `ipaddress.ip_address(...).is_private | is_loopback | is_link_local | is_reserved`.

- [ ] **Step 5: Paste parser** — trivial passthrough; only normalises line endings and drops NUL bytes.

- [ ] **Step 6: All parsers raise a shared `ParserError`** that the service layer maps to HTTP 422.

---

### Task 7: Chunking

**Files:**
- Create: `finance-tweet-analyzer/app/rag/chunking.py`

- [ ] **Step 1: Implement a small recursive char splitter**

```python
def _split_with_separators(text: str, separators: list[str]) -> list[str]:
    if not text:
        return []
    if not separators:
        return [text]
    sep, rest = separators[0], separators[1:]
    if sep == "":
        return list(text)
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        idx = text.find(sep, cursor)
        if idx == -1:
            parts.append(text[cursor:])
            break
        if idx > cursor:
            parts.append(text[cursor:idx])
        parts.append(sep)
        cursor = idx + len(sep)
    return parts


def chunk_document(
    text: str, *, chunk_size: int, chunk_overlap: int
) -> list[str]:
    separators = ["\n\n", "\n", "。", "！", "？", ". ", " ", ""]
    if not text or not text.strip():
        return []
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: list[str] = []
    buf = ""
    for piece in _split_with_separators(text, separators):
        if len(buf) + len(piece) <= chunk_size:
            buf += piece
            continue
        if buf:
            chunks.append(buf)
            buf = buf[-chunk_overlap:] if chunk_overlap else ""
        if len(piece) > chunk_size:
            for i in range(0, len(piece), chunk_size - chunk_overlap):
                chunks.append(piece[i : i + chunk_size])
            buf = chunks[-1][-chunk_overlap:] if chunk_overlap else ""
        else:
            buf += piece
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if c.strip()]
```

This mirrors `RecursiveCharacterTextSplitter`'s separator priority (paragraph → newline → CJK terminators → period+space → space → char). We own the code so the Windows-only `pyarrow` crash inside `langchain_text_splitters` cannot block ingestion.

- [ ] **Step 2: Tweet/analysis helpers**

```python
def chunk_tweet(text: str) -> list[str]: return [text.strip()] if text.strip() else []
def chunk_analysis(text: str, chunk_size: int) -> list[str]: ...  # uses splitter w/ chunk_size_analysis, no overlap
```

- [ ] **Step 3: Char-count helper** for the eventual token budget integration; for this plan we emit chunk char counts for `doc_chunks.char_count`.

---

### Task 8: Embedding Client with Cache

**Files:**
- Create: `finance-tweet-analyzer/app/rag/embeddings.py`

- [ ] **Step 1: Define an `Embedder` protocol** matching LangChain's `Embeddings` interface (`embed_documents(list[str]) -> list[list[float]]`, `embed_query(str) -> list[float]`). We use `typing.Protocol` so we are not coupled to `langchain_core.embeddings.Embeddings` (avoids transitive imports of fragile pkgs on Windows).

- [ ] **Step 2: Implement `DashScopeEmbedder`**

```python
class DashScopeEmbedder:
    def __init__(self, api_key: str, model: str, batch_size: int, dim: int, timeout: float):
        ...

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        # Inline retry with exponential backoff (do NOT use resilient_tool — it
        # returns string fallbacks, which is incompatible with embedding output).
        last_exc = None
        for attempt in range(1, settings.tool_max_retries + 1):
            try:
                resp = dashscope.TextEmbedding.call(
                    model=self._model, input=texts,
                    dimension=self._dim, api_key=self._key,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"DashScope embedding failed: {resp.message}")
                return [item["embedding"] for item in resp.output["embeddings"]]
            except Exception as e:
                last_exc = e
                if attempt < settings.tool_max_retries:
                    time.sleep(2 ** (attempt - 1))
        raise RuntimeError(f"DashScope embedding failed after retries: {last_exc}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            out.extend(self._call_api(texts[i : i + self._batch_size]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call_api([text])[0]
```

- [ ] **Step 3: Content-hash dedupe helper**

```python
def embed_with_dedupe(
    texts: list[str], *, embedder: Embedder, session: Session,
) -> tuple[list[list[float] | None], list[str | None], list[str]]:
    """For each text, return (embedding, vector_id, content_hash) tuples.

    - If a previous DocChunk has the same content_hash AND vector_id IS NOT NULL,
      reuse the vector_id (cache hit) — embedding is None and the caller skips
      the vector_store.add() for that index.
    - Otherwise call embedder.embed_documents(...) for the misses only — vector_id
      is None and the caller writes the new embedding to the vector store and
      records the resulting id back into doc_chunks.
    """
    hashes = [sha256(t.encode("utf-8")).hexdigest() for t in texts]
    rows = session.execute(
        select(DocChunk.content_hash, DocChunk.vector_id)
        .where(DocChunk.content_hash.in_(hashes))
        .where(DocChunk.vector_id.is_not(None))
    ).all()
    hash_to_vid: dict[str, str] = {h: vid for h, vid in rows}

    miss_indexes = [i for i, h in enumerate(hashes) if h not in hash_to_vid]
    miss_embeddings = (
        embedder.embed_documents([texts[i] for i in miss_indexes])
        if miss_indexes else []
    )

    embeddings: list[list[float] | None] = [None] * len(texts)
    vector_ids: list[str | None] = [hash_to_vid.get(h) for h in hashes]
    for idx, emb in zip(miss_indexes, miss_embeddings):
        embeddings[idx] = emb
    return embeddings, vector_ids, hashes
```

The dedupe lookup uses `doc_chunks` because every chunk we ever embedded is recorded there; we re-use a previously computed `vector_id` when the same hash reappears (cross-document dedupe). The repository layer in Task 10 calls `embed_with_dedupe`, then writes only the misses to the vector store.

- [ ] **Step 4: Module-level singleton accessor** `get_embedder() -> Embedder` reading `settings`. Wrap with `functools.lru_cache(maxsize=1)`.

---

### Task 9: Vector Store Factory + Chroma Adapter

**Files:**
- Create: `finance-tweet-analyzer/app/rag/vector_store.py`

- [ ] **Step 1: Define an abstract base**

```python
class VectorStoreClient(Protocol):
    def add(self, collection: str, ids: list[str], texts: list[str],
            embeddings: list[list[float]], metadatas: list[dict]) -> None: ...
    def query(self, collection: str, query_embedding: list[float],
              k: int, filter: dict | None) -> list[VectorHit]: ...
    def delete(self, collection: str, ids: list[str]) -> None: ...
    def count(self, collection: str) -> int: ...
```

- [ ] **Step 2: Implement `ChromaVectorStore`** using `chromadb.PersistentClient(path=settings.chroma_persist_dir)`. Two collections are pre-created on first use: `user_documents`, `public_signals`. Distance: cosine.

- [ ] **Step 3: Implement `get_vector_store()` factory**

```python
def get_vector_store() -> VectorStoreClient:
    backend = settings.vector_backend
    if backend == "chroma":
        return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
    if backend == "milvus":
        raise NotImplementedError("Milvus adapter ships in a later plan")
    raise ValueError(f"Unknown vector backend: {backend}")
```

- [ ] **Step 4: Singleton + thread-safety** — wrap with `functools.lru_cache(maxsize=1)` or a module-level lock since chromadb's PersistentClient is process-local.

---

### Task 10: Repository Layer with Forced `user_id` Filter

**Files:**
- Create: `finance-tweet-analyzer/app/rag/repository.py`

- [ ] **Step 1: Implement `UserDocumentRepository`**

```python
class UserDocumentRepository:
    COLLECTION = "user_documents"

    def __init__(self, vs: VectorStoreClient, embedder: Embeddings):
        self._vs = vs
        self._embedder = embedder

    def add_chunks(self, *, user_id: UUID, document_id: UUID, chunks: list[Chunk]) -> list[str]:
        embeddings = self._embedder.embed_documents([c.content for c in chunks])
        ids = [f"{document_id}:{c.chunk_index}" for c in chunks]
        metadatas = [
            {"user_id": str(user_id), "document_id": str(document_id),
             "chunk_index": c.chunk_index, **c.metadata}
            for c in chunks
        ]
        self._vs.add(self.COLLECTION, ids, [c.content for c in chunks], embeddings, metadatas)
        return ids

    def search(self, *, user_id: UUID, query: str, k: int = 15,
               extra_filter: dict | None = None) -> list[VectorHit]:
        if not user_id:
            raise ValueError("user_id is required for user_documents search")
        flt = {"user_id": str(user_id)}
        if extra_filter:
            if "user_id" in extra_filter and extra_filter["user_id"] != str(user_id):
                raise PermissionError("user_id filter override is forbidden")
            flt.update(extra_filter)
        emb = self._embedder.embed_query(query)
        return self._vs.query(self.COLLECTION, emb, k=k, filter=flt)

    def delete_document(self, *, user_id: UUID, document_id: UUID) -> None:
        # narrow delete: query ids by metadata first to enforce ownership
        ...
```

The override-detection check is the **security primitive** the unit tests in Task 14 will exercise.

---

### Task 11: Document Service

**Files:**
- Create: `finance-tweet-analyzer/app/services/document_service.py`

- [ ] **Step 1: Quota & dedupe helpers**

```python
def check_quota(db, user_id: UUID, incoming_size_bytes: int) -> None:
    count = db.scalar(select(func.count()).select_from(Document)
                      .where(Document.user_id == user_id, Document.status != "deleted"))
    if count >= settings.max_documents_per_user:
        raise QuotaExceeded("max_documents_per_user")

    total = db.scalar(select(func.coalesce(func.sum(Document.file_size_bytes), 0))
                      .where(Document.user_id == user_id, Document.status != "deleted"))
    if total + incoming_size_bytes > settings.max_total_size_mb_per_user * 1024 * 1024:
        raise QuotaExceeded("max_total_size_mb_per_user")

    if incoming_size_bytes > settings.max_document_size_mb * 1024 * 1024:
        raise QuotaExceeded("max_document_size_mb")
```

- [ ] **Step 2: `create_document_record`** — runs in a single PG transaction:

  1. compute `content_hash = sha256(text.encode("utf-8"))`
  2. SELECT existing document for `(user_id, content_hash)`; if found and not `status='deleted'`, return it (idempotent).
  3. INSERT new `documents` row with `status='pending'`.
  4. Persist raw bytes via `DocumentStorage` (only for pdf/docx).
  5. Enqueue `ingest_document_task.delay(str(document.id))`.
  6. Return the row.

- [ ] **Step 3: `delete_document`** — sets `status='deleted'`, kicks off vector cleanup synchronously via `UserDocumentRepository.delete_document`. Disk file is unlinked.

- [ ] **Step 4: `get_status` / `list_documents`** — straightforward repository reads with `user_id` filter applied at the SQL layer.

- [ ] **Step 5: Define `QuotaExceeded` and `DuplicateDocument` exceptions** at module top; the API maps them to HTTP 429 / 200 (idempotent return) respectively.

---

### Task 12: Celery `ingest_document_task`

**Files:**
- Modify: `finance-tweet-analyzer/app/scheduler/tasks.py`
- Modify: `finance-tweet-analyzer/app/celery_app.py`

- [ ] **Step 1: Add the task** (in `tasks.py`)

```python
@shared_task(
    bind=True,
    name="app.scheduler.tasks.ingest_document_task",
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
@traced_node(node_name="ingest_document")
def ingest_document_task(self, document_id: str) -> dict:
    db = SessionLocal()
    try:
        doc = db.get(Document, UUID(document_id))
        if not doc or doc.status == "deleted":
            return {"skipped": True}

        doc.status = "processing"
        db.commit()

        text = _resolve_text(doc)              # parse from disk OR re-fetch URL OR use stored text
        chunks = chunk_document(
            text,
            chunk_size=settings.chunk_size_document,
            chunk_overlap=settings.chunk_overlap_document,
        )

        rows = [
            DocChunk(
                document_id=doc.id,
                chunk_index=i,
                content=c,
                content_hash=sha256(c.encode("utf-8")).hexdigest(),
                char_count=len(c),
                metadata_={"title": doc.title, "tickers": doc.tickers,
                           "publish_date": doc.publish_date.isoformat() if doc.publish_date else None},
            )
            for i, c in enumerate(chunks)
        ]
        db.add_all(rows)
        db.flush()

        repo = UserDocumentRepository(get_vector_store(), get_embedder())
        vector_ids = repo.add_chunks(
            user_id=doc.user_id, document_id=doc.id,
            chunks=[Chunk(chunk_index=r.chunk_index, content=r.content,
                          metadata=r.metadata_) for r in rows],
        )
        for r, vid in zip(rows, vector_ids):
            r.vector_id = vid

        doc.chunk_count = len(rows)
        doc.status = "indexed"
        db.commit()
        return {"document_id": str(doc.id), "chunks": len(rows)}
    except Exception as e:
        db.rollback()
        doc = db.get(Document, UUID(document_id))
        if doc:
            doc.status = "failed"
            doc.error_detail = str(e)[:1000]
            db.commit()
        raise
    finally:
        db.close()
```

- [ ] **Step 2: Route to `ingest` queue** in `celery_app.py`

Append to `task_routes`:

```python
"app.scheduler.tasks.ingest_document_task": {"queue": "ingest"},
```

- [ ] **Step 3: Verify `app.core.tracing` import is still at the top of `celery_app.py`** (added in the LangSmith fix). The task will inherit those env vars in the worker.

---

### Task 13: Documents API

**Files:**
- Create: `finance-tweet-analyzer/app/api/documents.py`
- Modify: `finance-tweet-analyzer/app/api/router.py`

- [ ] **Step 1: Implement endpoints**

```python
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    tickers: str = Form(default="[]"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not settings.feature_rag_enabled:
        raise HTTPException(404, "RAG not enabled")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_file_extensions:
        raise HTTPException(415, f"Unsupported file extension: {ext}")
    raw = await file.read()
    if len(raw) > settings.max_document_size_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")

    parsed = parse_by_extension(ext, raw)
    try:
        doc = create_document_record(
            db=db, user=user, title=title or parsed.metadata.get("title") or file.filename,
            text=parsed.text, source_type=ext.lstrip("."), source_bytes=raw, ext=ext,
            tickers=json.loads(tickers),
        )
    except QuotaExceeded as e:
        raise HTTPException(429, detail=str(e))
    return doc
```

Mirror endpoints (preserving auth + feature flag + quota mapping):

- `POST /api/documents/paste` → body = `DocumentPasteRequest`
- `POST /api/documents/url` → body = `DocumentUrlRequest`, calls `fetch_url(...)`
- `GET /api/documents` → pagination params `page`, `page_size`, optional `ticker`
- `GET /api/documents/{id}` → 404 if not found OR not owned by `user`
- `DELETE /api/documents/{id}` → soft delete via service
- `GET /api/documents/{id}/status` → `DocumentStatusResponse`

- [ ] **Step 2: Mount the router**

In `app/api/router.py` append `from app.api.documents import router as documents_router` and `api_router.include_router(documents_router)`.

---

### Task 14: Tests

**Files:**
- Create: `finance-tweet-analyzer/tests/unit/rag/test_chunking.py`
- Create: `finance-tweet-analyzer/tests/unit/rag/test_repository.py`
- Create: `finance-tweet-analyzer/tests/unit/rag/test_embeddings_cache.py`
- Create: `finance-tweet-analyzer/tests/unit/rag/test_vector_store_factory.py`
- Create: `finance-tweet-analyzer/tests/unit/rag/test_url_parser_ssrf.py`
- Create: `finance-tweet-analyzer/tests/unit/rag/test_pdf_parser.py`
- Create: `finance-tweet-analyzer/tests/unit/services/test_document_service.py`
- Create: `finance-tweet-analyzer/tests/integration/test_documents_api.py`

- [ ] **Step 1: `test_chunking.py`**
  - chunk size respected for long Chinese paragraph (no split inside word)
  - empty input returns `[]`
  - tweet chunker returns 1-element list
  - separators include Chinese full stop

- [ ] **Step 2: `test_repository.py` (security-critical)**
  - calling `search(user_id=None)` raises `ValueError`
  - calling `search(user_id=A, extra_filter={"user_id": B})` raises `PermissionError`
  - the metadata sent to vector store always contains `user_id` (use a fake `VectorStoreClient` recording calls)
  - `delete_document` only deletes IDs whose metadata `user_id == requested user_id`

- [ ] **Step 3: `test_embeddings_cache.py`**
  - given two identical chunks, the API is called once
  - re-embedding a previously seen content_hash hits cache, asserted via call counter on a stub `Embeddings`

- [ ] **Step 4: `test_vector_store_factory.py`**
  - `vector_backend="chroma"` returns ChromaVectorStore using a tmp_path persist dir
  - `vector_backend="milvus"` raises `NotImplementedError`
  - `vector_backend="bogus"` raises `ValueError`

- [ ] **Step 5: `test_url_parser_ssrf.py`**
  - `localhost`, `127.0.0.1`, `169.254.169.254` rejected
  - `file://` rejected
  - private IP after DNS resolution rejected (mock `socket.gethostbyname`)
  - happy-path returns parsed text (mock `requests.get` + `trafilatura.extract`)

- [ ] **Step 6: `test_pdf_parser.py`**
  - parse a 1-page sample PDF (committed under `tests/fixtures/sample.pdf`)
  - corrupted bytes → `ParserError`
  - empty/scanned PDF → `ParserError`

- [ ] **Step 7: `test_document_service.py`**
  - quota: 200th doc allowed, 201st raises `QuotaExceeded`
  - file size > `max_document_size_mb` raises
  - dedupe: posting same content twice returns the same row, status preserved
  - cross-user duplicate is allowed (different `user_id` partition)

- [ ] **Step 8: `test_documents_api.py` (integration)**
  - bypass auth via fixture overriding `get_current_user`
  - upload sample.pdf → poll `/status` (run task synchronously with `CELERY_TASK_ALWAYS_EAGER=True`) → assert status == `indexed` and chunks > 0
  - search the chroma collection directly and assert `user_id` metadata matches
  - cross-user GET `/documents/{id}` of another user's doc → 404
  - DELETE → vector store count decreases, GET returns 404

- [ ] **Step 9: Pytest config**
  - add `pytest.ini` markers if needed, or fixture `eager_celery` setting `task_always_eager` + `task_eager_propagates`
  - Chroma fixture uses `tmp_path` and patches `settings.chroma_persist_dir`
  - DashScope fixture stubs `_call_api` to a deterministic hash→float vector so tests don't hit the network

---

### Task 15: Manual Verification

**Files:** none

- [ ] **Step 1: Local end-to-end smoke test**

```
cd finance-tweet-analyzer
alembic upgrade head
celery -A app.celery_app worker -Q ingest -l info &
uvicorn app.main:app --reload &

# obtain JWT via existing /auth/login fixture user
curl -X POST http://localhost:8000/api/documents/paste \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Test","content":"TSLA 财报超预期……(>=400 字)","tickers":["TSLA"]}'
# poll /status → 'indexed'
```

- [ ] **Step 2: LangSmith trace check**

Open the LangSmith project and confirm the `ingest_document` span shows for the run.

- [ ] **Step 3: Acceptance criteria**

  - upload/paste/url all succeed for happy paths
  - duplicate paste returns the same `id`
  - `feature_rag_enabled=False` → all endpoints return 404
  - quota over-limit returns 429
  - SSRF test against `http://127.0.0.1:8000/anything` returns 422
  - Chroma persistence dir contains a `chroma.sqlite3` file with non-zero rows

---

## Risk Notes

| Risk | Mitigation in this plan |
|------|-------------------------|
| Embedding API outage stalls ingest | `@resilient_tool` retries + circuit breaker; failed docs land in `failed` state, no silent loss |
| Vector orphans on doc delete | service deletes vectors synchronously; later GC plan handles tombstones |
| Multi-tenant leak via metadata bypass | Repository raises on missing/overridden `user_id`; covered by tests in Task 14 |
| Chroma client not thread-safe across workers | factory caches per-process; Celery workers each open their own |
| Large PDF blowing memory | `max_document_size_mb=20` enforced before parse; pypdf streams pages |
| SSRF via URL ingest | scheme allowlist + host blocklist + private-IP DNS check |

---

## Definition of Done

- All 15 tasks ticked.
- `pytest tests/unit/rag tests/unit/services tests/integration/test_documents_api.py -q` passes (with eager Celery + Chroma tmp dir).
- `alembic upgrade head` applied cleanly, `downgrade -1` works.
- `feature_rag_enabled` toggles all endpoints on/off.
- Manual smoke test (Task 15) shows a paste-ingested document indexed in Chroma and visible via `GET /api/documents/{id}`.
- No lints introduced beyond pre-existing baseline (`ruff check app tests`).

---

## Next Plan Preview

Plan 2 will cover **Signal-Library Async Embedding Hooks** — `embed_signal_task`, post-`tweet.status='analyzed'` hook, post-`prediction_status='done'` hook, backfill script, `public_signals` collection schema enforcement, and the corresponding tests. It depends only on Tasks 1, 8, 9, 10 of this plan.
