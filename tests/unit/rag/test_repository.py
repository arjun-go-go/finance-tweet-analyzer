"""Unit tests for app.rag.repository — user_id isolation and security."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.rag.repository import UserDocumentRepository, Chunk


def _make_repo():
    vs = MagicMock()
    embedder = MagicMock()
    return UserDocumentRepository(vs=vs, embedder=embedder), vs, embedder


def test_search_rejects_user_id_override():
    repo, vs, embedder = _make_repo()
    embedder.embed_query.return_value = [0.0] * 10
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    with pytest.raises(PermissionError, match="user_id filter override is forbidden"):
        repo.search(user_id=user_a, query="test", extra_filter={"user_id": str(user_b)})


def test_search_allows_same_user_id_in_filter():
    repo, vs, embedder = _make_repo()
    embedder.embed_query.return_value = [0.0] * 10
    vs.query.return_value = []
    user_a = uuid.uuid4()
    # Should not raise
    repo.search(user_id=user_a, query="test", extra_filter={"user_id": str(user_a)})


def test_search_merges_extra_filter():
    repo, vs, embedder = _make_repo()
    embedder.embed_query.return_value = [0.0] * 10
    vs.query.return_value = []
    uid = uuid.uuid4()
    repo.search(user_id=uid, query="hi", extra_filter={"document_id": "abc"})
    call_kwargs = vs.query.call_args
    flt = call_kwargs[1]["filter"] if "filter" in call_kwargs[1] else call_kwargs[0][3]
    assert flt["user_id"] == str(uid)
    assert flt["document_id"] == "abc"


def test_add_chunks_metadata_contains_user_id():
    repo, vs, embedder = _make_repo()
    embedder.embed_documents.return_value = [[1.0, 2.0]]
    uid = uuid.uuid4()
    did = uuid.uuid4()
    chunks = [Chunk(content="hello", chunk_index=0, metadata={})]
    repo.add_chunks(user_id=uid, document_id=did, chunks=chunks)
    # add() is called with positional args: collection, ids, texts, embeddings, metadatas
    metadatas = vs.add.call_args[0][4]
    assert metadatas[0]["user_id"] == str(uid)


def test_add_chunks_empty():
    repo, vs, embedder = _make_repo()
    result = repo.add_chunks(user_id=uuid.uuid4(), document_id=uuid.uuid4(), chunks=[])
    assert result == []
    embedder.embed_documents.assert_not_called()
    vs.add.assert_not_called()


def test_delete_document_filters_by_user_and_doc():
    repo, vs, embedder = _make_repo()
    hit1 = MagicMock()
    hit1.id = "chunk1"
    hit2 = MagicMock()
    hit2.id = "chunk2"
    vs.query.return_value = [hit1, hit2]
    uid = uuid.uuid4()
    did = uuid.uuid4()
    repo.delete_document(user_id=uid, document_id=did)
    # Verify filter contains $and with both user_id and document_id
    call_args = vs.query.call_args
    # The call is positional: (collection, query_embedding, k, filter)
    # or keyword. Check both.
    if call_args[1]:
        flt = call_args[1].get("filter") or call_args[1].get("k")
    else:
        flt = None
    # Actually the implementation uses positional args in vs.query(collection, emb, k=..., filter=...)
    # Let's just verify via kwargs
    flt = call_args.kwargs.get("filter", call_args.args[3] if len(call_args.args) > 3 else None)
    assert flt is not None
    assert "$and" in flt
    assert {"user_id": str(uid)} in flt["$and"]
    assert {"document_id": str(did)} in flt["$and"]
    vs.delete.assert_called_once_with("user_documents", ["chunk1", "chunk2"])
