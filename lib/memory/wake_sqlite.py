"""
Fast wake retrieval via SQLite FTS5 (T206).

Replaces BM25 rebuild with direct FTS5 queries when the SQLite index exists.
Falls back to the original BM25 path if aes/index.db is missing.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

AES_ROOT = Path(__file__).resolve().parent.parent.parent
SHADOW_DIR = AES_ROOT / "aes" / "shadow"
ARCHIVE_DIR = SHADOW_DIR / "archive"
INDEX_DB = AES_ROOT / "aes" / "index.db"


@dataclass
class RelevantDoc:
    """A single relevant shadow doc with its score and metadata."""
    doc_id: str
    title: str
    score: float
    in_archive: bool = False
    source: str = "fts"  # "fts", "cascade", "bm25"


def extract_frontmatter(fpath: Path) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    content = fpath.read_text(encoding="utf-8")
    parts = content.split("---")
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def get_relevant_docs_sqlite(
    query: str,
    store,
    top_k: int = 10,
    use_confidence: bool = True,
) -> List[RelevantDoc]:
    """FTS5-based retrieval with optional confidence decay re-ranking.

    1. FTS5 MATCH for seed results
    2. Optional confidence_score() re-ranking
    3. Returns structured RelevantDoc list
    """
    if not query or not query.strip():
        return []

    start = time.time()

    # Step 1: FTS5 seed
    fts_results = store.search_shadow_docs(query, limit=top_k * 2)

    if not fts_results:
        return []

    # Step 2: Build results with optional confidence
    docs = []
    hot_ids = set()
    for f in SHADOW_DIR.glob("*.md"):
        if f.name != "README.md":
            hot_ids.add(f.stem)
    for f in ARCHIVE_DIR.glob("*.md"):
        if f.name != "README.md":
            hot_ids.add(f.stem)

    for r in fts_results:
        doc_id = r["id"]
        title = r.get("title", doc_id)
        fts_score = 1.0  # FTS match is binary — matched or not

        # Step 3: Confidence decay re-rank
        if use_confidence:
            conf = store.confidence_score(doc_id)
            score = conf if conf is not None else fts_score
        else:
            score = fts_score

        in_archive = doc_id not in hot_ids
        docs.append(RelevantDoc(
            doc_id=doc_id,
            title=title,
            score=score,
            in_archive=in_archive,
            source="fts",
        ))

    # Sort by score descending
    docs.sort(key=lambda d: -d.score)

    elapsed_ms = round((time.time() - start) * 1000)

    return docs[:top_k]


def get_relevant_docs_auto(
    ticket_id: Optional[str] = None,
    ticket_text: Optional[str] = None,
    top_k: int = 10,
) -> List[RelevantDoc]:
    """Auto-detect: use SQLite if available, else fall back to BM25.

    This is the main entry point for wake integration.
    """
    # Try SQLite path first
    if INDEX_DB.exists():
        try:
            from lib.storage.sqlite_store import SQLiteGraphStore
            store = SQLiteGraphStore(INDEX_DB)

            query = ticket_text or ""
            if not query and ticket_id:
                # Load ticket text from file
                matches = list(Path("aes/tickets").glob(f"{ticket_id}-*.md"))
                if matches:
                    content = matches[0].read_text()
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            query = parts[2].strip()

            if query:
                results = get_relevant_docs_sqlite(query, store, top_k=top_k)
                store.close()
                return results

            store.close()
        except Exception:
            pass  # fall through to BM25

    # Fallback: BM25 rebuild (original path)
    try:
        from lib.memory.consolidate import get_relevant_docs
        results = get_relevant_docs(ticket_id, ticket_text, top_k)
        return [
            RelevantDoc(
                doc_id=r.doc_id,
                title=r.title,
                score=r.score,
                in_archive=r.in_archive,
                source="bm25",
            )
            for r in results
        ]
    except Exception:
        return []


def cascade_retrieve_wake(
    query: str,
    store,
    max_depth: int = 2,
    top_k: int = 10,
) -> List[RelevantDoc]:
    """BFS expansion from FTS5 seeds to surface connected knowledge.

    1. FTS5 match to find seed nodes
    2. BFS outward collecting connected nodes up to max_depth hops
    3. Results include distance field (0=direct FTS hit, 1=one hop, etc.)
    4. De-duplicated: if a node appears via FTS and BFS, keep FTS score
    """
    if not query or not query.strip():
        return []

    # Step 1: FTS seeds
    fts_results = store.search_shadow_docs(query, limit=top_k)
    if not fts_results:
        return []

    # Build initial results from FTS hits
    seen = {}
    results = []
    hot_ids = set()
    for f in SHADOW_DIR.glob("*.md"):
        if f.name != "README.md":
            hot_ids.add(f.stem)
    for f in ARCHIVE_DIR.glob("*.md"):
        if f.name != "README.md":
            hot_ids.add(f.stem)

    for r in fts_results:
        nid = r["id"]
        seen[nid] = 0
        conf = store.confidence_score(nid)
        results.append(RelevantDoc(
            doc_id=nid,
            title=r.get("title", nid),
            score=conf if conf is not None else 1.0,
            in_archive=nid not in hot_ids,
            source="fts",
        ))

    # Step 2: BFS expansion
    queue = [(nid, 0) for nid in seen]
    for nid, depth in queue:
        if depth >= max_depth:
            continue
        neighbors = store.get_neighbors(nid)
        for neighbor in neighbors:
            if neighbor.id not in seen:
                seen[neighbor.id] = depth + 1
                queue.append((neighbor.id, depth + 1))
                conf = store.confidence_score(neighbor.id)
                results.append(RelevantDoc(
                    doc_id=neighbor.id,
                    title=neighbor.label,
                    score=(conf if conf is not None else 0.5) * (0.8 ** (depth + 1)),
                    in_archive=neighbor.id not in hot_ids,
                    source="cascade",
                ))

    # Sort by score descending (FTS hits should rank higher due to no decay)
    results.sort(key=lambda d: -d.score)
    return results[:top_k]
