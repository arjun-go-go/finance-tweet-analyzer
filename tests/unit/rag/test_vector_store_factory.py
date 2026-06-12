"""Unit tests for app.rag.vector_store — ChromaVectorStore and factory."""

from unittest.mock import patch

from app.rag.vector_store import ChromaVectorStore, get_vector_store, VectorHit


def test_chroma_add_query_delete(tmp_path):
    vs = ChromaVectorStore(persist_dir=str(tmp_path))
    assert vs.count("user_documents") == 0
    vs.add("user_documents", ["id1"], ["hello"], [[1.0, 0.0]], [{"user_id": "u1"}])
    assert vs.count("user_documents") == 1
    hits = vs.query("user_documents", [1.0, 0.0], k=1)
    assert len(hits) == 1
    assert hits[0].id == "id1"
    vs.delete("user_documents", ["id1"])
    assert vs.count("user_documents") == 0


def test_factory_chroma(tmp_path):
    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "chroma"
        mock_settings.chroma_persist_dir = str(tmp_path)
        get_vector_store.cache_clear()
        vs = get_vector_store()
        assert isinstance(vs, ChromaVectorStore)
        get_vector_store.cache_clear()


def test_factory_milvus_not_implemented():
    import pytest

    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "milvus"
        get_vector_store.cache_clear()
        with pytest.raises(NotImplementedError):
            get_vector_store()
        get_vector_store.cache_clear()


def test_factory_unknown_raises():
    import pytest

    with patch("app.rag.vector_store.settings") as mock_settings:
        mock_settings.vector_backend = "bogus"
        get_vector_store.cache_clear()
        with pytest.raises(ValueError, match="Unknown vector backend"):
            get_vector_store()
        get_vector_store.cache_clear()
