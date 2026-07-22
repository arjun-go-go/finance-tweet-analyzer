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


def test_elasticsearch_keyword_settings_have_safe_defaults():
    configured = _settings()

    assert configured.rag_keyword_backend == "elasticsearch"
    assert configured.elasticsearch_url == ""
    assert configured.elasticsearch_username == ""
    assert configured.elasticsearch_password == ""
    assert configured.es_rag_index == "finance_rag_chunks"
    assert configured.es_request_timeout_sec == 3.0
    assert configured.es_bulk_chunk_size == 500


def test_elasticsearch_keyword_settings_can_be_configured():
    configured = _settings(
        rag_keyword_backend="elasticsearch",
        elasticsearch_url="http://localhost:9200",
        elasticsearch_username="es_admin",
        elasticsearch_password="secret",
        es_rag_index="custom_chunks",
        es_request_timeout_sec=5,
        es_bulk_chunk_size=100,
    )

    assert configured.rag_keyword_backend == "elasticsearch"
    assert configured.elasticsearch_url == "http://localhost:9200"
    assert configured.elasticsearch_username == "es_admin"
    assert configured.elasticsearch_password == "secret"
    assert configured.es_rag_index == "custom_chunks"
    assert configured.es_request_timeout_sec == 5
    assert configured.es_bulk_chunk_size == 100


def test_elasticsearch_password_is_redacted_from_repr():
    configured = _settings(elasticsearch_password="es-password-value")

    assert "es-password-value" not in repr(configured)
