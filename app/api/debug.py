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

    from app.agents.self_query_agent import parse_intent
    from app.rag.hybrid_retrieval import hybrid_retrieve

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

    result = hybrid_retrieve(
        intent,
        user_id=current_user.id,
        query=request.query,
        include_es_debug=True,
    )
    latency_ms.update(result["latency_ms"])

    return {
        "intent": intent.model_dump(),
        "paths": result["paths"],
        "errors": result["errors"],
        "es_debug": result["es_debug"],
        "fused": result["fused"],
        "reranked": result["reranked"],
        "rerank_debug": result["rerank_debug"],
        "latency_ms": latency_ms,
    }
