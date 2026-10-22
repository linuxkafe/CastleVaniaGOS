"""
Cold-layer retrieval: PPR (Personalized PageRank) over premise+shadow graph.

Implements two contenders for T052:
(b) PPR over premise+shadow graph (power iteration)
(c) Hybrid BM25 seeds -> PPR expansion

References:
  - PageRank: Page et al. (1999) "The PageRank Citation Ranking"
  - Personalized PageRank: Haveliwala (2002) "Topic-Sensitive PageRank"
  - HippoRAG: Gutierrez et al. (2024) "HippoRAG: Memory-Augmented Retrieval"
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Callable

AES_ROOT = Path(__file__).resolve().parent.parent.parent

_STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "all", "am", "an", "and", "any",
    "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "just", "ll", "me", "might", "more", "most", "my",
    "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only",
    "or", "other", "our", "ours", "ourselves", "out", "over", "own", "per",
    "que", "s", "same", "she", "should", "so", "some", "such", "t", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "would", "you",
    "your", "yours", "yourself", "yourselves",
    # Portuguese stopwords
    "a", "ao", "aos", "aquela", "aquelas", "aquele", "aqueles", "aquilo",
    "as", "até", "com", "como", "da", "das", "de", "dela", "delas", "dele",
    "deles", "depois", "do", "dos", "e", "ela", "elas", "ele", "eles",
    "em", "entre", "era", "eram", "essa", "essas", "esse", "esses", "esta",
    "estas", "este", "estes", "eu", "foi", "foram", "há", "isso", "isto",
    "já", "lhe", "lhes", "mais", "mas", "me", "mesmo", "na", "nas", "nem",
    "no", "nos", "nós", "num", "numa", "o", "os", "ou", "para", "pela",
    "pelas", "pelo", "pelos", "por", "qual", "quando", "que", "se", "sem",
    "são", "seu", "seus", "sua", "suas", "também", "te", "tem", "têm",
    "teu", "teus", "tu", "tuas", "um", "uma", "você", "vocês",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase tokenization, keep only 3+ char alphabetic tokens."""
    tokens = re.findall(r'\b[a-zà-ü]{3,}\b', text.lower())
    return [t for t in tokens if t not in _STOP_WORDS]


def build_shadow_graph(
    shadow_dir: Optional[Path] = None,
    min_shared_terms: int = 2,
) -> Dict[str, Set[str]]:
    """
    Build an undirected graph connecting shadow docs by lexical + structural
    similarity.

    Graph construction:
    - Nodes: shadow doc IDs
    - Edges:
      1. Lexical: two docs share >= min_shared_terms significant terms
      2. Epistemic state: two docs share the same epistemic_state
      3. Source ticket: two docs share the same provenance.source_ticket

    Returns adjacency dict: {node_id: {neighbor_id, ...}}
    """
    sdir = shadow_dir or AES_ROOT / "aes" / "shadow"
    adir = sdir / "archive"

    # Load all shadow docs' metadata
    doc_terms: Dict[str, Set[str]] = {}
    doc_state: Dict[str, str] = {}
    doc_ticket: Dict[str, str] = {}

    for directory in [sdir, adir]:
        for fpath in sorted(directory.glob("*.md")):
            if fpath.name in ("README.md", ".gitkeep"):
                continue
            content = fpath.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            try:
                import yaml
                fm = yaml.safe_load(parts[1])
                synthesis = fm.get("synthesis", "")
                body = parts[2].strip()
                text_for_terms = f"{synthesis}\n{body}" if body else synthesis
                terms = set(_tokenize(text_for_terms))
                doc_terms[fpath.stem] = terms
                state = fm.get("epistemic_state", "")
                if state:
                    doc_state[fpath.stem] = state
                prov = fm.get("provenance", {}) or {}
                ticket = prov.get("source_ticket", "")
                if ticket:
                    doc_ticket[fpath.stem] = ticket
            except:
                pass

    adj: Dict[str, Set[str]] = defaultdict(set)
    doc_ids = list(doc_terms.keys())

    for i in range(len(doc_ids)):
        for j in range(i + 1, len(doc_ids)):
            di, dj = doc_ids[i], doc_ids[j]

            # 1. Lexical similarity
            shared = doc_terms[di] & doc_terms[dj]
            if len(shared) >= min_shared_terms:
                adj[di].add(dj)
                adj[dj].add(di)

            # 2. Epistemic state (same state → edge)
            if di in doc_state and dj in doc_state:
                if doc_state[di] == doc_state[dj]:
                    adj[di].add(dj)
                    adj[dj].add(di)

            # 3. Source ticket (same ticket → edge)
            if di in doc_ticket and dj in doc_ticket:
                if doc_ticket[di] == doc_ticket[dj]:
                    adj[di].add(dj)
                    adj[dj].add(di)

    return dict(adj)


