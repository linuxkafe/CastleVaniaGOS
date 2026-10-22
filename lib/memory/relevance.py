"""
BM25 Lexical Relevance — Pure Python Implementation

Retrieval-time relevance scoring using BM25 (Best Matching 25).
Pure Python, no external dependencies. Based on Robertson & Zaragoza 2009.

Reference: Robertson, S., & Zaragoza, H. (2009). The Probabilistic Relevance
Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from .scoring import compute_scores


@dataclass
class BM25Config:
    """BM25 hyperparameters."""
    k1: float = 1.5      # Term frequency saturation
    b: float = 0.75      # Length normalization (0 = no norm, 1 = full)
    k3: float = 0.0      # Query term frequency saturation (0 = no saturation)


def tokenize(text: str) -> List[str]:
    """Simple tokenization: lowercase, alphanumeric only."""
    return re.findall(r'\b\w+\b', text.lower())


class BM25Index:
    """
    BM25 index for lexical relevance scoring.
    
    Builds inverted index from document collection, supports BM25 scoring
    against arbitrary queries. Pure Python, no external dependencies.
    """
    
    def __init__(
        self,
        documents: Dict[str, str],  # doc_id -> text
        config: Optional[BM25Config] = None,
    ):
        self.config = config or BM25Config()
        self.documents = documents
        self.doc_ids = list(documents.keys())
        self.N = len(documents)
        
        # Build index
        self.doc_tokens: Dict[str, List[str]] = {}
        self.doc_freqs: Dict[str, Counter] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.avgdl: float = 0.0
        self.term_df: Dict[str, int] = defaultdict(int)
        self.idf: Dict[str, float] = {}
        
        self._build_index()
    
    def _build_index(self) -> None:
        total_length = 0
        for doc_id, text in self.documents.items():
            tokens = tokenize(text)
            self.doc_tokens[doc_id] = tokens
            freqs = Counter(tokens)
            self.doc_freqs[doc_id] = freqs
            length = len(tokens)
            self.doc_lengths[doc_id] = length
            total_length += length
            
            # Document frequency per term
            for term in set(tokens):
                self.term_df[term] += 1
        
        self.avgdl = total_length / self.N if self.N > 0 else 0
        
        # Precompute IDF
        for term, df in self.term_df.items():
            # BM25 IDF: log((N - df + 0.5) / (df + 0.5) + 1) to ensure positive
            self.idf[term] = math.log(1 + (self.N - df + 0.5) / (df + 0.5))
    
    def score(self, query: str, doc_id: str) -> float:
        """
        Compute BM25 score for a single document.
        
        score = sum_{q in query} IDF(q) * ((f * (k1 + 1)) / (f + k1 * (1 - b + b * |D|/avgdl)))
        """
        if doc_id not in self.documents:
            return 0.0
        
        query_terms = tokenize(query)
        freqs = self.doc_freqs[doc_id]
        dl = self.doc_lengths[doc_id]
        
        score = 0.0
        k1 = self.config.k1
        b = self.config.b
        avgdl = self.avgdl
        
        for term in query_terms:
            if term not in self.idf:
                continue
            
            idf = self.idf[term]
            tf = freqs.get(term, 0)
            
            if tf == 0:
                continue
            
            # BM25 formula
            numerator = tf * (self.config.k1 + 1)
            denominator = tf + self.config.k1 * (1 - self.config.b + self.config.b * (self.doc_lengths[doc_id] / self.avgdl))
            score += idf * (numerator / denominator)
        
        return score
    
    def rank(self, query: str, top_k: Optional[int] = None) -> List[tuple]:
        """
        Rank all documents by BM25 score for a query.
        
        Returns list of (doc_id, score) sorted descending by score.
        """
        if top_k is None:
            top_k = self.N
        
        scores = []
        for doc_id in self.doc_ids:
            score = self.score(query, doc_id)
            if score > 0:
                scores.append((doc_id, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def bm25_search(
    query: str,
    documents: Dict[str, str],
    config: Optional[BM25Config] = None,
    top_k: Optional[int] = None,
) -> List[tuple]:
    """
    Convenience function: build index, search, return ranked results.
    
    Args:
        query: Search query string
        documents: {doc_id: text} mapping
        config: BM25Config (optional)
        top_k: Number of results to return (None = all)
    
    Returns:
        List of (doc_id, score) sorted by score descending
    """
    index = BM25Index(documents, config)
    return index.rank(query, top_k)


def bm25_search_reranked(
    query: str,
    documents: Dict[str, str],
    shadow_dir: Optional[Path] = None,
    access_log_path: Optional[Path] = None,
    config: Optional[BM25Config] = None,
    top_k: int = 10,
    bm25_weight: float = 0.7,
    activation_weight: float = 0.3,
) -> List[tuple]:
    """
    BM25 search reranked by ACT-R activation score.

    Blends lexical relevance (BM25) with memory activation (ACT-R) to produce
    results that are both topically relevant and recently accessed.

    Args:
        query: Search query string
        documents: {doc_id: text} mapping
        shadow_dir: Path to shadow docs (for compute_scores)
        access_log_path: Path to access.log (for compute_scores)
        config: BM25Config (optional)
        top_k: Number of results to return
        bm25_weight: Weight for BM25 score component (default 0.7)
        activation_weight: Weight for ACT-R activation component (default 0.3)

    Returns:
        List of (doc_id, blended_score) sorted by blended score descending
    """
    from pathlib import Path as _Path

    # Step 1: BM25 retrieval
    bm25_results = bm25_search(query, documents, config, top_k=top_k * 3)
    if not bm25_results:
        return []

    # Step 2: Get activation scores
    sdir = shadow_dir or _Path("aes/shadow")
    alog = access_log_path or _Path("aes/shadow/access.log")
    try:
        activation_scores = compute_scores(sdir, alog)
    except Exception:
        activation_scores = {}

    # Step 3: Normalize BM25 scores to [0, 1]
    bm25_max = max((s for _, s in bm25_results), default=1.0)
    bm25_norm = {doc_id: score / bm25_max if bm25_max > 0 else 0.0
                  for doc_id, score in bm25_results}

    # Step 4: Normalize activation scores to [0, 1]
    act_vals = [activation_scores.get(d, 0.0) for d in bm25_norm]
    act_max = max(act_vals) if act_vals else 1.0
    act_norm = {d: activation_scores.get(d, 0.0) / act_max if act_max > 0 else 0.0
                for d in bm25_norm}

    # Step 5: Blend
    blended = {}
    for doc_id in bm25_norm:
        blended[doc_id] = (bm25_weight * bm25_norm[doc_id] +
                           activation_weight * act_norm.get(doc_id, 0.0))

    ranked = sorted(blended.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]