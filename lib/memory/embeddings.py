"""
Semantic embedding search for shadow documents.

Uses ChromaDB's ONNX MiniLM-L6-V2 (384-dim, local, no API calls).
Provides the same interface as bm25_search for easy swapping.

Usage:
    from lib.memory.embeddings import embedding_search
    results = embedding_search("my query", documents, top_k=10)
    # results = [("doc_id", score), ...]
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    _HAS_EMBEDDINGS = True
except ImportError:
    _HAS_EMBEDDINGS = False

AES_ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_DIR = AES_ROOT / "aes" / "embeddings"
EMBEDDING_CACHE = INDEX_DIR / "shadow_docs.npy"
ID_MAP_CACHE = INDEX_DIR / "id_map.json"
MODEL_CACHE_DIR = INDEX_DIR / "model"

# Lazy-loaded embedding function
_ef = None


def _get_embedding_fn():
    """Get or initialize the ONNX embedding function."""
    global _ef
    if _ef is None:
        if not _HAS_EMBEDDINGS:
            raise ImportError(
                "chromadb not installed. "
                "Install with: pip install chromadb"
            )
        _ef = ONNXMiniLM_L6_V2()
    return _ef


def _embed_texts(texts: List[str]) -> np.ndarray:
    """Embed a list of texts, return (n, 384) numpy array."""
    ef = _get_embedding_fn()
    embeddings = ef(texts)
    return np.array(embeddings, dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def build_index(
    documents: Dict[str, str],
    force_rebuild: bool = False,
    frontmatter_only: bool = True,
) -> Tuple[np.ndarray, List[str]]:
    """Build embedding index from shadow documents.

    Args:
        documents: {doc_id: full_text} or {doc_id: frontmatter_only_text}
        force_rebuild: If True, rebuild even if cache exists
        frontmatter_only: If True, strip body content from texts before embedding
                          (English titles only — avoids Portuguese dilution)

    Returns:
        (embeddings_array, doc_ids) where embeddings_array is (n, 384)
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # Check cache
    if not force_rebuild and EMBEDDING_CACHE.exists() and ID_MAP_CACHE.exists():
        embeddings = np.load(EMBEDDING_CACHE)
        with open(ID_MAP_CACHE) as f:
            cached_ids = json.load(f)
        if set(cached_ids) == set(documents.keys()):
            return embeddings, cached_ids

    # Build index
    doc_ids = sorted(documents.keys())
    texts = [_strip_body(documents[did]) if frontmatter_only else documents[did]
             for did in doc_ids]

    print(f"  Embedding {len(texts)} documents (frontmatter_only={frontmatter_only})...")
    start = time.perf_counter()
    embeddings = _embed_texts(texts)
    elapsed = time.perf_counter() - start
    print(f"  Embedded in {elapsed:.2f}s")

    # Cache
    np.save(EMBEDDING_CACHE, embeddings)
    with open(ID_MAP_CACHE, "w") as f:
        json.dump(doc_ids, f)

    return embeddings, doc_ids


def _strip_body(text: str) -> str:
    """Strip body content from shadow doc text, keep frontmatter only.

    Shadow docs have format: 'title\\nsynthesis\\n\\nBody content...'
    We keep everything before the first double-newline.
    """
    parts = text.split("\n\n", 1)
    return parts[0] if len(parts) > 1 else text


def embedding_search(
    query: str,
    documents: Dict[str, str],
    top_k: int = 10,
    force_rebuild: bool = False,
) -> List[Tuple[str, float]]:
    """Semantic search via embedding cosine similarity.

    Same interface as bm25_search in relevance.py.

    Args:
        query: Search query
        documents: {doc_id: "title\nsynthesis\nbody"}
        top_k: Number of results to return
        force_rebuild: Force index rebuild

    Returns:
        [(doc_id, score)] sorted by similarity descending
    """
    if not documents:
        return []

    # Build/load index
    embeddings, doc_ids = build_index(documents, force_rebuild=force_rebuild)

    # Embed query
    query_emb = _embed_texts([query])[0]

    # Cosine similarity against all docs
    scores = []
    for i, doc_id in enumerate(doc_ids):
        sim = _cosine_similarity(query_emb, embeddings[i])
        scores.append((doc_id, sim))

    # Sort descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def get_embedding_dim() -> int:
    """Return the embedding dimension."""
    return 384