def power_iteration(
    adj: Dict[str, Set[str]],
    seed_weights: Dict[str, float],
    alpha: float = 0.85,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> Dict[str, float]:
    """
    Personalized PageRank via power iteration.

    Args:
        adj: Adjacency dict {node_id: {neighbor_id, ...}}
        seed_weights: {node_id: weight} — the personalization vector
        alpha: Damping factor (teleport probability)
        max_iter: Maximum power iterations
        tol: Convergence tolerance

    Returns:
        {node_id: ppr_score} — converged PageRank scores

    Reference: Haveliwala (2002) Eq. 2
    """
    nodes = list(adj.keys())
    if not nodes:
        return {}

    n = len(nodes)
    node_index = {node: i for i, node in enumerate(nodes)}

    # Build transition matrix column-stochastic
    # For each node, outgoing probability = 1/degree
    out_degree = {node: len(neighbors) for node, neighbors in adj.items()}

    # Normalize seed weights to sum to 1
    total_seed = sum(seed_weights.values())
    if total_seed == 0:
        p = {node: 1.0 / n for node in nodes}
    else:
        p = {node: seed_weights.get(node, 0.0) / total_seed for node in nodes}

    # Initialize rank vector: uniform
    r = {node: 1.0 / n for node in nodes}

    for iteration in range(max_iter):
        r_new = {}
        for node in nodes:
            # Teleport component
            teleport = (1 - alpha) * p[node]

            # Follow-links component: sum of incoming PageRank / out-degree
            link_sum = 0.0
            for neighbor in adj.get(node, set()):
                link_sum += r[neighbor] / max(out_degree[neighbor], 1)

            r_new[node] = teleport + alpha * link_sum

        # Check convergence
        diff = sum(abs(r_new[node] - r[node]) for node in nodes)
        r = r_new
        if diff < tol:
            break

    return r


def _bm25_confidence(bm25_results: List[Tuple[str, float]]) -> float:
    """Estimate BM25 confidence from score distribution.

    Returns a value in [0, 1] where:
      - 0 = flat scores or all-zero (no confidence, PPR should dominate)
      - 1 = sharp peak (high confidence, BM25 should dominate)

    Uses two signals:
      1. Coefficient of variation (CV): low CV = flat = low confidence
      2. Score gap: small gap between #1 and #2 = low confidence
    """
    if len(bm25_results) < 2:
        return 0.5

    scores = [s for _, s in bm25_results if s > 0]
    if not scores:
        return 0.0

    # Signal 1: coefficient of variation
    mean = sum(scores) / len(scores)
    if mean == 0:
        return 0.0
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std = variance ** 0.5
    cv = std / mean
    cv_conf = max(0.0, min(1.0, 1.0 - cv / 2.0))

    # Signal 2: normalized gap between top-2 scores
    sorted_scores = sorted(scores, reverse=True)
    if len(sorted_scores) >= 2 and sorted_scores[0] > 0:
        gap = (sorted_scores[0] - sorted_scores[1]) / sorted_scores[0]
    else:
        gap = 0.0
    gap_conf = gap  # gap=1 → only one match → high conf; gap=0 → tied → low conf

    # Combine: both signals must agree for high confidence
    return cv_conf * gap_conf


def hybrid_bm25_ppr(
    query: str,
    bm25_search_fn: Callable,
    shadow_docs: Dict[str, str],
    adj: Dict[str, Set[str]],
    top_k_bm25: int = 20,
    alpha: float = 0.85,
    final_k: int = 10,
) -> List[Tuple[str, float]]:
    """
    Hybrid BM25 → PPR with adaptive weighting.

    When BM25 is confident (sharp score peak), trust BM25 more.
    When BM25 is uncertain (flat scores), trust PPR more.

    Args:
        query: Search query
        bm25_search_fn: BM25 search function (query, documents, top_k) -> list
        shadow_docs: {doc_id: text} mapping
        adj: Full graph adjacency
        top_k_bm25: How many BM25 results to use as PPR seeds
        alpha: PPR damping factor
        final_k: How many results to return

    Returns:
        [(doc_id, score)] ranked by hybrid relevance
    """
    # Step 1: BM25 search
    bm25_results = bm25_search_fn(query, shadow_docs, top_k=top_k_bm25)
    if not bm25_results:
        return []

    # Step 2: Estimate BM25 confidence
    conf = _bm25_confidence(bm25_results)

    # Step 3: Binary seeding — equal weight for all BM25 results
    # (score-weighted seeding lets wrong BM25 results dominate)
    seed_nodes = [doc_id for doc_id, _ in bm25_results if doc_id in adj]
    if not seed_nodes:
        return bm25_results[:final_k]

    seed_weights = {node: 1.0 for node in seed_nodes}

    # Step 4: Build subgraph from seed nodes + their neighbors
    subgraph_nodes = set(seed_weights.keys())
    for node in seed_nodes:
        if node in adj:
            subgraph_nodes.update(adj[node])

    subgraph_adj = {
        node: adj.get(node, set()) & subgraph_nodes
        for node in subgraph_nodes
    }

    # Step 5: Run PPR on subgraph with binary seeds
    ppr_scores = power_iteration(subgraph_adj, seed_weights, alpha=alpha)

    # Step 6: Adaptive combination
    # conf=1 → w_bm25=0.6, w_ppr=0.4 (trust BM25 somewhat)
    # conf=0 → w_bm25=0.1, w_ppr=0.9 (trust PPR heavily)
    w_bm25 = 0.1 + 0.5 * conf
    w_ppr = 1.0 - w_bm25

    # Normalize each score set to [0, 1]
    bm25_only = {doc_id: score for doc_id, score in bm25_results}
    bm25_vals = [bm25_only.get(d, 0.0) for d in subgraph_nodes]
    ppr_vals = [ppr_scores.get(d, 0.0) for d in subgraph_nodes]
    bm25_max = max(bm25_vals) if bm25_vals else 1.0
    ppr_max = max(ppr_vals) if ppr_vals else 1.0

    combined = {}
    for doc_id in subgraph_nodes:
        bm25_norm = bm25_only.get(doc_id, 0.0) / bm25_max if bm25_max > 0 else 0.0
        ppr_norm = ppr_scores.get(doc_id, 0.0) / ppr_max if ppr_max > 0 else 0.0
        combined[doc_id] = w_bm25 * bm25_norm + w_ppr * ppr_norm

    sorted_results = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    return sorted_results[:final_k]
