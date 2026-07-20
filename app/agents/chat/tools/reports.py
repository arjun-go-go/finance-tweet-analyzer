from __future__ import annotations

from uuid import UUID


def generate_tracking_report_impl(db, user_id: UUID, ticker: str) -> str:
    """Create and run a tracking report, returning the user-facing summary."""
    from app.services.report_service import create_and_run_report

    report = create_and_run_report(db, user_id, ticker, trigger_type="chat")
    if report.status == "done":
        summary = report.summary or "报告生成完成"
        return (
            f"{ticker} 跟踪报告已生成\n\n{summary}\n\n"
            f"评级: {report.consensus or 'N/A'}\n报告ID: {report.id}"
        )
    return f"报告生成失败: {report.error_detail or '未知错误'}"
