"""Trace service — writes agent execution traces to agent_traces table.

Design:
    - Background thread for non-blocking writes (doesn't slow SSE stream)
    - Output truncation (4KB max) to prevent storage bloat
    - Batch-friendly: collects traces during a request, flushes at end
    - traced_node decorator for LangGraph node instrumentation
"""

import json
import threading
import time
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps

from loguru import logger

from app.core.deps import SessionLocal
from app.models.agent_trace import AgentTrace

OUTPUT_MAX_BYTES = 4096

_current_batch_id: ContextVar[uuid.UUID | None] = ContextVar("_current_batch_id", default=None)


def set_trace_batch_id(batch_id: uuid.UUID):
    _current_batch_id.set(batch_id)


def get_trace_batch_id() -> uuid.UUID | None:
    return _current_batch_id.get()


def _truncate_output(data: dict | str | None) -> dict | None:
    if data is None:
        return None
    if isinstance(data, str):
        data = {"result": data}
    serialized = json.dumps(data, ensure_ascii=False, default=str)
    if len(serialized.encode("utf-8")) > OUTPUT_MAX_BYTES:
        truncated = serialized.encode("utf-8")[:OUTPUT_MAX_BYTES].decode(
            "utf-8", errors="ignore"
        )
        return {"_truncated": True, "preview": truncated}
    return data


@dataclass
class TraceRecord:
    conversation_id: uuid.UUID
    node_name: str
    tool_name: str | None = None
    message_id: uuid.UUID | None = None
    input: dict | None = None
    output: dict | str | None = None
    status: str = "success"
    retry_count: int = 0
    latency_ms: int = 0
    error_detail: str | None = None


@dataclass
class TraceCollector:
    """Collects traces during a single request, then flushes in background."""

    conversation_id: uuid.UUID
    records: list[TraceRecord] = field(default_factory=list)

    def add(
        self,
        node_name: str,
        tool_name: str | None = None,
        message_id: uuid.UUID | None = None,
        input: dict | None = None,
        output: dict | str | None = None,
        status: str = "success",
        retry_count: int = 0,
        latency_ms: int = 0,
        error_detail: str | None = None,
    ):
        self.records.append(
            TraceRecord(
                conversation_id=self.conversation_id,
                node_name=node_name,
                tool_name=tool_name,
                message_id=message_id,
                input=input,
                output=output,
                status=status,
                retry_count=retry_count,
                latency_ms=latency_ms,
                error_detail=error_detail,
            )
        )

    def flush(self):
        if not self.records:
            return
        records = self.records.copy()
        self.records.clear()
        thread = threading.Thread(
            target=_flush_traces, args=(records,), daemon=True
        )
        thread.start()


def _flush_traces(records: Sequence[TraceRecord]):
    db = SessionLocal()
    try:
        for r in records:
            trace = AgentTrace(
                id=uuid.uuid4(),
                conversation_id=r.conversation_id,
                message_id=r.message_id,
                node_name=r.node_name,
                tool_name=r.tool_name,
                input=r.input,
                output=_truncate_output(r.output),
                status=r.status,
                retry_count=r.retry_count,
                latency_ms=r.latency_ms,
                error_detail=r.error_detail,
            )
            db.add(trace)
        db.commit()
        logger.debug("[Trace] Flushed {} traces", len(records))
    except Exception as e:
        logger.error("[Trace] Flush failed: {}", e)
        db.rollback()
    finally:
        db.close()


def write_trace_immediate(
    conversation_id: uuid.UUID,
    node_name: str,
    tool_name: str | None = None,
    input: dict | None = None,
    output: dict | str | None = None,
    status: str = "success",
    retry_count: int = 0,
    latency_ms: int = 0,
    error_detail: str | None = None,
):
    record = TraceRecord(
        conversation_id=conversation_id,
        node_name=node_name,
        tool_name=tool_name,
        input=input,
        output=output,
        status=status,
        retry_count=retry_count,
        latency_ms=latency_ms,
        error_detail=error_detail,
    )
    thread = threading.Thread(
        target=_flush_traces, args=([record],), daemon=True
    )
    thread.start()


def traced_node(node_name: str, conv_id_key: str = "_trace_conv_id"):
    """Decorator for LangGraph node functions to auto-record traces.

    The decorated node function receives state dict. The conversation_id
    is extracted from state[conv_id_key]. If not present, tracing is skipped.

    Captures: input summary, output summary, latency, errors.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(state: dict) -> dict:
            conv_id = state.get(conv_id_key)
            start = time.perf_counter()

            try:
                result = fn(state)
                latency = int((time.perf_counter() - start) * 1000)

                if conv_id:
                    output_summary = _extract_output_summary(result)
                    write_trace_immediate(
                        conversation_id=uuid.UUID(str(conv_id)) if not isinstance(conv_id, uuid.UUID) else conv_id,
                        node_name=node_name,
                        input=_extract_input_summary(state, node_name),
                        output=output_summary,
                        status="success",
                        retry_count=state.get("retry_count", 0),
                        latency_ms=latency,
                    )
                return result

            except Exception as e:
                latency = int((time.perf_counter() - start) * 1000)
                if conv_id:
                    write_trace_immediate(
                        conversation_id=uuid.UUID(str(conv_id)) if not isinstance(conv_id, uuid.UUID) else conv_id,
                        node_name=node_name,
                        input=_extract_input_summary(state, node_name),
                        status="error",
                        retry_count=state.get("retry_count", 0),
                        latency_ms=latency,
                        error_detail=str(e)[:500],
                    )
                raise

        return wrapper
    return decorator


def _extract_input_summary(state: dict, node_name: str) -> dict:
    summary = {}
    if "question" in state:
        summary["question"] = state["question"][:200]
    if "generated_sql" in state and state["generated_sql"]:
        summary["sql"] = state["generated_sql"][:500]
    if "tweets" in state:
        summary["tweet_count"] = len(state["tweets"])
    if "user_id" in state:
        summary["user_id"] = state["user_id"]
    return summary or None


def _extract_output_summary(result: dict | None) -> dict | None:
    if not result:
        return None
    summary = {}
    for key in ("sub_intent", "generated_sql", "validation_error", "execution_error", "result", "phase"):
        if key in result and result[key]:
            val = result[key]
            summary[key] = val[:500] if isinstance(val, str) else val
    if "partial_analyses" in result:
        summary["analyses_count"] = len(result["partial_analyses"])
    if "risk_assessments" in result:
        summary["risk_count"] = len(result["risk_assessments"])
    if "analyses" in result:
        summary["analyses_count"] = len(result["analyses"])
    if "predictions" in result:
        summary["predictions_count"] = len(result["predictions"])
    if "ticker_summaries" in result:
        summary["summaries_count"] = len(result["ticker_summaries"])
    if "classification" in result:
        cls = result["classification"]
        summary["has_investment"] = cls.get("has_investment_content", False)
        summary["classified_count"] = len(cls.get("classifications", []))
    return summary or None
