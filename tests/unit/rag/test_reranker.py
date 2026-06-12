"""Unit tests for DashScope reranker module."""

from unittest.mock import patch, MagicMock

from app.rag.reranker import rerank


def test_rerank_empty_documents():
    result = rerank("test query", [], top_n=5)
    assert result == []


def test_rerank_fewer_than_top_n():
    """When documents <= top_n, return all without calling API."""
    result = rerank("test query", ["doc1", "doc2"], top_n=5)
    assert len(result) == 2
    assert result[0] == (0, 1.0)
    assert result[1] == (1, 1.0)


@patch("app.rag.reranker._rerank_with_circuit")
def test_rerank_fallback_on_circuit_break(mock_circuit):
    """Circuit breaker fallback returns original order."""
    mock_circuit.return_value = "[熔断] __RERANK_FALLBACK__"
    result = rerank("query", ["a", "b", "c", "d", "e"], top_n=3)
    assert len(result) == 3
    assert result[0][0] == 0
    assert result[1][0] == 1
    assert result[2][0] == 2


@patch("app.rag.reranker._rerank_with_circuit")
def test_rerank_success(mock_circuit):
    """Successful rerank returns indices with scores."""
    mock_circuit.return_value = [(2, 0.95), (0, 0.8), (1, 0.6)]
    result = rerank("query", ["a", "b", "c", "d", "e"], top_n=3)
    assert result == [(2, 0.95), (0, 0.8), (1, 0.6)]
