from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings


def _settings(**overrides):
    values = {
        "openrouter_api_key": "test-openrouter",
        "dashscope_api_key": "test-dashscope",
        "jwt_secret_key": "test-jwt-secret",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_security_sensitive_logging_is_disabled_by_default():
    configured = _settings()

    assert configured.log_request_body is False
    assert configured.log_response_body is False


def test_cors_allowed_origins_can_be_configured():
    configured = _settings(
        cors_allowed_origins=["https://app.example.com", "https://admin.example.com"]
    )

    assert configured.cors_allowed_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_create_app_uses_configured_cors_origins(monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(
        main_module.settings,
        "cors_allowed_origins",
        ["https://app.example.com"],
    )
    application = main_module.create_app()
    cors = next(
        middleware
        for middleware in application.user_middleware
        if middleware.cls is CORSMiddleware
    )

    assert cors.kwargs["allow_origins"] == ["https://app.example.com"]


def test_settings_repr_redacts_secrets():
    configured = _settings(
        openrouter_api_key="openrouter-secret-value",
        dashscope_api_key="dashscope-secret-value",
        jwt_secret_key="jwt-secret-value",
        twitter_auth_token="twitter-secret-value",
    )

    rendered = repr(configured)

    assert "openrouter-secret-value" not in rendered
    assert "dashscope-secret-value" not in rendered
    assert "jwt-secret-value" not in rendered
    assert "twitter-secret-value" not in rendered
