"""Unit tests for app.rag.embeddings — embed_with_dedupe cache logic."""

import hashlib
from unittest.mock import MagicMock

from app.rag.embeddings import embed_with_dedupe


def test_empty_texts():
    embedder = MagicMock()
    session = MagicMock()
    embs, vids, hashes = embed_with_dedupe([], embedder=embedder, session=session)
    assert embs == [] and vids == [] and hashes == []
    embedder.embed_documents.assert_not_called()


def test_all_cache_miss():
    embedder = MagicMock()
    embedder.embed_documents.return_value = [[1.0], [2.0]]
    session = MagicMock()
    session.execute.return_value.all.return_value = []  # no cache hits
    embs, vids, hashes = embed_with_dedupe(["a", "b"], embedder=embedder, session=session)
    assert embs == [[1.0], [2.0]]
    assert vids == [None, None]
    assert len(hashes) == 2


def test_cache_hit_skips_api():
    embedder = MagicMock()
    embedder.embed_documents.return_value = [[1.0]]
    session = MagicMock()
    hash_b = hashlib.sha256("b".encode()).hexdigest()
    session.execute.return_value.all.return_value = [(hash_b, "vid_b")]
    embs, vids, hashes = embed_with_dedupe(["a", "b"], embedder=embedder, session=session)
    # "b" is a cache hit, so only "a" was embedded
    embedder.embed_documents.assert_called_once_with(["a"])
    assert embs[0] == [1.0]
    assert embs[1] is None
    assert vids[1] == "vid_b"


def test_in_batch_dedupe():
    embedder = MagicMock()
    embedder.embed_documents.return_value = [[1.0]]  # only 1 unique
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    embs, vids, hashes = embed_with_dedupe(["foo", "foo"], embedder=embedder, session=session)
    # Should call embedder only once with ["foo"]
    embedder.embed_documents.assert_called_once_with(["foo"])
    assert embs[0] == [1.0]
    assert embs[1] == [1.0]
