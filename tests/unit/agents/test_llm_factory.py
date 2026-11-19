from app.agents import llm


def test_signal_llm_has_bounded_request_budget(monkeypatch):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(llm, "require_analysis_enabled", lambda: None)
    monkeypatch.setattr(llm.httpx, "Client", lambda **kwargs: object())
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: object())
    monkeypatch.setattr(llm.settings, "signal_llm_timeout_seconds", 75.0)
    monkeypatch.setattr(llm.settings, "signal_llm_max_completion_tokens", 3000)
    monkeypatch.setattr(llm.settings, "signal_llm_reasoning_effort", "none")
    monkeypatch.setattr(llm.settings, "signal_llm_max_retries", 1)

    llm.get_signal_llm()

    assert captured["timeout"] == 75.0
    assert captured["max_retries"] == 1
    assert captured["max_completion_tokens"] == 3000
    assert captured["reasoning_effort"] == "none"
