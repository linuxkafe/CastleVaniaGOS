"""
Sleep/wake: governed consolidation (T039).

Sleep = batch job that re-scores, merges redundant shadow docs, promotes
risers, demotes fallers to archive. Wake = load INDEX.md into working context.

HARD CONSTRAINT: demotion is a GOVERNED epistemic event. A shadow doc
supporting promoted (SUPORTADA) claims cannot silently leave the hot index.
"""

import shutil
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from lib.epistemic.loop_closure import (
    OpenLoop,
    LoopStatus,
    LoopCriticality,
    generate_loop_id,
)

from lib.epistemic.epistemic_objects import (
    ClosureRecord,
)

from lib.memory.scoring import (
    CONFIG,
    compute_activation,
    compute_centrality,
    composite_score,
    parse_access_log,
    compute_scores,
)

AES_ROOT = Path(__file__).resolve().parent.parent.parent
SHADOW_DIR = AES_ROOT / "aes" / "shadow"
ARCHIVE_DIR = SHADOW_DIR / "archive"
ACCESS_LOG = AES_ROOT / "aes" / "shadow" / "access.log"
PREMISES_DIR = AES_ROOT / "aes" / "premises"
INDEX_FILE = AES_ROOT / "aes" / "INDEX.md"
TEMPORAL_BLEND_WEIGHT = 0.15

DEMOTION_THRESHOLD = float(
    __import__("os").environ.get("AES_DEMOTION_THRESHOLD", "0.2")
)


@dataclass
class DemotionEvent:
    shadow_id: str
    title: str
    old_score: float
    reason: str
    loop_opened: Optional[str] = None


@dataclass
class MergeEvent:
    target_id: str
    source_ids: List[str]
    reason: str


@dataclass
class SleepReport:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    demoted: List[DemotionEvent] = field(default_factory=list)
    merged: List[MergeEvent] = field(default_factory=list)
    score_summary: Dict[str, float] = field(default_factory=dict)
    total_hot: int = 0
    total_archive: int = 0
    blocked_demotions: int = 0
    pinned_unused: List[str] = field(default_factory=list)
    used_low_score: List[str] = field(default_factory=list)
    score_trajectory: Dict[str, List[float]] = field(default_factory=dict)
    stale_docs: List[str] = field(default_factory=list)
    temporal_decays: Dict[str, float] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class InsightRelevance:
    """A single shadow doc insight relevant to the current ticket."""
    doc_id: str
    title: str
    synthesis: str
    relevance_score: float
    epistemic_state: str
    gmif: str = ""
    is_stale: bool = False
    premise_failures: List[str] = field(default_factory=list)


@dataclass
class ExecutionContext:
    """
    Structured output from wake() — not a string, but actionable data.

    Use .format() for CLI output.
    """
    ticket_id: Optional[str] = None
    sprint: str = "unknown"
    relevant_insights: List[InsightRelevance] = field(default_factory=list)
    stale_warnings: List[str] = field(default_factory=list)
    premise_failures: Dict[str, List[str]] = field(default_factory=dict)
    open_loops: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    # Graph governance (T199)
    graph_lint_issues: Dict[str, int] = field(default_factory=dict)  # code -> count
    gmif_classifications: Dict[str, str] = field(default_factory=dict)  # doc_id -> level
    governance_decisions: Dict[str, str] = field(default_factory=dict)  # doc_id -> decision

    def format(self) -> str:
        """Format for CLI output — human-readable, not machine-readable."""
        parts = []
        parts.append("=" * 60)
        parts.append("  ACORDAR — AES Context Load")
        parts.append("=" * 60)
        parts.append("")

        parts.append(f"Ticket: {self.ticket_id or 'none'}  |  Sprint: {self.sprint}")
        parts.append("")

        # Relevant insights (the core value)
        if self.relevant_insights:
            parts.append(f"── RELEVANT INSIGHTS ({len(self.relevant_insights)}) ──")
            for ins in self.relevant_insights:
                stale_flag = " [STALE]" if ins.is_stale else ""
                parts.append(f"  {ins.doc_id} — {ins.title} (relevance: {ins.relevance_score:.2f}){stale_flag}")
                if ins.synthesis:
                    parts.append(f"    {ins.synthesis[:120]}...")
                if ins.premise_failures:
                    parts.append(f"    Premise failures: {', '.join(ins.premise_failures)}")
            parts.append("")

        # Stale warnings
        if self.stale_warnings:
            parts.append(f"── STALE WARNINGS ({len(self.stale_warnings)}) ──")
            for w in self.stale_warnings:
                parts.append(f"  ⚠ {w}")
            parts.append("")

        # Open loops
        if self.open_loops:
            parts.append(f"── OPEN HIGH LOOPS ({len(self.open_loops)}) ──")
            for loop in self.open_loops:
                parts.append(f"  • {loop}")
            parts.append("")

        # Actions
        if self.actions:
            parts.append("── SUGGESTED ACTIONS ──")
            for a in self.actions:
                parts.append(f"  → {a}")
            parts.append("")

        parts.append("=" * 60)
        return "\n".join(parts)


