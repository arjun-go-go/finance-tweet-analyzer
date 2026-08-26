"""Shared hybrid retrieval pipeline for the assistant and retrieval debugging."""

from __future__ import annotations

import concurrent.futures
import hashlib
import time
from uuid import UUID

from app.agents.self_query_agent import QueryIntent
from app.core.config import settings
from app.rag.evidence_scope import infer_ticker, matches_target
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranker import apply_time_decay, rerank
from app.rag.retrievers.analysis_retriever import retrieve_analyses
from app.rag.retrievers.bm25_retriever import retrieve_bm25
from app.rag.retrievers.structured_retriever import retrieve_structured
from app.rag.retrievers.tweet_retriever import retrieve_tweets


ALL_PATHS = ("tweets", "analyses", "structured", "bm25")


def build_retrieval_intent(
    query: str,
    *,
    ticker: str = "",
    blogger: str = "",
) -> QueryIntent:
    """Build a fast deterministic intent for interactive retrieval tools."""
    resolved_ticker = (ticker or infer_ticker(query) or "UNKNOWN").upper()
    keywords = [
        part for part in query.split()
        if len(part) > 1 and part.upper() != resolved_ticker
    ]
    return QueryIntent(
        ticker=resolved_ticker,
        keywords=keywords,
        blogger_filter=[blogger.lstrip("@")] if blogger else [],
    )


def paths_for_scope(source_scope: list[str] | None) -> tuple[list[str], set[str] | None]:
    if not source_scope:
        return list(ALL_PATHS), None

    paths: list[str] = []
    allowed_types: set[str] = set()
    for raw_source in source_scope:
        source = raw_source.lower()
        if source == "public_signals":
            requested = ("tweets", "analyses", "structured", "bm25")
            allowed_types.update({"tweet", "analysis", "structured"})
        elif source in {"tweet", "tweets"}:
            requested = ("tweets", "bm25")
            allowed_types.add("tweet")
        elif source in {"analysis", "analyses"}:
            requested = ("analyses", "structured", "bm25")
            allowed_types.update({"analysis", "structured"})
        elif source == "structured":
            requested = ("structured",)
            allowed_types.add("structured")
        elif source in ALL_PATHS:
            requested = (source,)
        else:
            continue
        for path in requested:
            if path not in paths:
                paths.append(path)
    return paths or list(ALL_PATHS), allowed_types or None


