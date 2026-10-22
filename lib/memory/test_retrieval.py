"""Tests for retrieval.py — unified 3-signal search."""

import pytest
from pathlib import Path
from lib.memory.retrieval import unified_search


class TestUnifiedSearch:
    def test_empty_docs_returns_empty(self):
        result = unified_search("test query", shadow_docs={}, adj={}, bm25_docs={}, embed_docs={}, top_k=5)
        assert result == []

    def test_returns_list_of_tuples(self):
        docs = {"SD-1": "hello world", "SD-2": "foo bar"}
        result = unified_search("hello", shadow_docs=docs, adj={}, bm25_docs=docs, embed_docs=docs, top_k=5)
        assert len(result) > 0
        assert isinstance(result[0], tuple)
        assert len(result[0]) == 2

    def test_respects_top_k(self):
        docs = {f"SD-{i}": f"doc {i} content" for i in range(20)}
        result = unified_search("doc", shadow_docs=docs, adj={}, bm25_docs=docs, embed_docs=docs, top_k=3)
        assert len(result) <= 3

    def test_scores_non_negative(self):
        docs = {"SD-1": "test content", "SD-2": "other content"}
        result = unified_search("test", shadow_docs=docs, adj={}, bm25_docs=docs, embed_docs=docs, top_k=5)
        for doc_id, score in result:
            assert score >= 0

    def test_relevant_doc_ranks_first(self):
        docs = {"SD-HELLO": "hello world greeting", "SD-OTHER": "completely different topic"}
        result = unified_search("hello", shadow_docs=docs, adj={}, bm25_docs=docs, embed_docs=docs, top_k=2)
        assert len(result) > 0
        assert result[0][0] == "SD-HELLO"
