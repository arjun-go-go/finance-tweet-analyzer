from fastapi import APIRouter
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.tweets import router as tweets_router
from app.api.analysis import router as analysis_router
from app.api.signals import router as signals_router
from app.api.dashboard import router as dashboard_router
from app.api.bloggers import router as bloggers_router
from app.api.predictions import router as predictions_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.tracking import router as tracking_router
from app.api.reports import router as reports_router
from app.api.me import router as me_router
from app.api.admin_traces import router as admin_traces_router
from app.core.config import settings


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(tweets_router)
    router.include_router(analysis_router)
    router.include_router(signals_router)
    router.include_router(dashboard_router)
    router.include_router(bloggers_router)
    router.include_router(predictions_router)
    router.include_router(chat_router)
    router.include_router(documents_router)
    router.include_router(tracking_router)
    router.include_router(reports_router)
    router.include_router(me_router)
    router.include_router(admin_traces_router)
    if settings.debug_mode:
        from app.api.debug import router as debug_router

        router.include_router(debug_router)
    return router


api_router = build_api_router()


@api_router.get("/api/health")
def health_check():
    from app.core.resilience import get_circuit_status
    from loguru import logger

    checks = {}

    # Database connectivity
    try:
        from app.core.deps import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        logger.warning("[Health] database check failed: {}", e)
        checks["database"] = f"error: {e}"

    # Redis connectivity
    try:
        from app.scheduler.locks import _get_redis
        _get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.warning("[Health] redis check failed: {}", e)
        checks["redis"] = f"error: {e}"

    # Vector store connectivity
    try:
        from app.rag.vector_store import get_vector_store
        vs = get_vector_store()
        vs.count("user_documents")
        vs.count("public_signals")
        checks["vector_store"] = "ok"
    except Exception as e:
        logger.warning("[Health] vector store check failed: {}", e)
        checks["vector_store"] = f"error: {e}"

    # Optional Elasticsearch keyword read model connectivity
    if settings.rag_keyword_backend.lower().strip() == "elasticsearch" or settings.elasticsearch_url:
        try:
            from app.rag.keyword_store import get_keyword_store
            if get_keyword_store().health_check():
                checks["elasticsearch"] = "ok"
            else:
                checks["elasticsearch"] = "error: ping returned false"
        except Exception as e:
            logger.warning("[Health] elasticsearch check failed: {}", e)
            checks["elasticsearch"] = f"error: {e}"

    hard_checks = ["database", "redis", "vector_store"]
    overall = "ok" if all(checks.get(name) == "ok" for name in hard_checks) else "degraded"
    return {"status": overall, "checks": checks, "circuits": get_circuit_status()}