def extract_frontmatter(path: Path) -> dict:
    content = path.read_text()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def write_frontmatter(path: Path, frontmatter: dict, body: str) -> None:
    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
    path.write_text(f"---\n{fm_str}\n---\n{body}")


def find_duplicates(
    shadow_dir: Path,
) -> List[Tuple[str, str, str]]:
    """
    Find near-duplicate shadow docs.

    Returns list of (target_id, source_id, reason) where source should merge
    into target. Heuristic: explicit duplicate-of field or same pointer.path.
    """
    docs: Dict[str, dict] = {}
    merges: List[Tuple[str, str, str]] = []

    for fpath in sorted(shadow_dir.glob("*.md")):
        if fpath.name == "README.md":
            continue
        fm = extract_frontmatter(fpath)
        sid = fm.get("id", fpath.stem)
        docs[sid] = {"fm": fm, "path": fpath}

    # Pass 1: explicit duplicate-of
    for sid, info in docs.items():
        dup_of = info["fm"].get("duplicate-of")
        if dup_of and dup_of in docs:
            merges.append((dup_of, sid, f"explicit duplicate-of: {sid} → {dup_of}"))

    # Pass 2: same pointer.path
    seen_ptrs: Dict[str, str] = {}
    for sid, info in docs.items():
        ptr = info["fm"].get("pointer", {}).get("path", "")
        if not ptr:
            continue
        if ptr in seen_ptrs and seen_ptrs[ptr] != sid:
            merges.append((seen_ptrs[ptr], sid, f"same pointer.path: {ptr}"))
        else:
            seen_ptrs[ptr] = sid

    # Pass 3: semantic dedup via BM25 cross-similarity
    try:
        from .relevance import bm25_search
        already_merged = {s for _, s, _ in merges}
        doc_texts = {}
        for sid, info in docs.items():
            if sid in already_merged:
                continue
            fm = info["fm"]
            title = fm.get("title", sid)
            synthesis = fm.get("synthesis", "")
            text = f"{title}\n{synthesis}"
            # Only consider docs with substantial content for semantic dedup
            if len(text.split()) >= 10:
                doc_texts[sid] = text

        for sid in list(doc_texts.keys()):
            if sid in already_merged:
                continue
            query_text = doc_texts[sid]
            # Self-match score = BM25(query, query) — max possible for this doc
            self_results = bm25_search(query_text, {sid: query_text}, top_k=1)
            self_score = self_results[0][1] if self_results else 1.0
            results = bm25_search(query_text, doc_texts, top_k=3)
            for other_id, score in results:
                if other_id == sid or other_id in already_merged:
                    continue
                # Normalize by self-match: ratio > 0.90 means near-duplicate
                norm = score / self_score if self_score > 0 else 0.0
                if norm > 0.90:
                    merges.append((sid, other_id, f"semantic dedup norm={norm:.2f}"))
                    already_merged.add(other_id)
                    break
    except (ImportError, Exception):
        pass  # semantic dedup optional

    return merges


def merge_shadow_docs(
    target_id: str,
    source_ids: List[str],
    shadow_dir: Path,
) -> str:
    """
    Merge source docs into target. Fuse provenance and append synthesis.
    Returns description of what was merged.
    """
    target_path = shadow_dir / f"{target_id}.md"
    if not target_path.exists():
        target_path = next(shadow_dir.glob(f"{target_id}*"), None)
    if not target_path:
        # Try finding by id in frontmatter
        for fp in sorted(shadow_dir.glob("*.md")):
            if fp.name == "README.md":
                continue
            fm = extract_frontmatter(fp)
            if fm.get("id") == target_id:
                target_path = fp
                break
    if not target_path:
        return f"MERGE FAILED: target {target_id} not found"

    target_fm = extract_frontmatter(target_path)
    target_body = target_path.read_text().split("---", 2)[-1] if "---" in target_path.read_text() else target_path.read_text()

    merged_sources = target_fm.get("provenance", {}).get("merged_from", [])
    merged_descriptions = []

    for src_id in source_ids:
        src_path = shadow_dir / f"{src_id}.md"
        if not src_path.exists():
            src_path = next(shadow_dir.glob(f"{src_id}*"), None)
        if not src_path:
            merged_descriptions.append(f"{src_id}: not found")
            continue

        src_fm = extract_frontmatter(src_path)
        src_body = src_path.read_text().split("---", 2)[-1] if "---" in src_path.read_text() else src_path.read_text()

        if src_id not in merged_sources:
            merged_sources.append(src_id)

        target_body += f"\n\n--- merged from {src_id} ---\n{src_body.strip()}"
        src_path.unlink()
        merged_descriptions.append(f"{src_id}: merged into {target_id}")

    target_fm.setdefault("provenance", {})
    target_fm["provenance"]["merged_from"] = merged_sources
    target_fm["provenance"]["merged_at"] = datetime.now(timezone.utc).isoformat()
    target_fm["provenance"]["merged_count"] = len(merged_sources)

    write_frontmatter(target_path, target_fm, target_body.strip())
    return "; ".join(merged_descriptions)


