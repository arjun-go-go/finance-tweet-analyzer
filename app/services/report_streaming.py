"""Report 流式生成服务

被 Celery `report_streaming_task` 调用：
  1. 跑 generate_report_streaming 迭代图节点
  2. 每个节点完成后：
     - 通过 Redis pub/sub 推送事件到 SSE 频道
     - 关键节点同时增量写库（rerank → citations, generate_section → sections,
       synthesize → summary/consensus/status=done）
  3. 用 channel 名 `report_stream:{report_id}` 隔离不同报告
"""

from __future__ import annotations

import json
import time
from uuid import UUID

import redis
from loguru import logger
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.agents.report_agent import generate_report_streaming
from app.core.config import settings
from app.models.report import Report


# --- Redis 连接（专用于 pub/sub，独立于 locks 的连接）---

_publisher: redis.Redis | None = None


def _get_publisher() -> redis.Redis:
    global _publisher
    if _publisher is None:
        _publisher = redis.from_url(settings.redis_url, decode_responses=True)
    return _publisher


def channel_for(report_id: UUID | str) -> str:
    return f"{settings.report_stream_redis_channel_prefix}:{report_id}"


def _publish(report_id: UUID | str, event: str, data: dict) -> None:
    try:
        _get_publisher().publish(
            channel_for(report_id),
            json.dumps({"event": event, "data": data}, ensure_ascii=False),
        )
    except Exception as e:  # publish 失败不能阻塞主流程
        logger.warning(f"SSE publish failed for {report_id}: {e}")


# --- 增量落库辅助 ---


def _persist_citations(db: Session, report_id: UUID, reranked: list[dict]) -> list[dict]:
    citations = [
        {
            "index": item.get("global_index") or (i + 1),
            "source_type": item.get("source_type", ""),
            "snippet": (item.get("content", "") or "")[:200],
            "unique_id": item.get("unique_id", ""),
            "metadata": item.get("metadata", {}),
        }
        for i, item in enumerate(reranked)
    ]
    db.execute(update(Report).where(Report.id == report_id).values(citations=citations))
    db.commit()
    return citations


def _persist_section(db: Session, report_id: UUID, section: dict) -> None:
    """Merge 单个 section 进 sections JSONB（按 name 作 key）。"""
    report = db.get(Report, report_id)
    if not report:
        return
    sections = dict(report.sections or {})
    sections[section["name"]] = section
    report.sections = sections
    db.commit()


def _persist_synthesis(db: Session, report_id: UUID, synthesis: dict, latency_ms: int) -> None:
    db.execute(
        update(Report).where(Report.id == report_id).values(
            summary=synthesis.get("summary", ""),
            consensus=synthesis.get("consensus", "neutral"),
            latency_ms=latency_ms,
            status="done",
        )
    )
    db.commit()


def _persist_failure(db: Session, report_id: UUID, error: str) -> None:
    db.execute(
        update(Report).where(Report.id == report_id).values(
            status="failed",
            error_detail=error[:1000],
        )
    )
    db.commit()


# --- 主入口 ---


def run_report_streaming(
    db: Session,
    report_id: UUID,
    user_id: UUID,
    query: str,
) -> dict:
    """跑流式报告生成，边发 SSE 边写库。返回最终状态摘要。"""
    start = time.perf_counter()
    _publish(report_id, "start", {"report_id": str(report_id), "status": "generating"})

    try:
        for node_name, node_output in generate_report_streaming(str(user_id), query):
            # parse_intent: 推送 intent 解析完成
            if node_name == "parse_intent":
                _publish(report_id, "intent_parsed", {
                    "intent": node_output.get("intent"),
                })
            # retrieve_*: 单路检索完成
            elif node_name.startswith("retrieve_"):
                errors = node_output.get("retrieval_errors") or {}
                results = node_output.get("retrieve_results") or [[]]
                count = sum(len(r) for r in results)
                _publish(report_id, "retrieval_progress", {
                    "node": node_name,
                    "count": count,
                    "errors": errors,
                })
            # fuse: RRF 合并完成
            elif node_name == "fuse":
                fused = node_output.get("fused") or []
                _publish(report_id, "fused", {
                    "count": len(fused),
                    "error": node_output.get("error"),
                })
            # rerank: 精排完成 → 落库 citations + 推送
            elif node_name == "rerank":
                reranked = node_output.get("reranked") or []
                citations = _persist_citations(db, report_id, reranked)
                _publish(report_id, "reranked", {"citations": citations})
            # generate_section: 单章节完成 → 落库 sections + 推送
            elif node_name == "generate_section":
                sections_list = node_output.get("sections") or []
                for section in sections_list:
                    _persist_section(db, report_id, section)
                    _publish(report_id, "section_done", {"section": section})
            # synthesize: 综合完成 → 落库 + 推送
            elif node_name == "synthesize":
                synthesis = node_output.get("synthesis") or {}
                latency = int((time.perf_counter() - start) * 1000)
                _persist_synthesis(db, report_id, synthesis, latency)
                _publish(report_id, "synthesized", {
                    **synthesis,
                    "latency_ms": latency,
                })

        _publish(report_id, "done", {})
        return {"status": "done", "report_id": str(report_id)}

    except Exception as e:
        logger.exception(f"Report streaming failed for {report_id}")
        _persist_failure(db, report_id, str(e))
        _publish(report_id, "error", {"error": str(e)[:500]})
        return {"status": "failed", "report_id": str(report_id), "error": str(e)}
