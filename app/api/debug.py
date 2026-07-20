"""
调试端点
============================================================
职责：暴露完整的 RAG 检索管线，供开发/测试阶段调试使用。

仅在 settings.debug_mode=True 时可用，否则返回 404。
返回每个阶段的原始结果 + 各阶段耗时，帮助定位性能瓶颈与召回质量问题。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/api/debug", tags=["debug"])


class DebugRetrieveRequest(BaseModel):
    query: str
    ticker: str | None = None
    blogger_filter: list[str] | None = None


@router.post("/retrieve")
async def debug_retrieve(
    request: DebugRetrieveRequest,
    current_user: User = Depends(get_current_user),
):
    if not settings.debug_mode:
        raise HTTPException(status_code=404, detail="Debug mode is not enabled")
    if not settings.feature_rag_enabled:
        raise HTTPException(status_code=404, detail="RAG feature is not enabled")

    # Lazy imports to avoid circular dependencies (same pattern as other endpoints)
    from app.agents.self_query_agent import parse_intent, QueryIntent
    from app.rag.retrievers.document_retriever import retrieve_documents
    from app.rag.retrievers.tweet_retriever import retrieve_tweets
    from app.rag.retrievers.analysis_retriever import retrieve_analyses
    from app.rag.retrievers.structured_retriever import retrieve_structured
    from app.rag.retrievers.bm25_retriever import retrieve_bm25
    from app.rag.fusion import reciprocal_rank_fusion
    from app.rag.reranker import rerank, apply_time_decay

    latency_ms: dict[str, float] = {}

    # 1. Parse intent
    t0 = time.perf_counter()
    intent = parse_intent(request.query)
    latency_ms["intent"] = round((time.perf_counter() - t0) * 1000, 1)

    # Override ticker if explicitly provided in request
    if request.ticker:
        intent = intent.model_copy(update={"ticker": request.ticker})
    if request.blogger_filter:
        intent = intent.model_copy(update={"blogger_filter": request.blogger_filter})

    intent_dict = intent.model_dump()

    # 2. Retrieve from 4 paths (adapting to each retriever's actual signature)
    paths: dict[str, list[dict]] = {}

    # document_retriever: takes (intent: QueryIntent, user_id: UUID)
    t0 = time.perf_counter()
    try:
        paths["documents"] = retrieve_documents(intent, user_id=current_user.id)
    except Exception as e:
        paths["documents"] = [{"unique_id": "error", "content": str(e), "source_type": "error", "metadata": {}, "score": 0}]
    latency_ms["documents"] = round((time.perf_counter() - t0) * 1000, 1)

    # tweet_retriever: takes (intent: QueryIntent)
    t0 = time.perf_counter()
    try:
        paths["tweets"] = retrieve_tweets(intent)
    except Exception as e:
        paths["tweets"] = [{"unique_id": "error", "content": str(e), "source_type": "error", "metadata": {}, "score": 0}]
    latency_ms["tweets"] = round((time.perf_counter() - t0) * 1000, 1)

    # analysis_retriever: takes (intent: QueryIntent)
    t0 = time.perf_counter()
    try:
        paths["analyses"] = retrieve_analyses(intent)
    except Exception as e:
        paths["analyses"] = [{"unique_id": "error", "content": str(e), "source_type": "error", "metadata": {}, "score": 0}]
    latency_ms["analyses"] = round((time.perf_counter() - t0) * 1000, 1)

    # structured_retriever: takes (intent: QueryIntent)
    t0 = time.perf_counter()
    try:
        paths["structured"] = retrieve_structured(intent)
    except Exception as e:
        paths["structured"] = [{"unique_id": "error", "content": str(e), "source_type": "error", "metadata": {}, "score": 0}]
    latency_ms["structured"] = round((time.perf_counter() - t0) * 1000, 1)

    # bm25_retriever: takes (intent: QueryIntent)
    t0 = time.perf_counter()
    try:
        paths["bm25"] = retrieve_bm25(intent, user_id=current_user.id)
    except Exception as e:
        paths["bm25"] = [{"unique_id": "error", "content": str(e), "source_type": "error", "metadata": {}, "score": 0}]
    latency_ms["bm25"] = round((time.perf_counter() - t0) * 1000, 1)

    # 3. RRF Fusion
    t0 = time.perf_counter()
    all_results = [paths["documents"], paths["tweets"], paths["analyses"], paths["structured"], paths["bm25"]]
    fused = reciprocal_rank_fusion(all_results, k=settings.rag_rrf_k, top_n=30)
    latency_ms["fusion"] = round((time.perf_counter() - t0) * 1000, 1)

    # 4. Rerank
    t0 = time.perf_counter()
    try:
        reranked_indices = rerank(
            query=request.query,
            documents=[item["content"] for item in fused],
            top_n=settings.reranker_top_n,
        )
        reranked = [fused[idx] for idx, _score in reranked_indices]
    except Exception:
        reranked = fused[: settings.reranker_top_n]
    reranked = apply_time_decay(reranked)
    latency_ms["rerank"] = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "intent": intent_dict,
        "paths": paths,
        "fused": fused,
        "reranked": reranked,
        "latency_ms": latency_ms,
    }
