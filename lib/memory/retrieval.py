"""
Unified hybrid retrieval: BM25 + Embeddings + PPR.

Combines three signals with adaptive weighting:
  1. BM25 — lexical match on English frontmatter titles
  2. Embeddings — semantic similarity via ONNX MiniLM (384-dim)
  3. PPR — graph-based relevance from shadow doc relationships

Weighting strategy:
  - BM25 confidence drives how much to trust lexical vs graph signals
  - Embeddings provide a language-bridge signal (English queries → mixed corpus)
  - PPR catches documents that are topically related but lexically distant

References:
  - Robertson & Zaragoza 2009 (BM25)
  - Reimers & Gurevych 2019 (Sentence-BERT)
  - Page et al. 1999 (PageRank)

Usage:
    from lib.memory.retrieval import unified_search
    results = unified_search("my query", top_k=10)
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple

from .relevance import bm25_search
from .embeddings import embedding_search
from ..epistemic.cold_retrieval import (
    _bm25_confidence,
    build_shadow_graph,
    power_iteration,
)


def unified_search(
    query: str,
    shadow_docs: Optional[Dict[str, str]] = None,
    adj: Optional[Dict[str, Set[str]]] = None,
    bm25_docs: Optional[Dict[str, str]] = None,
    embed_docs: Optional[Dict[str, str]] = None,
    top_k: int = 10,
    top_k_bm25: int = 20,
    alpha: float = 0.85,
) -> List[Tuple[str, float]]:
    """
    Unified hybrid retrieval: BM25 + Embeddings + PPR.

    Args:
        query: Search query
        shadow_docs: Full shadow docs (title+synthesis+body) for PPR graph
        adj: Graph adjacency dict (auto-built if None)
        bm25_docs: Frontmatter-only docs for BM25 (auto-loaded if None)
        embed_docs: Frontmatter-only docs for embeddings (auto-loaded if None)
        top_k: Number of results to return
        top_k_bm25: How many BM25 results to seed PPR
        alpha: PPR damping factor

    Returns:
        [(doc_id, score)] ranked by unified relevance
    """
    # Lazy-load documents
    if shadow_docs is None or bm25_docs is None or embed_docs is None:
        from .benchmark import load_all_shadow_docs
        shadow_docs = shadow_docs or load_all_shadow_docs(include_body=True)
        bm25_docs = bm25_docs or load_all_shadow_docs(include_body=False)
        embed_docs = embed_docs or bm25_docs  # same frontmatter-only

    if adj is None:
        adj = build_shadow_graph()  # no args — reads aes/shadow/ directly

    # Step 1: BM25 (lexical, frontmatter-only)
    bm25_results = bm25_search(query, bm25_docs, top_k=top_k_bm25)
    bm25_conf = _bm25_confidence(bm25_results)

    # Step 2: Embeddings (semantic, frontmatter-only)
    embed_results = embedding_search(query, embed_docs, top_k=top_k_bm25)

    # Step 3: PPR (graph, full body content for edges)
    seed_nodes = [doc_id for doc_id, _ in bm25_results if doc_id in adj]
    if seed_nodes:
        seed_weights = {node: 1.0 for node in seed_nodes}
        subgraph_nodes = set(seed_weights.keys())
        for node in seed_nodes:
            if node in adj:
                subgraph_nodes.update(adj[node])
        subgraph_adj = {
            node: adj.get(node, set()) & subgraph_nodes
            for node in subgraph_nodes
        }
        ppr_scores = power_iteration(subgraph_adj, seed_weights, alpha=alpha)
    else:
        ppr_scores = {}

    # Step 4: Score normalization to [0, 1]
    all_candidates = set()
    all_candidates.update(d for d, _ in bm25_results)
    all_candidates.update(d for d, _ in embed_results)
    all_candidates.update(ppr_scores.keys())

    bm25_dict = {d: s for d, s in bm25_results}
    embed_dict = {d: s for d, s in embed_results}

    bm25_max = max((bm25_dict.get(d, 0.0) for d in all_candidates), default=1.0)
    embed_max = max((embed_dict.get(d, 0.0) for d in all_candidates), default=1.0)
    ppr_max = max((ppr_scores.get(d, 0.0) for d in all_candidates), default=1.0)

    # Step 5: Adaptive weighting
    # BM25 confidence controls lexical vs graph balance
    # Embeddings get a fixed moderate weight (language bridge)
    w_lexical = 0.1 + 0.4 * bm25_conf   # 0.1–0.5
    w_embed = 0.2                          # fixed bridge signal
    w_graph = 1.0 - w_lexical - w_embed    # 0.3–0.9

    # Step 6: Combine
    combined = {}
    for doc_id in all_candidates:
        bm25_norm = bm25_dict.get(doc_id, 0.0) / bm25_max if bm25_max > 0 else 0.0
        embed_norm = embed_dict.get(doc_id, 0.0) / embed_max if embed_max > 0 else 0.0
        ppr_norm = ppr_scores.get(doc_id, 0.0) / ppr_max if ppr_max > 0 else 0.0
        combined[doc_id] = w_lexical * bm25_norm + w_embed * embed_norm + w_graph * ppr_norm

    sorted_results = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return sorted_results[:top_k]


def search(query: str, top_k: int = 10) -> List[Tuple[str, float]]:
    """Simple interface for the unified search."""
    return unified_search(query, top_k=top_k)
