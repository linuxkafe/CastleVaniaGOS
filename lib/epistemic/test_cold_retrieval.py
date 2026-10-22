"""Tests for cold-layer retrieval (T052)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.epistemic.cold_retrieval import (
    power_iteration,
    build_shadow_graph,
    hybrid_bm25_ppr,
    _tokenize,
)


def test_tokenize_removes_stopwords():
    tokens = _tokenize("the quick brown fox jumps over the lazy dog")
    assert "the" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens


def test_tokenize_short_tokens():
    tokens = _tokenize("a an the of to in it is")
    assert tokens == []


def test_tokenize_portuguese():
    tokens = _tokenize("um gato preto e um cão branco")
    assert "gato" in tokens
    assert "preto" in tokens
    assert "um" not in tokens


def test_power_iteration_empty():
    assert power_iteration({}, {}) == {}


def test_power_iteration_single_node():
    adj = {"a": set()}
    result = power_iteration(adj, {"a": 1.0})
    assert "a" in result
    # Single dangling node converges to (1-alpha) = 0.15
    assert abs(result["a"] - 0.15) < 0.02


def test_power_iteration_two_nodes():
    adj = {"a": {"b"}, "b": {"a"}}
    result = power_iteration(adj, {"a": 1.0, "b": 0.0})
    # Seeded node should have higher score
    assert result["a"] > result["b"]


def test_power_iteration_converges():
    adj = {"a": {"b", "c"}, "b": {"a"}, "c": {"a"}}
    result = power_iteration(adj, {"a": 1.0})
    assert len(result) == 3
    scores = sorted(result.values(), reverse=True)
    assert scores[0] > 0


def test_build_shadow_graph_returns_dict():
    graph = build_shadow_graph(
        shadow_dir=Path("aes/shadow"),
    )
    assert isinstance(graph, dict)
    if graph:
        for node, neighbors in graph.items():
            assert isinstance(node, str)
            assert isinstance(neighbors, set)


def test_hybrid_bm25_ppr_fallback():
    """Hybrid returns BM25 results when no graph adj."""
    from lib.memory.relevance import bm25_search
    docs = {"a": "hello world", "b": "foo bar"}
    result = hybrid_bm25_ppr("hello", bm25_search, docs, {}, top_k_bm25=10)
    assert len(result) >= 1


def test_hybrid_bm25_ppr_with_graph():
    """Hybrid runs on a simple graph."""
    from lib.memory.relevance import bm25_search
    docs = {"a": "hello world", "b": "world hello", "c": "foo bar"}
    adj = {"a": {"b"}, "b": {"a"}}
    result = hybrid_bm25_ppr("hello", bm25_search, docs, adj, top_k_bm25=5)
    assert len(result) >= 1
    for doc_id, score in result:
        assert score > 0 or doc_id in adj