def check_premise_dependencies(
    shadow_id: str,
    premises_dir: Optional[Path] = None,
) -> bool:
    """
    Check if any premise nodes depend on this shadow doc.

    Returns True if dependencies exist (demotion should be blocked).
    Checks DOT files for nodes containing the shadow_id or label references.
    """
    pdir = premises_dir or PREMISES_DIR
    if not pdir or not pdir.exists():
        return False

    shadow_id_lower = shadow_id.lower()

    for dot_file in sorted(pdir.glob("*.dot")):
        content = dot_file.read_text().lower()
        if shadow_id_lower in content:
            return True

    return False


def demote_to_archive(
    shadow_id: str,
    shadow_dir: Path,
    archive_dir: Path,
    reason: str,
    old_score: float,
) -> DemotionEvent:
    """Move a shadow doc from hot to archive with provenance."""
    src = shadow_dir / f"{shadow_id}.md"
    if not src.exists():
        src = next(shadow_dir.glob(f"{shadow_id}*"), None)
    if not src:
        return DemotionEvent(shadow_id, shadow_id, old_score, "not found")

    fm = extract_frontmatter(src)
    body = src.read_text().split("---", 2)[-1] if "---" in src.read_text() else src.read_text()
    fm["archived_at"] = datetime.now(timezone.utc).isoformat()
    fm["archive_reason"] = reason
    fm["archived_score"] = old_score

    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / src.name

    write_frontmatter(dest, fm, body.strip())
    src.unlink()

    title = fm.get("title", shadow_id)
    return DemotionEvent(shadow_id, title, old_score, reason)


