"""Tests for layers.py — 4-layer memory stack."""

import pytest
from pathlib import Path
from lib.memory.layers import MemoryStack, SearchResult, LayerResult


class TestMemoryStack:
    def test_search_returns_search_result(self):
        stack = MemoryStack()
        result = stack.search("test query", max_layers=0, top_k=5)
        assert isinstance(result, SearchResult)

    def test_search_layer_used(self):
        stack = MemoryStack()
        result = stack.search("test", max_layers=0, top_k=5)
        assert result.layer_used == "L0"

    def test_search_layers_checked(self):
        stack = MemoryStack()
        result = stack.search("test", max_layers=2, top_k=5)
        assert "L0" in result.layers_checked

    def test_search_latency_non_negative(self):
        stack = MemoryStack()
        result = stack.search("test", max_layers=3, top_k=5)
        assert result.total_latency_ms >= 0

    def test_search_max_layers_0(self):
        stack = MemoryStack()
        result = stack.search("test", max_layers=0, top_k=5)
        assert result.layer_used == "L0"
        assert len(result.layers_checked) == 1

    def test_search_max_layers_3(self):
        stack = MemoryStack()
        result = stack.search("test", max_layers=3, top_k=5)
        assert len(result.layers_checked) >= 1
        assert result.layer_used in ("L0", "L1", "L2", "L3")

    def test_results_are_scored(self):
        stack = MemoryStack()
        result = stack.search("AES", max_layers=3, top_k=5)
        for doc_id, score in result.results:
            assert isinstance(score, (int, float))
            assert score >= 0
