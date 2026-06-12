"""Centralized logging configuration using loguru.

Production-grade features:
- Text or JSON output (toggle via settings.log_json / LOG_JSON env var)
- Per-request request_id propagated via contextvars + loguru's bind/extra
- Standard logging libs (uvicorn, sqlalchemy, fastapi) routed through loguru
- File rotation with 7-day retention
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

from loguru import logger

from app.core.config import settings

# ============================================================
# Per-request context (propagates request_id / user_id into logs)
# ============================================================
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


def _patch_record(record):
    """Inject contextvars into every log record's extra."""
    record["extra"].setdefault("request_id", request_id_var.get())
    record["extra"].setdefault("user_id", user_id_var.get())


TEXT_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss,SSS} | {level: <5} | "
    "rid={extra[request_id]} uid={extra[user_id]} | "
    "{name}:{function}:{line} | {message}"
)


def _json_sink(message):
    """Write a single JSON line per record. Used when log_json=True."""
    record = message.record
    payload = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "file": f"{record['file'].name}:{record['line']}",
        "func": record["function"],
        "msg": record["message"],
        "request_id": record["extra"].get("request_id", "-"),
        "user_id": record["extra"].get("user_id", "-"),
    }
    for k, v in record["extra"].items():
        if k in payload:
            continue
        try:
            json.dumps(v, default=str)
            payload[k] = v
        except Exception:
            payload[k] = str(v)
    if record["exception"]:
        payload["exception"] = str(record["exception"])
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


# ============================================================
# Configure loguru
# ============================================================
logger.remove()
logger.configure(patcher=_patch_record)

if settings.log_json:
    logger.add(_json_sink, level=settings.log_level)
else:
    logger.add(sys.stderr, level=settings.log_level, format=TEXT_FORMAT, enqueue=False)

logger.add(
    "logs/app.log",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
    format=TEXT_FORMAT,
    enqueue=True,
)


# ============================================================
# Route stdlib logging through loguru
# ============================================================
class InterceptHandler(logging.Handler):
    """Route standard logging through loguru so all libs use the same format."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

# Silence overly chatty libs and route everything through our handler.
for name in (
    "uvicorn", "uvicorn.error", "uvicorn.access",
    "fastapi", "sqlalchemy.engine", "celery",
    "httpx", "httpcore", "openai",
):
    lg = logging.getLogger(name)
    lg.handlers = [InterceptHandler()]
    lg.propagate = False

# uvicorn.access is noisy and we already log requests via middleware.
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
