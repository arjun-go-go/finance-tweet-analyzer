# ES RAG BM25 Design

## Scope

Implement P0 and P1 for Elasticsearch-backed keyword retrieval:

- P0: Replace the RAG BM25 path with Elasticsearch when `RAG_KEYWORD_BACKEND=elasticsearch`.
- P1: Dual-write new document, tweet, and analysis chunks to Elasticsearch.
- Keep PostgreSQL BM25 as fallback and do not remove `doc_chunks.search_vector`.
- Do not create the Elasticsearch index until the index name and mapping are explicitly approved.

The approved index name is `finance_rag_chunks`.

## Architecture

PostgreSQL remains the source of truth. Milvus/Zilliz remains the vector store. Elasticsearch stores a searchable read-model copy of `doc_chunks` for keyword/BM25 retrieval.

`retrieve_bm25()` becomes a backend switch:

- `postgres`: existing `tsvector/ts_rank` query.
- `elasticsearch`: ES BM25 query with fallback to PostgreSQL on error.

New writes continue to commit PG and vector-store changes first. ES writes are best-effort and must not break the main ingestion flow.

## Elasticsearch Mapping

`content` and `title` use IK analyzers:

- index analyzer: `ik_max_word`
- search analyzer: `ik_smart`

Filter fields use `keyword` or `date` types: `user_id`, `visibility`, `source_type`, `ticker`, `tickers`, `blogger_handle`, `published_at`, `created_at`.

## User Isolation

Private document chunks must be searched only with `user_id=current_user.id`.

Public tweet and analysis chunks use `visibility=public` and may be searched globally.

## Operational Rules

- ES query failure falls back to PG BM25.
- ES write failure logs a warning and does not rollback PG/Milvus.
- Index creation is exposed through an explicit script and is not hidden inside app startup or write paths.
- Historical indexing is done by an explicit reindex task after index creation.