def open_demotion_loop(
    shadow_id: str, title: str, score: float
) -> OpenLoop:
    """Open a HIGH-criticality loop when a promoted doc resists demotion."""
    loop = OpenLoop(
        id=generate_loop_id(),
        source_type="shadow_doc",
        source_id=shadow_id,
        status=LoopStatus.OPEN,
        criticality=LoopCriticality.HIGH,
        closure_policy=f"demotion_review: {shadow_id} ({title}) score {score:.2f} below threshold",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return loop


def _build_sleep_dependencies(sdir: Path) -> Dict[str, List[str]]:
    """Build dependency dict for centrality during sleep — same source as generate-index.py."""
    try:
        from lib.epistemic.cold_retrieval import build_shadow_graph
        shadow_ids = []
        for f in sdir.glob("*.md"):
            if f.name != "README.md":
                shadow_ids.append(f.stem)
        if not shadow_ids:
            return {}
        _, deps = build_shadow_graph(shadow_ids, sdir)
        return deps
    except (ImportError, Exception):
        return {}


def sleep(
    shadow_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None,
    access_log_path: Optional[Path] = None,
    premises_dir: Optional[Path] = None,
    demotion_threshold: Optional[float] = None,
    regenerate_index: bool = True,
) -> SleepReport:
    """
    Run the consolidation cycle.

    1. Recompute scores from access.log
    2. Check demotion gate (premise dependencies)
    3. Merge near-duplicates
    4. Archive below-threshold entries (with gate guard)
    5. Regenerate INDEX.md
    6. Return report
    """
    sdir = shadow_dir or SHADOW_DIR
    adir = archive_dir or ARCHIVE_DIR
    alog = access_log_path or ACCESS_LOG
    pd = premises_dir or PREMISES_DIR
    threshold = demotion_threshold if demotion_threshold is not None else DEMOTION_THRESHOLD

    report = SleepReport()
    accesses = parse_access_log(alog)
    now = datetime.now(timezone.utc)

    # Count current files
    hot_before = set()
    for f in sdir.glob("*.md"):
        if f.name != "README.md":
            hot_before.add(f.name)
    report.total_hot = len(hot_before)
    report.total_archive = len(list(adir.glob("*.md"))) if adir.exists() else 0

    # Step 1: recompute scores
    scores = compute_scores(sdir, alog, dependencies=_build_sleep_dependencies(sdir))
    report.score_summary = scores

    # Step 1b: detect stale docs (for report only — no score blending here)
    tidx = None
    try:
        from lib.memory.temporal import TemporalIndex
        tidx = TemporalIndex()
        decays = tidx.decay_report()
        report.temporal_decays = decays
        stale = tidx.stale_docs(threshold=0.3)
        report.stale_docs = [d.doc_id for d in stale]
    except (ImportError, FileNotFoundError, Exception):
        pass  # temporal module optional — skip if unavailable

    # Step 1c: confidence decay from SQLite index (T208)
    import os
    half_life = float(os.environ.get("AES_CONFIDENCE_HALF_LIFE_DAYS", "30"))
    index_db = AES_ROOT / "aes" / "index.db"
    if index_db.exists():
        try:
            from lib.storage.sqlite_store import SQLiteGraphStore
            cstore = SQLiteGraphStore(index_db)
            confidence = {}
            for sid in scores:
                conf = cstore.confidence_score(sid, half_life_days=half_life)
                if conf is not None:
                    confidence[sid] = conf
            # Blend: 70% ACT-R scores + 30% confidence decay
            for sid in scores:
                if sid in confidence:
                    scores[sid] = 0.7 * scores[sid] + 0.3 * confidence[sid]
            report.confidence_scores = confidence
            cstore.close()
        except Exception:
            pass  # confidence is best-effort

    # Cohort view: pinned-but-never-used, used-but-low-score, score trajectory
    for sid, score in scores.items():
        fpath = sdir / f"{sid}.md"
        if not fpath.exists():
            continue
        fm = extract_frontmatter(fpath)
        synthesis = fm.get("synthesis", "")
        if synthesis:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
            # Idempotent: only write if last access is not already /synthesis
            last_access = ""
            if sid in accesses and accesses[sid]:
                last_line = accesses[sid][-1].strip().split()
                if len(last_line) >= 3:
                    last_access = " ".join(last_line[2:])
            if last_access != "/synthesis":
                with open(alog, "a") as lf:
                    lf.write(f"{ts} {sid} /synthesis\n")
        pinned = fm.get("score", {}).get("pinned", False)
        accessed = sid in accesses and len(accesses[sid]) > 0

        if pinned and not accessed:
            report.pinned_unused.append(sid)

        if accessed and score < 0.1 and not pinned:
            report.used_low_score.append(sid)

        # Score trajectory: check archive for previous scores
        archive_path = adir / f"{sid}.md"
        prev_scores = []
        if archive_path.exists():
            afm = extract_frontmatter(archive_path)
            prev = afm.get("archived_score")
            if prev is not None:
                prev_scores.append(float(prev))
        prev_scores.append(score)
        report.score_trajectory[sid] = prev_scores

    # Step 2: merge duplicates before demoting
    merges = find_duplicates(sdir)
    for target_id, source_id, reason in merges:
        merge_desc = merge_shadow_docs(target_id, [source_id], sdir)
        report.merged.append(MergeEvent(target_id, [source_id], reason))

    # Step 3: demotion gate + archive (reuses tidx from step 1b)

    for sid, score in scores.items():
        # Blend temporal decay into demotion score
        if tidx:
            tdoc = tidx.docs().get(sid)
            if tdoc:
                decay = tdoc.temporal_decay()
                score = (1 - TEMPORAL_BLEND_WEIGHT) * score + TEMPORAL_BLEND_WEIGHT * decay

        if score >= threshold:
            continue

        fm = extract_frontmatter(sdir / f"{sid}.md") if (sdir / f"{sid}.md").exists() else {}
        if not fm:
            continue

        title = fm.get("title", sid)
        pinned = fm.get("score", {}).get("pinned", False)
        ep_state = fm.get("epistemic_state", "")

        # Pinned never demotes
        if pinned:
            continue

        # Gate: check premise dependencies for SUPORTADA docs
        if ep_state == "SUPORTADA" and check_premise_dependencies(sid, pd):
            loop = open_demotion_loop(sid, title, score)
            report.blocked_demotions += 1
            report.demoted.append(DemotionEvent(
                sid, title, score, "blocked by premise dependencies", loop.id
            ))
            continue

        # Demote
        event = demote_to_archive(sid, sdir, adir, f"score {score:.2f} below threshold {threshold}", score)
        report.demoted.append(event)

    # Step 4: regenerate INDEX.md
    if regenerate_index:
        import subprocess
        import sys
        subprocess.run([sys.executable, str(AES_ROOT / "scripts" / "generate-index.py")],
                      cwd=str(AES_ROOT), check=True)

    # Step 4b: rebuild SQLite index if it exists
    index_db = AES_ROOT / "aes" / "index.db"
    if index_db.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "sync_sqlite", AES_ROOT / "scripts" / "sync-sqlite.py"
            )
            sync_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sync_mod)
            sync_mod.sync_all(index_db, AES_ROOT)
        except (ImportError, Exception):
            pass  # sync is best-effort

    # Update counts
    hot_after = set()
    for f in sdir.glob("*.md"):
        if f.name != "README.md":
            hot_after.add(f.name)
    report.total_hot = len(hot_after)
    report.total_archive = len(list(adir.glob("*.md"))) if adir.exists() else 0

    return report


