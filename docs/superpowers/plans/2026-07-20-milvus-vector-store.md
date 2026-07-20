# Milvus Vector Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Milvus/Zilliz vector store backend and switch new vector writes to Milvus when `VECTOR_BACKEND=milvus`.

**Architecture:** Keep the existing `VectorStoreClient` protocol and add a `MilvusVectorStore` adapter behind the existing factory. Preserve the two logical collections, `user_documents` and `public_signals`, by mapping them to physical Milvus collection names with a configurable prefix.

**Tech Stack:** FastAPI, Pydantic Settings, pymilvus `MilvusClient`, DashScope embeddings, pytest.

---

### Task 1: Configuration

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] Add Milvus settings: URI, token, database name, collection prefix, timeout.
- [ ] Redact Milvus token in config repr.
- [ ] Document `.env.example` values without real secrets.

### Task 2: Milvus Adapter

**Files:**
- Modify: `app/rag/vector_store.py`

- [ ] Implement `MilvusVectorStore`.
- [ ] Create collections on first use with 1024-dim COSINE vector.
- [ ] Store `id`, `vector`, `content`, JSON metadata, and common scalar fields.
- [ ] Convert existing dict filters to Milvus expressions.
- [ ] Wire `get_vector_store()` to return Milvus adapter when `VECTOR_BACKEND=milvus`.

### Task 3: Health and Tests

**Files:**
- Modify: `app/api/router.py`
- Modify: `tests/unit/rag/test_vector_store_factory.py`

- [ ] Rename vector health check key from `chromadb` to `vector_store`.
- [ ] Update factory tests for Milvus.
- [ ] Add unit tests for collection mapping and filter conversion.
- [ ] Run targeted tests.

### Task 4: Server Deployment

**Files:**
- Server `.env` only, not committed.

- [ ] Update server `.env` with `VECTOR_BACKEND=milvus` and Milvus credentials.
- [ ] Sync code to server.
- [ ] Restart backend/Celery/frontend with `scripts/manage.sh restart`.
- [ ] Verify `/api/health`.
