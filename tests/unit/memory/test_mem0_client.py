"""Unit tests for app.memory.mem0_client (self-hosted OSS mode)."""
from unittest.mock import MagicMock, patch


def _base_settings(mock_settings):
    mock_settings.mem0_enabled = True
    mock_settings.signal_model = "qwen/qwen3-7b"
    mock_settings.openrouter_api_key = "or-key"
    mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
    mock_settings.embedding_model = "text-embedding-v4"
    mock_settings.dashscope_api_key = "ds-key"
    mock_settings.embedding_dim = 1024
    mock_settings.mem0_chroma_path = "./test_chroma_mem0"
    mock_settings.mem0_history_db_path = "./test_mem0_history.db"
    mock_settings.mem0_vector_backend = "chroma"
    mock_settings.milvus_uri = "https://example.cloud.zilliz.com"
    mock_settings.milvus_token = "milvus-token"
    mock_settings.milvus_db_name = "default"
    mock_settings.mem0_milvus_collection = "finance_tweet_mem0_memories"
    mock_settings.mem0_milvus_metric_type = "COSINE"


def test_get_client_disabled_returns_none():
    """When mem0_enabled=False, get_mem0_client returns None."""
    with patch("app.memory.mem0_client.settings") as mock_settings:
        mock_settings.mem0_enabled = False
        import app.memory.mem0_client as m
        m._mem0_client_singleton = None
        result = m.get_mem0_client()
    assert result is None


def test_get_client_initializes_memory():
    """When mem0_enabled=True, get_mem0_client initializes Memory with config."""
    mock_memory = MagicMock()
    with patch("app.memory.mem0_client.settings") as mock_settings, \
         patch("app.memory.mem0_client.Memory") as mock_cls:
        mock_cls.from_config.return_value = mock_memory
        _base_settings(mock_settings)
        import app.memory.mem0_client as m
        m._mem0_client_singleton = None
        result = m.get_mem0_client()
    assert result is mock_memory
    mock_cls.from_config.assert_called_once()
    cfg = mock_cls.from_config.call_args[0][0]
    assert cfg["llm"]["provider"] == "openai"
    assert cfg["llm"]["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"
    assert cfg["embedder"]["provider"] == "openai"
    assert cfg["vector_store"]["provider"] == "chroma"
    assert cfg["vector_store"]["config"]["path"] == "./test_chroma_mem0"
    assert "http_client_proxies" not in cfg["llm"]["config"]
    assert "http_client_proxies" not in cfg["embedder"]["config"]


def test_get_client_uses_milvus_vector_store_when_configured():
    """When mem0_vector_backend=milvus, Memory is configured with mem0's Milvus provider."""
    mock_memory = MagicMock()
    with patch("app.memory.mem0_client.settings") as mock_settings, \
         patch("app.memory.mem0_client.Memory") as mock_cls:
        mock_cls.from_config.return_value = mock_memory
        _base_settings(mock_settings)
        mock_settings.mem0_vector_backend = "milvus"
        import app.memory.mem0_client as m
        m._mem0_client_singleton = None
        result = m.get_mem0_client()

    assert result is mock_memory
    cfg = mock_cls.from_config.call_args[0][0]
    assert cfg["vector_store"] == {
        "provider": "milvus",
        "config": {
            "url": "https://example.cloud.zilliz.com",
            "token": "milvus-token",
            "collection_name": "finance_tweet_mem0_memories",
            "embedding_model_dims": 1024,
            "metric_type": "COSINE",
            "db_name": "default",
        },
    }


def test_get_client_singleton():
    """get_mem0_client returns the same instance on repeated calls."""
    mock_memory = MagicMock()
    with patch("app.memory.mem0_client.settings") as mock_settings, \
         patch("app.memory.mem0_client.Memory") as mock_cls:
        mock_cls.from_config.return_value = mock_memory
        _base_settings(mock_settings)
        import app.memory.mem0_client as m
        m._mem0_client_singleton = None
        c1 = m.get_mem0_client()
        c2 = m.get_mem0_client()
    assert c1 is c2
    assert mock_cls.from_config.call_count == 1


def test_get_client_init_failure_returns_none():
    """When Memory.from_config raises, get_mem0_client returns None without crashing."""
    with patch("app.memory.mem0_client.settings") as mock_settings, \
         patch("app.memory.mem0_client.Memory") as mock_cls:
        mock_cls.from_config.side_effect = RuntimeError("connection refused")
        _base_settings(mock_settings)
        import app.memory.mem0_client as m
        m._mem0_client_singleton = None
        result = m.get_mem0_client()
    assert result is None
