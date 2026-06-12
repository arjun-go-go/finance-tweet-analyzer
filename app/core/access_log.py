"""HTTP access-log middleware with request/response body capture and PII scrubbing.

Each request gets a request_id (X-Request-ID echoed back) propagated via
contextvars so every log line emitted during request handling carries it.

Production safeguards:
- Skip noisy paths (health/docs) via settings.log_skip_paths
- Truncate bodies to settings.log_body_max_bytes
- Strip sensitive fields (password/token/api_key/...) from JSON bodies and headers
- Skip body capture for streaming responses (text/event-stream) and large uploads
- 4xx/5xx logs at WARNING/ERROR; 2xx/3xx at INFO
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import request_id_var, user_id_var

_SENSITIVE = {k.lower() for k in settings.log_sensitive_keys}
_REDACTED = "***"
_SKIP_PATHS = set(settings.log_skip_paths)
_NON_BODY_METHODS = {"GET", "HEAD", "DELETE", "OPTIONS"}


def _scrub(value: Any) -> Any:
    """Recursively redact sensitive keys in dicts/lists; leave primitives alone."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _SENSITIVE else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _scrub_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        k: (_REDACTED if k.lower() in _SENSITIVE else v)
        for k, v in headers.items()
    }


def _decode_body(raw: bytes, max_bytes: int) -> Any:
    if not raw:
        return None
    truncated = len(raw) > max_bytes
    blob = raw[:max_bytes]
    try:
        text = blob.decode("utf-8", errors="replace")
    except Exception:
        return f"<{len(raw)} bytes binary>"
    try:
        parsed = json.loads(text)
        scrubbed = _scrub(parsed)
        return {"_truncated": True, "body": scrubbed} if truncated else scrubbed
    except Exception:
        return text + ("...<truncated>" if truncated else "")


def _format_extras_for_text(req: Any, resp: Any) -> str:
    """Render req/resp body inline for human-readable text logs.

    Returns empty string in JSON mode (the bind() extras are already structured).
    """
    if settings.log_json:
        return ""
    parts: list[str] = []
    if req is not None:
        try:
            parts.append("req=" + json.dumps(req, ensure_ascii=False, default=str))
        except Exception:
            parts.append(f"req={req!r}")
    if resp is not None:
        try:
            parts.append("resp=" + json.dumps(resp, ensure_ascii=False, default=str))
        except Exception:
            parts.append(f"resp={resp!r}")
    return ("  " + "  ".join(parts)) if parts else ""


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Production-grade HTTP access logger."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _SKIP_PATHS:
            return await call_next(request)

        # Establish request_id (honor incoming header for cross-service tracing).
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        rid_token = request_id_var.set(rid)
        uid_token = user_id_var.set("-")

        method = request.method
        client_ip = request.client.host if request.client else "-"
        query = str(request.url.query) if request.url.query else ""

        # Capture request body for logging. BaseHTTPMiddleware wraps the
        # request in a _CachedRequest which transparently caches the body
        # after request.body() is awaited and replays it via its own
        # wrapped_receive — we just consume here and read request._body later.
        req_body_repr: Any = None
        if (
            settings.log_request_body
            and method not in _NON_BODY_METHODS
        ):
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                req_body_repr = f"<multipart upload, {request.headers.get('content-length', '?')} bytes>"
            else:
                raw = await request.body()
                req_body_repr = _decode_body(raw, settings.log_body_max_bytes)

        # Headers (scrubbed).
        headers = _scrub_headers({k: v for k, v in request.headers.items()})

        start = time.perf_counter()
        status = 500
        resp_body_repr: Any = None
        response: Response
        try:
            response = await call_next(request)
            status = response.status_code

            # Capture response body for errors or when explicitly enabled,
            # but never for streaming (SSE / file download).
            ct = response.headers.get("content-type", "")
            is_stream = "text/event-stream" in ct or "application/octet-stream" in ct
            should_capture = (
                settings.log_response_body
                and not is_stream
                and (status >= 400 or "application/json" in ct)
            )
            if should_capture:
                chunks: list[bytes] = []
                async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                    chunks.append(chunk)
                raw = b"".join(chunks)
                resp_body_repr = _decode_body(raw, settings.log_body_max_bytes)
                response = Response(
                    content=raw,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            extra_text = _format_extras_for_text(req_body_repr, None)
            logger.bind(
                request_id=rid,
                method=method,
                path=path,
                query=query,
                client_ip=client_ip,
                headers=headers,
                req_body=req_body_repr,
                duration_ms=round(elapsed, 1),
            ).exception(f"HTTP 500 {method} {path} unhandled: {exc}{extra_text}")
            request_id_var.reset(rid_token)
            user_id_var.reset(uid_token)
            raise
        finally:
            pass

        elapsed = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = rid

        # BaseHTTPMiddleware runs route in a separate task, so ContextVar.set()
        # in auth dependency doesn't propagate back. Read from request.state instead.
        uid = getattr(request.state, "uid", None) or user_id_var.get()

        log_ctx = logger.bind(
            request_id=rid,
            user_id=uid,
            method=method,
            path=path,
            query=query,
            status=status,
            client_ip=client_ip,
            duration_ms=round(elapsed, 1),
            headers=headers,
            req_body=req_body_repr,
            resp_body=resp_body_repr,
        )
        extra_text = _format_extras_for_text(req_body_repr, resp_body_repr)
        msg = f"{method} {path} -> {status} ({elapsed:.1f}ms){extra_text}"
        if status >= 500:
            log_ctx.error(msg)
        elif status >= 400:
            log_ctx.warning(msg)
        else:
            log_ctx.info(msg)

        request_id_var.reset(rid_token)
        user_id_var.reset(uid_token)
        return response
