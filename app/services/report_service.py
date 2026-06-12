"""Service layer for report generation and retrieval."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.report_agent import generate_report
from app.models.report import Report


def create_report_record(
    db: Session,
    user_id: UUID,
    ticker: str,
    trigger_type: str,
    tracked_ticker_id: UUID | None = None,
) -> Report:
    """Insert a pending Report row (status='generating') without running the pipeline."""
    report = Report(
        user_id=user_id,
        ticker=ticker.upper(),
        title=f"{ticker.upper()} 跟踪报告",
        trigger_type=trigger_type,
        tracked_ticker_id=tracked_ticker_id,
        status="generating",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def create_and_run_report(
    db: Session,
    user_id: UUID,
    ticker: str,
    trigger_type: str,
    tracked_ticker_id: UUID | None = None,
) -> Report:
    """Create a report record and execute the generation pipeline."""
    report = Report(
        user_id=user_id,
        ticker=ticker.upper(),
        title=f"{ticker.upper()} 跟踪报告",
        trigger_type=trigger_type,
        tracked_ticker_id=tracked_ticker_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    try:
        result = generate_report(str(user_id), f"生成 {ticker} 跟踪报告")

        synthesis = result.get("synthesis") or {}
        sections_data = {s["name"]: s for s in result.get("sections", [])}
        citations = [
            {
                "index": item.get("global_index") or (i + 1),
                "source_type": item.get("source_type", ""),
                "snippet": (item.get("content", "") or "")[:200],
                "unique_id": item.get("unique_id", ""),
                "metadata": item.get("metadata", {}),
            }
            for i, item in enumerate(result.get("reranked", []))
        ]

        report.sections = sections_data
        report.citations = citations
        report.summary = synthesis.get("summary", "")
        report.consensus = synthesis.get("consensus", "neutral")
        report.token_usage = {}
        report.latency_ms = result.get("latency_ms", 0)
        report.status = "done"
        db.commit()
    except Exception as e:
        report.status = "failed"
        report.error_detail = str(e)[:1000]
        db.commit()

    db.refresh(report)
    return report


def get_report(db: Session, user_id: UUID, report_id: UUID) -> Report | None:
    return db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user_id)
    ).scalar_one_or_none()


def list_reports(
    db: Session, user_id: UUID, *, ticker: str | None = None, page: int = 1, size: int = 20
) -> tuple[list[Report], int]:
    query = select(Report).where(Report.user_id == user_id)
    count_query = select(func.count()).select_from(Report).where(Report.user_id == user_id)

    if ticker:
        query = query.where(Report.ticker == ticker.upper())
        count_query = count_query.where(Report.ticker == ticker.upper())

    total = db.execute(count_query).scalar_one()
    items = list(
        db.execute(
            query.order_by(Report.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).scalars().all()
    )
    return items, total


def delete_report(db: Session, user_id: UUID, report_id: UUID) -> bool:
    report = db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user_id)
    ).scalar_one_or_none()
    if not report:
        return False
    db.delete(report)
    db.commit()
    return True
