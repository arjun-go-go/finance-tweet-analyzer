"""Unit tests for app.rag.vector_store — ChromaVectorStore and factory."""

from unittest.mock import Mock, patch

import pytest

from app.rag.vector_store import ChromaVectorStore, MilvusVectorStore, get_vector_store, VectorHit
import app.rag.vector_store as vector_store_module


def test_chroma_add_query_delete(tmp_path):
    vs = ChromaVectorStore(persist_dir=str(tmp_path))
    assert vs.count("public_signals") == 0
    vs.add("public_signals", ["id1"], ["hello"], [[1.0, 0.0]], [{"source_type": "tweet"}])
    assert vs.count("public_signals") == 1
    hits = vs.query("public_signals", [1.0, 0.0], k=1)
    assert len(hits) == 1
    assert hits[0].id == "id1"
    vs.delete("public_signals", ["id1"])
    assert vs.count("public_signals") == 0


def test_factory_chroma(tmp_path):
    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "chroma"
        mock_settings.chroma_persist_dir = str(tmp_path)
        vector_store_module._vector_store_singleton = None
        vs = get_vector_store()
        assert isinstance(vs, ChromaVectorStore)
        vector_store_module._vector_store_singleton = None


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


def test_milvus_add_remains_compatible_with_existing_signal_schema():
    vs = object.__new__(MilvusVectorStore)
    vs._collection_prefix = "finance_tweet"
    vs._timeout_sec = 30.0
    vs._ensured = {"finance_tweet_public_signals"}
    vs._collection_fields = {
        "finance_tweet_public_signals": {
            "id", "vector", "content", "metadata", "source_type",
            "ticker", "user_id", "document_id",
        }
    }
    vs._client = fake_client = Mock()

    vs.add(
        "public_signals",
        ["tweet:1:0"],
        ["content"],
        [[0.1, 0.2]],
        [{"source_type": "tweet", "source_id": "1", "index_stage": "raw"}],
    )

    row = fake_client.upsert.call_args.kwargs["data"][0]
    assert row["user_id"] == ""
    assert row["document_id"] == ""
    assert row["metadata"]["source_id"] == "1"


def test_factory_unknown_raises():
    import pytest

    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "bogus"
        vector_store_module._vector_store_singleton = None
        with pytest.raises(ValueError, match="Unknown vector backend"):
            get_vector_store()
        vector_store_module._vector_store_singleton = None
