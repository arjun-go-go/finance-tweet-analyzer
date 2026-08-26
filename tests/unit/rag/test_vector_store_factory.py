"""Unit tests for the Milvus vector store and factory."""

from unittest.mock import Mock, patch

import pytest

from app.rag.vector_store import MilvusVectorStore, get_vector_store
import app.rag.vector_store as vector_store_module


def test_factory_milvus():
    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "milvus"
        mock_settings.milvus_uri = "https://example.cloud.zilliz.com"
        mock_settings.milvus_token = "test-token"
        mock_settings.milvus_db_name = "default"
        mock_settings.milvus_collection_prefix = "finance_tweet"
        mock_settings.embedding_dim = 1024
        mock_settings.milvus_timeout_sec = 30.0
        vector_store_module._vector_store_singleton = None
        with patch("pymilvus.MilvusClient") as client_cls:
            client = client_cls.return_value
            client.has_collection.return_value = True
            vs = get_vector_store()
            assert isinstance(vs, MilvusVectorStore)
            client_cls.assert_called_once_with(
                uri="https://example.cloud.zilliz.com",
                token="test-token",
                db_name="default",
                timeout=30.0,
            )
            assert client.load_collection.call_count == 1
        vector_store_module._vector_store_singleton = None


def test_milvus_collection_name_mapping():
    vs = object.__new__(MilvusVectorStore)
    vs._collection_prefix = "finance_tweet"

    assert vs._physical_name("public_signals") == "finance_tweet_public_signals"
    with pytest.raises(KeyError):
        vs._physical_name("user_documents")


def test_milvus_filter_expression():
    expr = MilvusVectorStore._filter_to_expr({
        "$and": [
            {"source_type": "tweet"},
            {"ticker": "NVDA"},
        ]
    })

    assert expr == '(source_type == "tweet") and (ticker == "NVDA")'


def test_milvus_add_projects_common_metadata_fields():
    vs = object.__new__(MilvusVectorStore)
    vs._collection_prefix = "finance_tweet"
    vs._timeout_sec = 30.0
    vs._ensured = {"finance_tweet_public_signals"}
    vs._collection_fields = {
        "finance_tweet_public_signals": {
            "id", "vector", "content", "metadata", "source_type",
            "source_id", "index_stage", "ticker",
        }
    }
    vs._client = fake_client = Mock()

    vs.add(
        "public_signals",
        ["id1"],
        ["content"],
        [[0.1, 0.2]],
        [{
            "source_type": "tweet",
            "source_id": "tweet-1",
            "index_stage": "raw",
            "ticker": "NVDA",
            "ignored": None,
        }],
    )

    fake_client.upsert.assert_called_once()
    row = fake_client.upsert.call_args.kwargs["data"][0]
    assert row["id"] == "id1"
    assert row["content"] == "content"
    assert row["source_type"] == "tweet"
    assert row["source_id"] == "tweet-1"
    assert row["index_stage"] == "raw"
    assert row["ticker"] == "NVDA"
    assert row["metadata"] == {
        "source_type": "tweet",
        "source_id": "tweet-1",
        "index_stage": "raw",
        "ticker": "NVDA",
    }


def test_factory_unknown_raises():
    import pytest

    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "bogus"
        vector_store_module._vector_store_singleton = None
        with pytest.raises(ValueError, match="VECTOR_BACKEND must be 'milvus'"):
            get_vector_store()
        vector_store_module._vector_store_singleton = None