@dataclass
class RelevantDoc:
    """A single relevant shadow doc with its score and metadata."""
    doc_id: str
    title: str
    score: float
    in_archive: bool = False


def get_relevant_docs(
    ticket_id: Optional[str] = None,
    ticket_text: Optional[str] = None,
    top_k: int = 10,
) -> List[RelevantDoc]:
    """
    Get relevant shadow docs ranked by BM25+PPR relevance.

    Returns structured data (not formatted text). Use this for programmatic access.
    For formatted output, use build_relevant_now_section().
    """
    if not ticket_text:
        # Try to load ticket text from ticket file
        if ticket_id:
            matches = list(Path("aes/tickets").glob(f"{ticket_id}-*.md"))
            if matches:
                content = matches[0].read_text()
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        ticket_text = parts[2].strip()

    if not ticket_text:
        return []

    # Collect all shadow docs (hot + archive)
    documents = {}

    # Hot docs
    for fpath in sorted(SHADOW_DIR.glob("*.md")):
        if fpath.name == "README.md":
            continue
        content = fpath.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                doc_id = fpath.stem
                fm_str = parts[1]
                try:
                    fm = yaml.safe_load(fm_str)
                    title = fm.get("title", fpath.stem)
                    synthesis = fm.get("synthesis", "")
                    text = f"{title}\n{synthesis}"
                    documents[fpath.stem] = text
                except Exception:
                    pass

    # Archive docs
    for fpath in sorted(ARCHIVE_DIR.glob("*.md")):
        if fpath.name == "README.md":
            continue
        content = fpath.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                doc_id = fpath.stem
                fm_str = parts[1]
                try:
                    fm = yaml.safe_load(fm_str)
                    title = fm.get("title", fpath.stem)
                    synthesis = fm.get("synthesis", "")
                    text = f"{title}\n{synthesis}"
                    documents[fpath.stem] = text
                except Exception:
                    pass

    if not documents:
        return []

    # Run hybrid search (BM25 + PPR) for better cross-language retrieval
    from .relevance import bm25_search_reranked
    from lib.epistemic.cold_retrieval import hybrid_bm25_ppr, build_shadow_graph
    adj = build_shadow_graph()
    results = hybrid_bm25_ppr(
        query=ticket_text,
        bm25_search_fn=bm25_search_reranked,
        shadow_docs=documents,
        adj=adj,
        top_k_bm25=20,
        final_k=20,
    )

    if not results:
        return []

    # Blend temporal decay into search results (fresh docs rank higher)
    try:
        from lib.memory.temporal import TemporalIndex
        tidx = TemporalIndex()
        tdocs = tidx.docs()
        results = [
            (doc_id, (1 - TEMPORAL_BLEND_WEIGHT) * score + TEMPORAL_BLEND_WEIGHT * tdocs[doc_id].temporal_decay())
            if doc_id in tdocs else (doc_id, score)
            for doc_id, score in results
        ]
    except (ImportError, Exception):
        pass

    # Split results: hot vs archive
    hot_ids = set()
    for f in SHADOW_DIR.glob("*.md"):
        if f.name != "README.md":
            hot_ids.add(f.stem)

    # Build structured results
    relevant_docs = []
    for doc_id, score in results[:top_k]:
        in_archive = doc_id not in hot_ids
        # Get title from frontmatter
        fpath = (ARCHIVE_DIR if in_archive else SHADOW_DIR) / f"{doc_id}.md"
        title = doc_id
        if fpath.exists():
            content = fpath.read_text()
            if content.startswith("---"):
                try:
                    fm = yaml.safe_load(content.split("---")[1])
                    title = fm.get("title", doc_id)
                except Exception:
                    pass
        relevant_docs.append(RelevantDoc(
            doc_id=doc_id,
            title=title,
            score=score,
            in_archive=in_archive,
        ))

    return relevant_docs


