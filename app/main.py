from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

import app.core.logging  # noqa: F401 — configure loguru on import
import app.core.tracing  # noqa: F401 — configure LangSmith before LangChain imports
import app.celery_app  # noqa: F401 — bind shared_task to configured Redis broker
from app.api.router import api_router
from app.core.access_log import AccessLogMiddleware
from app.memory.checkpointer import setup_checkpointer, teardown_checkpointer
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_checkpointer()
    start_scheduler()
    yield
    stop_scheduler()
    teardown_checkpointer()


app = FastAPI(title="Finance Tweet Analyzer", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)


app.include_router(api_router)

logger.info("Finance Tweet Analyzer started")
