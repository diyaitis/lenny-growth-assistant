import math

from app.services.retriever import cosine_similarity, rank_chunks_by_similarity


def test_cosine_similarity_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-6)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_cosine_similarity_opposite_vectors_is_negative_one():
    assert math.isclose(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0, rel_tol=1e-6)


def test_rank_chunks_returns_most_similar_first():
    query = [1.0, 0.0, 0.0]
    candidates = [
        ("far", [0.0, 1.0, 0.0]),
        ("close", [0.9, 0.1, 0.0]),
        ("exact", [1.0, 0.0, 0.0]),
        ("opposite", [-1.0, 0.0, 0.0]),
    ]
    ranked = rank_chunks_by_similarity(query, candidates, top_k=2)
    ids_in_order = [cid for cid, _ in ranked]
    assert ids_in_order == ["exact", "close"]


def test_rank_chunks_respects_top_k():
    query = [1.0, 0.0]
    candidates = [(str(i), [1.0, 0.0]) for i in range(10)]
    ranked = rank_chunks_by_similarity(query, candidates, top_k=3)
    assert len(ranked) == 3


def test_rank_chunks_skips_empty_vectors():
    query = [1.0, 0.0]
    candidates = [("has_vector", [1.0, 0.0]), ("no_vector", [])]
    ranked = rank_chunks_by_similarity(query, candidates, top_k=5)
    assert [cid for cid, _ in ranked] == ["has_vector"]