def run_retriever_path(
    path: str,
    intent: QueryIntent,
    *,
    user_id: UUID | None = None,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    if path == "tweets":
        return retrieve_tweets(intent, query_embedding=query_embedding)
    if path == "analyses":
        return retrieve_analyses(intent, query_embedding=query_embedding)
    if path == "structured":
        return retrieve_structured(intent)
    if path == "bm25":
        return retrieve_bm25(intent, user_id=user_id)
    raise ValueError(f"Unknown retrieval path: {path}")


def _canonical_item(item: dict) -> dict:
    normalized = {**item, "metadata": dict(item.get("metadata") or {})}
    metadata = normalized["metadata"]
    source_type = str(normalized.get("source_type") or metadata.get("source_type") or "")
    normalized["source_type"] = source_type

    source_id = str(metadata.get("source_id") or "")
    chunk_index = metadata.get("chunk_index")
    old_id = str(normalized.get("unique_id") or "")
    if source_type == "tweet" and source_id:
        normalized["unique_id"] = f"tweet:{source_id}"
    elif source_type == "analysis" and source_id:
        normalized["unique_id"] = f"analysis:{source_id}"
    elif not old_id:
        normalized["unique_id"] = hashlib.sha1(
            f"{source_type}:{normalized.get('content', '')}".encode("utf-8")
        ).hexdigest()
    return normalized


def fuse_results(
    results_per_path: list[list[dict]],
    *,
    ticker: str = "",
    allowed_source_types: set[str] | None = None,
    top_n: int = 30,
) -> list[dict]:
    normalized_paths: list[list[dict]] = []
    for path_results in results_per_path:
        normalized = [_canonical_item(item) for item in path_results]
        if allowed_source_types is not None:
            normalized = [item for item in normalized if item["source_type"] in allowed_source_types]
        if ticker and ticker != "UNKNOWN":
            normalized = [item for item in normalized if matches_target(item, ticker)]
        deduped: list[dict] = []
        seen: set[str] = set()
        for item in normalized:
            unique_id = item["unique_id"]
            if unique_id in seen:
                continue
            seen.add(unique_id)
            deduped.append(item)
        normalized_paths.append(deduped)
    return reciprocal_rank_fusion(normalized_paths, k=settings.rag_rrf_k, top_n=top_n)


def _apply_source_quota(
    ranked_pairs: list[tuple[int, float]],
    fused: list[dict],
    quota_map: dict[str, int],
    total_top_n: int,
) -> list[dict]:
    counts: dict[str, int] = {key: 0 for key in quota_map}
    picked: list[dict] = []
    leftover: list[dict] = []
    for idx, score in ranked_pairs:
        if idx >= len(fused):
            continue
        item = {**fused[idx], "rerank_score": float(score)}
        source_type = item.get("source_type", "unknown")
        if counts.get(source_type, 0) < quota_map.get(source_type, 0):
            picked.append(item)
            counts[source_type] = counts.get(source_type, 0) + 1
        else:
            leftover.append(item)
        if len(picked) >= total_top_n:
            break
    for item in leftover:
        if len(picked) >= total_top_n:
            break
        picked.append(item)
    return picked


def rank_results(
    query: str,
    fused: list[dict],
    *,
    top_n: int | None = None,
    quota_map: dict[str, int] | None = None,
) -> tuple[list[dict], list[tuple[int, float]]]:
    if not fused:
        return [], []
    limit = top_n or settings.reranker_top_n
    ranked_pairs = rerank(query, [item["content"] for item in fused], top_n=len(fused))
    selected = _apply_source_quota(
        ranked_pairs,
        fused,
        quota_map or settings.report_rerank_quota,
        limit,
    )
    selected = apply_time_decay(selected)
    for index, item in enumerate(selected, 1):
        item["global_index"] = index
    return selected, ranked_pairs


def hybrid_retrieve(
    intent: QueryIntent,
    *,
    user_id: UUID | None = None,
    query: str = "",
    source_scope: list[str] | None = None,
    query_embedding: list[float] | None = None,
    include_es_debug: bool = False,
) -> dict:
    paths, allowed_types = paths_for_scope(source_scope)
    latency_ms: dict[str, float] = {}
    errors: dict[str, str] = {}

    if query_embedding is None and any(path in {"tweets", "analyses"} for path in paths):
        t0 = time.perf_counter()
        try:
            from app.rag.embeddings import get_embedder

            query_embedding = get_embedder().embed_query(
                f"{intent.ticker} {' '.join(intent.keywords)}".strip() or query
            )
        except Exception as exc:
            errors["embedding"] = f"{type(exc).__name__}: {exc}"
        latency_ms["embedding"] = round((time.perf_counter() - t0) * 1000, 1)

    path_results: dict[str, list[dict]] = {path: [] for path in paths}

    def _run(path: str) -> tuple[str, list[dict], float, str | None]:
        started = time.perf_counter()
        try:
            results = run_retriever_path(
                path,
                intent,
                user_id=user_id,
                query_embedding=query_embedding,
            )
            error = None
        except Exception as exc:
            results = []
            error = f"{type(exc).__name__}: {exc}"
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return path, results, elapsed, error

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(paths)) as executor:
        futures = [executor.submit(_run, path) for path in paths]
        for future in concurrent.futures.as_completed(futures):
            path, results, elapsed, error = future.result()
            path_results[path] = results
            latency_ms[path] = elapsed
            if error:
                errors[path] = error

    t0 = time.perf_counter()
    ordered_results = [path_results[path] for path in paths]
    fused = fuse_results(
        ordered_results,
        ticker=intent.ticker,
        allowed_source_types=allowed_types,
    )
    latency_ms["fusion"] = round((time.perf_counter() - t0) * 1000, 1)

    rank_query = f"{intent.ticker} {' '.join(intent.keywords)}".strip() or query
    t0 = time.perf_counter()
    reranked, ranked_pairs = rank_results(rank_query, fused)
    latency_ms["rerank"] = round((time.perf_counter() - t0) * 1000, 1)

    es_debug = None
    if include_es_debug:
        t0 = time.perf_counter()
        try:
            from app.rag.keyword_store import get_keyword_store

            es_debug = get_keyword_store().debug_search(
                query_text=rank_query,
                user_id=user_id,
                blogger_filter=intent.blogger_filter,
                time_range_start=intent.time_range_start,
                time_range_end=intent.time_range_end,
                top_k=settings.rag_bm25_top_k,
            )
        except Exception as exc:
            es_debug = {"error": str(exc), "query": None, "raw_hits": [], "results": []}
        latency_ms["es_debug"] = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "paths": path_results,
        "errors": errors,
        "fused": fused,
        "reranked": reranked,
        "rerank_debug": {
            "input_count": len(fused),
            "selected_indices": [
                {"index": index, "score": float(score)} for index, score in ranked_pairs
            ],
        },
        "es_debug": es_debug,
        "latency_ms": latency_ms,
    }


def evidence_from_items(items: list[dict], *, content_limit: int = 1000) -> list[dict]:
    evidence: list[dict] = []
    prefixes = {"analysis": "EA", "tweet": "ET", "structured": "EP"}
    for item in items:
        metadata = item.get("metadata") or {}
        identity = str(item.get("unique_id") or metadata.get("source_id") or item.get("content", ""))
        suffix = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8].upper()
        source_type = str(item.get("source_type") or "")
        evidence.append(
            {
                "evidence_id": f"{prefixes.get(source_type, 'ER')}-{suffix}",
                "source_type": source_type,
                "source_id": str(
                    metadata.get("source_id")
                    or metadata.get("chunk_id")
                    or identity
                ),
                "ticker": metadata.get("ticker") or metadata.get("tickers") or "",
                "author": metadata.get("blogger_handle") or metadata.get("author") or "",
                "published_at": metadata.get("published_at") or metadata.get("created_at"),
                "content": str(item.get("content") or "")[:content_limit],
                "sentiment": metadata.get("sentiment") or "",
                "verification_status": metadata.get("verification_status") or "indexed",
                "relevance_score": round(
                    float(item.get("rerank_score", item.get("score", 0.0)) or 0.0), 4
                ),
                "source_url": metadata.get("source_uri") or metadata.get("url") or "",
            }
        )
    return evidence
