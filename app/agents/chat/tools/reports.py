from __future__ import annotations

from uuid import UUID

from app.agents.chat.tool_results import tool_ok


def generate_tracking_report_impl(db, user_id: UUID, ticker: str) -> str:
    """Queue a report and return immediately; generation runs in a worker."""
    from app.services.report_service import create_report_record

    report = create_report_record(
        db,
        user_id,
        ticker,
        trigger_type="chat",
        query=f"生成 {ticker.upper()} 当前研究报告，重点说明最新观点、重要变化、方向性预测和主要风险。",
    )
    return tool_ok(
        f"{ticker.upper()} 研究报告已进入后台生成队列。报告ID: {report.id}。可前往报告页面查看实时进度。",
        data={
            "report_id": str(report.id),
            "ticker": report.ticker,
            "status": report.status,
            "path": f"/reports/{report.id}",
        },
    )
