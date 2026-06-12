"""Unit tests for RRF fusion algorithm."""

from app.rag.fusion import reciprocal_rank_fusion


def test_single_path():
    results = reciprocal_rank_fusion(
        [[{"unique_id": "a", "content": "x"}, {"unique_id": "b", "content": "y"}]],
        k=60,
        top_n=5,
    )
    assert [r["unique_id"] for r in results] == ["a", "b"]


def test_multi_path_overlap_boosted():
    """Items appearing in multiple paths get higher RRF score."""
    results = reciprocal_rank_fusion(
        [
            [{"unique_id": "a", "content": "1"}, {"unique_id": "b", "content": "2"}],
            [{"unique_id": "b", "content": "2"}, {"unique_id": "c", "content": "3"}],
        ],
        k=60,
        top_n=3,
    )
    assert results[0]["unique_id"] == "b"


def test_top_n_truncation():
    items = [{"unique_id": str(i), "content": ""} for i in range(100)]
    results = reciprocal_rank_fusion([items], k=60, top_n=10)
    assert len(results) == 10


def test_empty_paths():
    results = reciprocal_rank_fusion([[], []], k=60, top_n=5)
    assert results == []


def test_k_parameter_affects_scores():
    """Different k values should produce same ordering for simple cases."""
    path = [{"unique_id": "a", "content": ""}, {"unique_id": "b", "content": ""}]
    r1 = reciprocal_rank_fusion([path], k=1, top_n=2)
    r2 = reciprocal_rank_fusion([path], k=100, top_n=2)
    assert [r["unique_id"] for r in r1] == [r["unique_id"] for r in r2]
