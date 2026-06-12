"""Unit tests for URL parser SSRF protections."""

from unittest.mock import patch, MagicMock

import pytest

from app.rag.parsers.url_parser import fetch_url
from app.rag.parsers.base import ParserError

BLOCKED = ["localhost", "127.0.0.1", "169.254.169.254"]


def test_rejects_file_scheme():
    with pytest.raises(ParserError, match="Only http/https"):
        fetch_url("file:///etc/passwd", blocked_hosts=BLOCKED, timeout=5)


def test_rejects_blocked_host_localhost():
    with pytest.raises(ParserError, match="blocklist"):
        fetch_url("https://localhost/api", blocked_hosts=BLOCKED, timeout=5)


def test_rejects_blocked_host_metadata():
    with pytest.raises(ParserError, match="blocklist"):
        fetch_url("http://169.254.169.254/latest/meta-data/", blocked_hosts=BLOCKED, timeout=5)


@patch("app.rag.parsers.url_parser.socket.getaddrinfo")
def test_rejects_private_ip_after_dns(mock_dns):
    mock_dns.return_value = [(2, 1, 6, '', ('10.0.0.1', 0))]
    with pytest.raises(ParserError, match="private"):
        fetch_url("http://evil.example.com/", blocked_hosts=BLOCKED, timeout=5)


@patch("app.rag.parsers.url_parser.trafilatura.extract")
@patch("app.rag.parsers.url_parser.requests.get")
@patch("app.rag.parsers.url_parser._is_private_ip", return_value=False)
def test_happy_path(mock_private, mock_get, mock_extract):
    mock_resp = MagicMock()
    mock_resp.url = "https://example.com/article"
    mock_resp.text = "<html><body>Content</body></html>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp
    mock_extract.return_value = "Extracted content"
    result = fetch_url("https://example.com/article", blocked_hosts=BLOCKED, timeout=5)
    assert result.text == "Extracted content"
    assert result.metadata["source_uri"] == "https://example.com/article"
