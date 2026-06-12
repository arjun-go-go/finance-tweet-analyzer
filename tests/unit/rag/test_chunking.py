"""Unit tests for app.rag.chunking module."""

import pytest

from app.rag.chunking import chunk_document, chunk_tweet, chunk_analysis, char_count


def test_empty_input_returns_empty():
    assert chunk_document("", chunk_size=100, chunk_overlap=10) == []
    assert chunk_document("   ", chunk_size=100, chunk_overlap=10) == []


def test_short_text_returns_single_chunk():
    text = "Hello world"
    result = chunk_document(text, chunk_size=100, chunk_overlap=10)
    assert result == ["Hello world"]


def test_chunk_size_respected():
    text = "A" * 1000
    result = chunk_document(text, chunk_size=200, chunk_overlap=20)
    for c in result:
        assert len(c) <= 200


def test_chinese_separators():
    text = "第一段话。第二段话。第三段话。"
    result = chunk_document(text, chunk_size=8, chunk_overlap=0)
    assert len(result) >= 2
    # Verify splits at Chinese full stop
    assert any("。" in c for c in result)


def test_overlap_raises_if_ge_chunk_size():
    with pytest.raises(ValueError, match="chunk_overlap must be smaller"):
        chunk_document("hello", chunk_size=10, chunk_overlap=10)


def test_chunk_tweet_normal():
    assert chunk_tweet("Buy $AAPL") == ["Buy $AAPL"]


def test_chunk_tweet_empty():
    assert chunk_tweet("") == []
    assert chunk_tweet("   ") == []


def test_chunk_analysis_no_overlap():
    text = "X" * 200
    result = chunk_analysis(text, chunk_size=50)
    assert len(result) >= 3


def test_char_count():
    assert char_count("abc") == 3
    assert char_count("") == 0
    assert char_count("中文") == 2