def build_relevant_now_section(
    ticket_id: Optional[str] = None,
    ticket_text: Optional[str] = None,
    top_k: int = 10,
) -> Optional[str]:
    """
    Build the 'RELEVANT NOW' section for wake output.

    Uses get_relevant_docs() and formats as text.
    For structured data, use get_relevant_docs() directly.
    """
    relevant_docs = get_relevant_docs(ticket_id, ticket_text, top_k)

    if not relevant_docs:
        return None

    section_parts = ["── RELEVANT NOW ──"]

    # Hot results first
    hot_docs = [d for d in relevant_docs if not d.in_archive]
    if hot_docs:
        section_parts.append("  Hot index (entrenchment order):")
        for doc in hot_docs:
            section_parts.append(f"  • {doc.doc_id} — {doc.title} (relevance: {doc.score:.3f})")

    # Archive resurfacing
    archive_docs = [d for d in relevant_docs if d.in_archive]
    if archive_docs:
        section_parts.append("  Archive resurfacing:")
        for doc in archive_docs:
            section_parts.append(f"  • {doc.doc_id} — {doc.title} (relevance: {doc.score:.3f}) [ARCHIVED]")

    if len(section_parts) == 1:
        return None

    return "\n".join(section_parts)


def _load_shadow_doc_full(fpath: Path) -> Optional[dict]:
    """Load a shadow doc and return frontmatter + body text."""
    if fpath.name == "README.md":
        return None
    content = fpath.read_text()
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
        body = parts[2].strip()
        return {"fm": fm, "body": body, "path": fpath}
    except Exception:
        return None


def _verify_shadow_premises(doc: dict) -> List[str]:
    """
    Verify premises for a single shadow doc.

    Returns list of premise descriptions that failed, or empty if all pass.
    Checks: pointer.path existence, epistemic_state consistency, source ticket.
    """
    failures = []
    fm = doc["fm"]

    # Check pointer.path exists
    pointer_path = fm.get("pointer", {}).get("path", "")
    if pointer_path and not pointer_path.startswith("http"):
        p = Path(pointer_path)
        if not p.exists():
            failures.append(f"pointer.path missing: {pointer_path}")

    # Check source ticket exists (informational, not a failure)
    source_ticket = fm.get("provenance", {}).get("source_ticket", "")
    if source_ticket:
        tickets_dir = AES_ROOT / "aes" / "tickets"
        if tickets_dir.exists():
            matches = list(tickets_dir.glob(f"{source_ticket}-*.md"))
        # Don't fail on missing tickets — they may be archived

    # Check epistemic_state consistency
    ep_state = fm.get("epistemic_state", "")
    if ep_state == "SUPORTADA" and not fm.get("synthesis"):
        failures.append("SUPORTADA but no synthesis")

    return failures


STALENESS_THRESHOLD_DAYS = int(
    __import__("os").environ.get("AES_STALENESS_THRESHOLD_DAYS", "14")
)


def _detect_staleness(doc: dict, last_accessed: str) -> bool:
    """
    Detect if a shadow doc might be stale.

    Heuristic: if last_accessed > STALENESS_THRESHOLD_DAYS ago and not pinned.
    Configurable via AES_STALENESS_THRESHOLD_DAYS env var (default: 14).
    """
    if doc["fm"].get("score", {}).get("pinned", False):
        return False  # pinned docs are never stale

    try:
        # Handle both naive and timezone-aware datetimes
        accessed_str = last_accessed.replace("Z", "+00:00")
        accessed = datetime.fromisoformat(accessed_str)
        now = datetime.now(timezone.utc)
        
        # If naive, assume UTC
        if accessed.tzinfo is None:
            accessed = accessed.replace(tzinfo=timezone.utc)
        
        days_since = (now - accessed).days
        return days_since > STALENESS_THRESHOLD_DAYS
    except (ValueError, TypeError):
        return False


def _verify_premise_graphs() -> Dict[str, List[str]]:
    """
    Load and verify all premise graphs in aes/premises/.

    Returns dict of {node_id: [failure_reasons]} for failed premises.
    Uses the premise_engine to parse DOT/JSON graphs and verify each node.
    """
    failures: Dict[str, List[str]] = {}
    premises_dir = AES_ROOT / "aes" / "premises"

    if not premises_dir.exists():
        return failures

    try:
        import sys
        # premise-engine has a hyphen — can't import normally
        engine_dir = AES_ROOT / "lib" / "premise-engine"
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        from premise_engine import (
            load_graph,
            verify_all,
            VerifyStatus,
        )
    except ImportError:
        # premise_engine not available — skip graph verification
        return failures

    for graph_file in premises_dir.glob("*.dot"):
        try:
            graph = load_graph(graph_file.read_text(), fmt="dot")
            results = verify_all(graph)
            for r in results:
                if r.status == VerifyStatus.FAIL:
                    node = graph.premises.get(r.node_id)
                    label = node.label if node else r.node_id
                    if r.node_id not in failures:
                        failures[r.node_id] = []
                    failures[r.node_id].append(f"{label}: {r.output or 'failed'}")
        except Exception:
            pass  # skip malformed graphs

    for graph_file in premises_dir.glob("*.json"):
        try:
            graph = load_graph(graph_file.read_text(), fmt="json")
            results = verify_all(graph)
            for r in results:
                if r.status == VerifyStatus.FAIL:
                    node = graph.premises.get(r.node_id)
                    label = node.label if node else r.node_id
                    if r.node_id not in failures:
                        failures[r.node_id] = []
                    failures[r.node_id].append(f"{label}: {r.output or 'failed'}")
        except Exception:
            pass  # skip malformed graphs

    return failures


