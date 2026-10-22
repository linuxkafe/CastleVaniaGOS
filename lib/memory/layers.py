"""
4-Layer Memory Stack — MemPalace-inspired hierarchical retrieval.

Maps to AES's existing memory architecture:
  L0 (Identity):    Core project identity — CLAUDE.md, AGENTS.md, skills
  L1 (Working):     INDEX.md — hot index, auto-generated, ~20 entries
  L2 (Recent):      RELEVANT NOW — top-10 by ACT-R activation + centrality
  L3 (Deep):        All shadow docs — searched via BM25/embeddings/PPR

Retrieval proceeds top-down: check L0 → L1 → L2 → L3.
Each layer returns if confidence is high enough, avoiding expensive L3 search.

References:
  - MemPalace (2025): "Memory Palaces for LLM Agents"
  - ACT-R (Anderson 2007): Adaptive Control of Thought—Rational
  - AES wake/sleep cycle (consolidate.py)

Usage:
    from lib.memory.layers import MemoryStack
    stack = MemoryStack()
    results = stack.search("my query", max_layers=3)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

AES_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class LayerResult:
    """Result from a single memory layer."""
    layer: str          # "L0", "L1", "L2", "L3"
    confidence: float   # [0, 1] — how confident this layer is in its results
    doc_ids: List[str]  # retrieved document IDs
    scores: Dict[str, float]  # {doc_id: score} for ranking
    latency_ms: float = 0.0


@dataclass
class SearchResult:
    """Aggregated result from the memory stack."""
    layer_used: str            # which layer provided the final answer
    results: List[Tuple[str, float]]  # [(doc_id, score)]
    layers_checked: List[str]  # which layers were consulted
    total_latency_ms: float = 0.0


class MemoryStack:
    """4-layer memory stack for hierarchical retrieval."""

    def __init__(self):
        self._index_cache: Optional[Dict[str, str]] = None
        self._relevant_now_cache: Optional[Dict[str, str]] = None

    def search(
        self,
        query: str,
        max_layers: int = 3,
        confidence_threshold: float = 0.5,
        top_k: int = 10,
    ) -> SearchResult:
        """
        Search memory stack top-down: L0 → L1 → L2 → L3.

        Args:
            query: Search query
            max_layers: How deep to search (0=L0 only, 3=all layers)
            confidence_threshold: Min confidence to stop searching
            top_k: Number of results to return

        Returns:
            SearchResult with the best results found
        """
        import time
        total_start = time.perf_counter()
        layers_checked = []
        empty = LayerResult("L0", 0.0, [], {})
        l0 = l1 = l2 = l3 = empty

        # L0: Identity — exact match on project identity docs
        if max_layers >= 0:
            l0 = self._search_l0(query)
            layers_checked.append("L0")
            if l0.confidence >= confidence_threshold and len(l0.doc_ids) >= top_k:
                return SearchResult(
                    layer_used="L0",
                    results=[(d, l0.scores.get(d, 0.0)) for d in l0.doc_ids[:top_k]],
                    layers_checked=layers_checked,
                    total_latency_ms=(time.perf_counter() - total_start) * 1000,
                )

        # L1: Working Memory — INDEX.md entries
        if max_layers >= 1:
            l1 = self._search_l1(query)
            layers_checked.append("L1")
            if l1.confidence >= confidence_threshold and len(l1.doc_ids) >= top_k:
                return SearchResult(
                    layer_used="L1",
                    results=[(d, l1.scores.get(d, 0.0)) for d in l1.doc_ids[:top_k]],
                    layers_checked=layers_checked,
                    total_latency_ms=(time.perf_counter() - total_start) * 1000,
                )

        # L2: Recent Memory — RELEVANT NOW (ACT-R scored)
        if max_layers >= 2:
            l2 = self._search_l2(query)
            layers_checked.append("L2")
            if l2.confidence >= confidence_threshold and len(l2.doc_ids) >= top_k:
                return SearchResult(
                    layer_used="L2",
                    results=[(d, l2.scores.get(d, 0.0)) for d in l2.doc_ids[:top_k]],
                    layers_checked=layers_checked,
                    total_latency_ms=(time.perf_counter() - total_start) * 1000,
                )

        # L3: Deep Memory — full BM25 + embeddings + PPR search
        if max_layers >= 3:
            l3 = self._search_l3(query, top_k)
            layers_checked.append("L3")
            return SearchResult(
                layer_used="L3",
                results=[(d, l3.scores.get(d, 0.0)) for d in l3.doc_ids[:top_k]],
                layers_checked=layers_checked,
                total_latency_ms=(time.perf_counter() - total_start) * 1000,
            )

        # Fallback: return whatever we have from the deepest layer checked
        best_layer = layers_checked[-1] if layers_checked else "L0"
        layer_results = {"L0": l0, "L1": l1, "L2": l2, "L3": l3}
        best_result = layer_results.get(best_layer, LayerResult("L0", 0.0, [], {}))
        return SearchResult(
            layer_used=best_layer,
            results=[(d, best_result.scores.get(d, 0.0)) for d in best_result.doc_ids[:top_k]],
            layers_checked=layers_checked,
            total_latency_ms=(time.perf_counter() - total_start) * 1000,
        )

    def _search_l0(self, query: str) -> LayerResult:
        """L0: Identity — match against core project files."""
        import time
        start = time.perf_counter()

        identity_files = {
            "CLAUDE.md": (AES_ROOT / "CLAUDE.md").read_text()
            if (AES_ROOT / "CLAUDE.md").exists() else "",
            "AGENTS.md": (AES_ROOT / "AGENTS.md").read_text()
            if (AES_ROOT / "AGENTS.md").exists() else "",
        }

        # Simple keyword overlap
        query_terms = set(_tokenize(query))
        scores = {}
        for name, text in identity_files.items():
            if not text:
                continue
            doc_terms = set(_tokenize(text))
            overlap = query_terms & doc_terms
            scores[name] = len(overlap) / max(len(query_terms), 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        doc_ids = [d for d, _ in ranked if scores[d] > 0]

        return LayerResult(
            layer="L0",
            confidence=max(scores.values()) if scores else 0.0,
            doc_ids=doc_ids,
            scores=scores,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def _search_l1(self, query: str) -> LayerResult:
        """L1: Working Memory — INDEX.md entries (hot index)."""
        import time
        start = time.perf_counter()

        index_file = AES_ROOT / "aes" / "INDEX.md"
        if not index_file.exists():
            return LayerResult("L1", 0.0, [], {})

        text = index_file.read_text()
        # Parse table rows: | **SD-XXX** ... | GMIF | Score | Synthesis |
        entries = {}
        for line in text.split("\n"):
            if not line.startswith("| **"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue
            doc_id_match = re.search(r'\*\*(SD-[A-Z0-9-]+)\*\*', parts[1])
            if not doc_id_match:
                continue
            doc_id = doc_id_match.group(1)
            synthesis = parts[4] if len(parts) > 4 else ""
            entries[doc_id] = synthesis

        # Keyword overlap
        query_terms = set(_tokenize(query))
        scores = {}
        for doc_id, synthesis in entries.items():
            doc_terms = set(_tokenize(synthesis))
            overlap = query_terms & doc_terms
            scores[doc_id] = len(overlap) / max(len(query_terms), 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        doc_ids = [d for d, _ in ranked if scores[d] > 0]

        return LayerResult(
            layer="L1",
            confidence=max(scores.values()) if scores else 0.0,
            doc_ids=doc_ids,
            scores=scores,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def _search_l2(self, query: str) -> LayerResult:
        """L2: Recent Memory — RELEVANT NOW (top-10 by ACT-R activation)."""
        import time
        start = time.perf_counter()

        from lib.memory.consolidate import SHADOW_DIR, ARCHIVE_DIR, ACCESS_LOG
        from lib.memory.scoring import compute_scores

        scores_data = compute_scores(SHADOW_DIR, ACCESS_LOG)
        if not scores_data:
            return LayerResult("L2", 0.0, [], {})

        # Top-10 by composite score
        ranked = sorted(scores_data.items(), key=lambda x: x[1], reverse=True)[:10]
        doc_ids = [d for d, _ in ranked]
        doc_scores = {d: s for d, s in ranked}

        # Cross-reference with query
        query_terms = set(_tokenize(query))
        relevance_scores = {}

        # Load frontmatter for keyword matching
        from lib.memory.benchmark import load_all_shadow_docs
        fm_docs = load_all_shadow_docs(include_body=False)

        for doc_id in doc_ids:
            if doc_id in fm_docs:
                doc_terms = set(_tokenize(fm_docs[doc_id]))
                overlap = query_terms & doc_terms
                keyword_score = len(overlap) / max(len(query_terms), 1)
                # Blend ACT-R score (activation) with keyword relevance
                relevance_scores[doc_id] = 0.6 * keyword_score + 0.4 * doc_scores.get(doc_id, 0.0)
            else:
                relevance_scores[doc_id] = 0.4 * doc_scores.get(doc_id, 0.0)

        ranked_relevance = sorted(relevance_scores.items(), key=lambda x: x[1], reverse=True)

        return LayerResult(
            layer="L2",
            confidence=max(relevance_scores.values()) if relevance_scores else 0.0,
            doc_ids=[d for d, _ in ranked_relevance],
            scores=relevance_scores,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def _search_l3(self, query: str, top_k: int) -> LayerResult:
        """L3: Deep Memory — full unified search."""
        import time
        start = time.perf_counter()

        from lib.memory.retrieval import unified_search
        results = unified_search(query, top_k=top_k)

        doc_ids = [d for d, _ in results]
        scores = {d: s for d, s in results}

        return LayerResult(
            layer="L3",
            confidence=max(scores.values()) if scores else 0.0,
            doc_ids=doc_ids,
            scores=scores,
            latency_ms=(time.perf_counter() - start) * 1000,
        )


def _tokenize(text: str) -> List[str]:
    """Simple tokenization: lowercase, 3+ char alphabetic tokens."""
    return [t for t in re.findall(r'\b[a-zà-ü]{3,}\b', text.lower())
            if t not in _STOP_WORDS]


_STOP_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "his", "how", "its", "may",
    "new", "now", "old", "see", "way", "who", "did", "get", "let", "say",
    "she", "too", "use", "from", "that", "with", "have", "this", "will",
    "your", "they", "been", "said", "each", "make", "like", "than", "time",
    "very", "when", "come", "could", "what", "there", "their", "about",
    "would", "other", "which", "after", "these", "first", "going", "those",
    "being", "where", "great", "between", "need", "large", "under", "never",
    "each", "same", "tell", "does", "set", "three", "more", "high", "well",
    "also", "back", "work", "year", "live", "home", "land", "just", "over",
    "such", "take", "only", "long", "make", "look", "come", "many", "then",
    "them", "wrote", "found", "give", "most", "us",
    # Portuguese
    "uma", "por", "com", "para", "como", "mas", "dos", "das", "nos", "nas",
    "sem", "sob", "até", "desde", "entre", "sobre", "cada", "todo", "esta",
    "esse", "essa", "isso", "isto", "aquele", "aquela", "muito", "também",
}
