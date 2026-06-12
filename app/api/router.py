from fastapi import APIRouter

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
from app.api.debug import router as debug_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(tweets_router)
api_router.include_router(analysis_router)
api_router.include_router(signals_router)
api_router.include_router(dashboard_router)
api_router.include_router(bloggers_router)
api_router.include_router(predictions_router)
api_router.include_router(chat_router)
api_router.include_router(documents_router)
api_router.include_router(tracking_router)
api_router.include_router(reports_router)
api_router.include_router(debug_router)


@api_router.get("/api/health")
def health_check():
    from app.core.resilience import get_circuit_status
    return {"status": "ok", "circuits": get_circuit_status()}