def _build_synthesis(
    relevant_docs: List[tuple],
    ticket_text: str,
) -> List[InsightRelevance]:
    """
    Synthesize relevant insights from shadow docs.

    Takes BM25+PPR results and builds structured InsightRelevance objects.
    This is where "information becomes knowledge" — not just search results,
    but actionable insights with staleness and premise checks.
    """
    insights = []
    seen_ids = set()

    for doc_id, score in relevant_docs:
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)

        fpath = SHADOW_DIR / f"{doc_id}.md"
        in_archive = False
        if not fpath.exists():
            fpath = ARCHIVE_DIR / f"{doc_id}.md"
            in_archive = True
        if not fpath.exists():
            continue

        doc = _load_shadow_doc_full(fpath)
        if not doc:
            continue

        fm = doc["fm"]
        title = fm.get("title", doc_id)
        synthesis = fm.get("synthesis", "")
        ep_state = fm.get("epistemic_state", "")
        last_accessed = fm.get("last_accessed", "")

        # Verify premises
        premise_failures = _verify_shadow_premises(doc)

        # Detect staleness
        is_stale = _detect_staleness(doc, last_accessed)

        gmif_level = fm.get("gmif", "")

        insights.append(InsightRelevance(
            doc_id=doc_id,
            title=title,
            synthesis=synthesis,
            relevance_score=score,
            epistemic_state=ep_state,
            gmif=gmif_level,
            is_stale=is_stale,
            premise_failures=premise_failures,
        ))

    return insights


