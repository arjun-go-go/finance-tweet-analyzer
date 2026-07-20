import json
import uuid
from types import SimpleNamespace

from app.agents import chat_agent
from app.services import report_service, tracking_service, user_resource_service


class _Db:
    def close(self):
        pass


def test_generate_tracking_report_passes_authenticated_user(monkeypatch):
    user_id = uuid.uuid4()
    captured = {}
    monkeypatch.setattr(chat_agent, "SessionLocal", _Db)

    def create_report(db, passed_user_id, ticker, trigger_type):
        captured.update(
            user_id=passed_user_id,
            ticker=ticker,
            trigger_type=trigger_type,
        )
        return SimpleNamespace(
            status="done",
            summary="summary",
            consensus="neutral",
            id=uuid.uuid4(),
        )

    monkeypatch.setattr(report_service, "create_and_run_report", create_report)

    chat_agent.generate_tracking_report.invoke(
        {"ticker": "TSLA", "time_range": "1w"},
        config={"metadata": {"user_id": str(user_id), "current_message": "确认生成 TSLA 报告"}},
    )

    assert captured == {
        "user_id": user_id,
        "ticker": "TSLA",
        "trigger_type": "chat",
    }


def test_generate_tracking_report_requires_explicit_confirmation(monkeypatch):
    user_id = uuid.uuid4()
    called = False
    monkeypatch.setattr(chat_agent, "SessionLocal", _Db)

    def create_report(db, passed_user_id, ticker, trigger_type):
        nonlocal called
        called = True
        return SimpleNamespace(status="done", summary="summary", consensus="neutral", id=uuid.uuid4())

    monkeypatch.setattr(report_service, "create_and_run_report", create_report)

    result = chat_agent.generate_tracking_report.invoke(
        {"ticker": "TSLA", "time_range": "1w"},
        config={"metadata": {"user_id": str(user_id), "current_message": "帮我看看 TSLA"}},
    )

    assert called is False
    envelope = json.loads(result)
    assert envelope["ok"] is False
    assert envelope["error_code"] == "CONFIRMATION_REQUIRED"
    assert "确认生成 TSLA 报告" in envelope["message"]


def test_list_tracked_tickers_passes_authenticated_user(monkeypatch):
    user_id = uuid.uuid4()
    captured = {}
    monkeypatch.setattr(chat_agent, "SessionLocal", _Db)

    def list_items(db, passed_user_id):
        captured["user_id"] = passed_user_id
        return []

    monkeypatch.setattr(tracking_service, "list_subscriptions", list_items)

    chat_agent.list_my_tracked_tickers.invoke(
        {},
        config={"metadata": {"user_id": str(user_id)}}
    )

    assert captured["user_id"] == user_id


def test_list_followed_bloggers_passes_authenticated_user(monkeypatch):
    user_id = uuid.uuid4()
    captured = {}
    monkeypatch.setattr(chat_agent, "SessionLocal", _Db)

    def list_items(db, passed_user_id, *, limit, offset):
        captured.update(user_id=passed_user_id, limit=limit, offset=offset)
        return (
            [
                SimpleNamespace(
                    handle="tesla_analyst",
                    name="Tesla Analyst",
                    credibility_score=8.2,
                    total_predictions=12,
                    correct_predictions=9,
                )
            ],
            1,
        )

    monkeypatch.setattr(user_resource_service, "list_followed_bloggers", list_items)

    result = chat_agent.list_my_followed_bloggers.invoke(
        {},
        config={"metadata": {"user_id": str(user_id)}},
    )

    assert captured == {"user_id": user_id, "limit": 20, "offset": 0}
    assert "@tesla_analyst" in result
    assert "Tesla Analyst" in result
    assert "正式关注列表" in result


def test_private_tools_fail_closed_without_user_identity(monkeypatch):
    monkeypatch.setattr(chat_agent, "SessionLocal", _Db)

    report_result = chat_agent.generate_tracking_report.invoke(
        {"ticker": "TSLA", "time_range": "1w"}, config={"metadata": {}}
    )
    tracking_result = chat_agent.list_my_tracked_tickers.invoke(
        {}, config={"metadata": {}}
    )
    followed_bloggers_result = chat_agent.list_my_followed_bloggers.invoke(
        {}, config={"metadata": {}}
    )

    assert "用户身份无效" in report_result
    assert "用户身份无效" in tracking_result
    assert "用户身份无效" in followed_bloggers_result
