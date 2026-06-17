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