def wake(
    shadow_dir: Optional[Path] = None,
    index_file: Optional[Path] = None,
    loops: Optional[List[OpenLoop]] = None,
    ticket_id: Optional[str] = None,
    ticket_text: Optional[str] = None,
    use_deep: bool = False,
    kanban_path: Optional[Path] = None,
) -> ExecutionContext:
    """
    Build execution context: what's relevant, what's stale, what needs attention.

    Returns ExecutionContext (structured data), not a string.
    Use .format() for CLI output.

    Phases:
    1. LOAD — load shadow docs and identify relevant ones
    2. VERIFY — check premises against reality
    3. SYNTHESIZE — extract actionable insights for current ticket
    4. BUILD — return structured context
    """
    sdir = shadow_dir or SHADOW_DIR

    # Read current ticket/sprint from kanban
    kpath = kanban_path or (AES_ROOT / "aes" / "kanban.md")
    current_ticket = ticket_id
    sprint = "unknown"
    if kpath and kpath.exists():
        fm = extract_frontmatter(kpath)
        if not current_ticket:
            current_ticket = fm.get("current_ticket")
        sprint = fm.get("current_sprint", "unknown")

    ctx = ExecutionContext(
        ticket_id=current_ticket,
        sprint=sprint,
    )

    # Phase 1: LOAD — load relevant shadow docs
    # If no ticket_text provided, try to load from ticket file
    if not ticket_text and current_ticket:
        matches = list(Path("aes/tickets").glob(f"{current_ticket}-*.md"))
        if matches:
            content = matches[0].read_text()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    ticket_text = parts[2].strip()

    # Get relevant docs via BM25+PPR if we have ticket_text
    relevant_docs = []
    if ticket_text or use_deep:
        relevant_structured = get_relevant_docs(current_ticket, ticket_text)
        relevant_docs = [(d.doc_id, d.score) for d in relevant_structured]

    # Phase 2: VERIFY + Phase 3: SYNTHESIZE
    if relevant_docs:
        ctx.relevant_insights = _build_synthesis(relevant_docs, ticket_text or "")
    else:
        # Fallback: just list hot shadow docs with basic info
        for fpath in sorted(sdir.glob("*.md")):
            if fpath.name == "README.md":
                continue
            doc = _load_shadow_doc_full(fpath)
            if not doc:
                continue
            fm = doc["fm"]
            doc_id = fm.get("id", fpath.stem)
            last_accessed = fm.get("last_accessed", "")
            is_stale = _detect_staleness(doc, last_accessed)
            premise_failures = _verify_shadow_premises(doc)

            ctx.relevant_insights.append(InsightRelevance(
                doc_id=doc_id,
                title=fm.get("title", doc_id),
                synthesis=fm.get("synthesis", ""),
                relevance_score=0.0,  # no relevance ranking without ticket
                epistemic_state=fm.get("epistemic_state", ""),
                gmif=fm.get("gmif", ""),
                is_stale=is_stale,
                premise_failures=premise_failures,
            ))

    # Collect stale warnings
    for ins in ctx.relevant_insights:
        if ins.is_stale:
            ctx.stale_warnings.append(
                f"{ins.doc_id} ({ins.title}) — last accessed > {STALENESS_THRESHOLD_DAYS} days ago"
            )
        if ins.premise_failures:
            ctx.premise_failures[ins.doc_id] = ins.premise_failures

    # Phase 2b: VERIFY PREMISE GRAPHS — check all premise graphs
    graph_failures = _verify_premise_graphs()
    for node_id, reasons in graph_failures.items():
        ctx.premise_failures[f"graph:{node_id}"] = reasons

    # Phase 4: OPEN LOOPS — load HIGH loops
    if loops is None and use_deep:
        try:
            import os
            from lib.epistemic.promotion_gate import load_loops
            store_path = Path(os.environ.get("GRILO_LOOPS", ".grilo/loops.json"))
            if store_path.exists():
                all_loops = load_loops(store_path)
                loops = all_loops if all_loops else []
            else:
                loops = []
        except (ImportError, FileNotFoundError, Exception):
            loops = []

    if loops:
        high_loops = [l for l in loops if l.criticality == LoopCriticality.HIGH and l.status == LoopStatus.OPEN]
        for l in high_loops:
            desc = getattr(l, 'description', '') or getattr(l, 'source_id', '')
            ctx.open_loops.append(f"{l.id} ({l.source_type}: {l.source_id}) — {desc}")

    # Generate suggested actions
    for ins in ctx.relevant_insights:
        if ins.is_stale:
            ctx.actions.append(f"Verify {ins.doc_id} — may be stale")
        if ins.premise_failures:
            ctx.actions.append(f"Fix premises for {ins.doc_id}: {', '.join(ins.premise_failures)}")

    # Phase 5: GRAPH GOVERNANCE — lint graph, classify claims, govern decisions
    try:
        from lib.epistemic.orchestrator import GovernanceOrchestrator
        from lib.epistemic.graph_store import InMemoryGraphStore
        from lib.epistemic.gmif import parse_gmif

        # Opt-in: use SQLite index if it exists, else build in-memory
        index_db = AES_ROOT / "aes" / "index.db"
        if index_db.exists():
            from lib.storage.sqlite_store import SQLiteGraphStore
            store = SQLiteGraphStore(index_db)
        else:
            store = InMemoryGraphStore()
            # Load graph from DOT files
            for dot_file in (AES_ROOT / "aes" / "premises").glob("*.dot"):
                store.load_from_dot(dot_file)
            # Load graph from shadow docs
            for fpath in sdir.glob("*.md"):
                if fpath.name == "README.md":
                    continue
                doc = _load_shadow_doc_full(fpath)
                if doc:
                    fm = doc["fm"]
                    doc_id = fm.get("id", fpath.stem)
                    store.load_from_shadow_doc(doc_id, fm)

        # Run orchestrator
        orchestrator = GovernanceOrchestrator(store, enforce=False)

        # Run graph lint
        lint_issues = orchestrator.run_graph_lint()
        for code, issues in lint_issues.items():
            if issues:
                ctx.graph_lint_issues[code] = len(issues)
                for issue in issues:
                    ctx.actions.append(f"Lint {code}: {issue.description}")

        # Classify relevant insights
        for ins in ctx.relevant_insights:
            if ins.synthesis:
                claimed = parse_gmif(ins.gmif) if getattr(ins, 'gmif', None) else parse_gmif(ins.epistemic_state) if ins.epistemic_state else None
                result = orchestrator.govern_claim(
                    ins.synthesis,
                    claim_id=ins.doc_id,
                    claimed_level=claimed,
                )
                ctx.gmif_classifications[ins.doc_id] = result.gmif_result.level.value
                ctx.governance_decisions[ins.doc_id] = result.overall_decision

                if result.overall_decision == "warn":
                    ctx.actions.append(f"Governance warning for {ins.doc_id}")

    except ImportError:
        # Epistemic modules not available — skip graph governance
        pass

    return ctx


def sleep_twice_idempotent(
    shadow_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None,
    access_log_path: Optional[Path] = None,
    premises_dir: Optional[Path] = None,
) -> bool:
    """
    Idempotence check: sleep twice with no new accesses → no changes.

    Returns True if no changes on second sleep.
    """
    first = sleep(shadow_dir, archive_dir, access_log_path, premises_dir)
    second = sleep(shadow_dir, archive_dir, access_log_path, premises_dir)

    return (
        len(second.demoted) == 0
        and len(second.merged) == 0
    )
