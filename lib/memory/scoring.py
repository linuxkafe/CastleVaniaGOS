"""
Composite scoring for the hot index (T038).

score = w1 * activation + w2 * pinned + w3 * centrality

Weights and decay are configurable via the CONFIG dict — never hard-coded
magic numbers. Defaults justified in docs/HOT_INDEX.md.
"""

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

CONFIG = {
    "w1": 0.5,       # activation weight — recency/frequency matters most
    "w2": 0.3,       # pinned weight — human override is strong
    "w3": 0.2,       # centrality weight — graph position matters less
    "decay_d": 0.5,  # ACT-R decay parameter (typical range 0.2–1.0)
    "token_budget": 4000,  # max tokens for INDEX.md
    "pinned_bonus": 1.0,
    "default_activation": 0.1,  # for docs never accessed
}


def compute_activation(
    access_timestamps: List[str],
    current_time: Optional[datetime] = None,
    decay_d: Optional[float] = None,
) -> float:
    """
    ACT-R base-level activation.

    activation = sum_i ( (t_now - t_i) / 86400 ) ^ (-d)

    Each access contributes an exponentially-decaying recency signal.
    A doc accessed 5 times in the last week scores higher than one
    accessed 5 times last month.
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    d = decay_d if decay_d is not None else CONFIG["decay_d"]

    total = 0.0
    valid_count = 0
    for ts in access_timestamps:
        try:
            t = datetime.fromisoformat(ts)
            days_ago = (current_time - t).total_seconds() / 86400
            if days_ago < 0:
                days_ago = 0.0
            total += (days_ago + 1) ** (-d)
            valid_count += 1
        except (ValueError, TypeError):
            continue

    if valid_count == 0:
        return CONFIG["default_activation"]
    return total


def compute_centrality(
    shadow_id: str,
    dependencies: Optional[Dict[str, List[str]]] = None,
) -> float:
    """
    Centrality = how many propositions depend on this shadow doc.

    Derived from the premise graph's dependency edges. A doc that supports
    many propositions gets a higher centrality score.
    """
    if dependencies is None:
        return 0.0
    return float(len(dependencies.get(shadow_id, [])))


def composite_score(
    activation: float,
    pinned: bool,
    centrality: float,
    config: Optional[Dict] = None,
) -> float:
    """Compute the composite score."""
    cfg = config or CONFIG
    p = cfg["pinned_bonus"] if pinned else 0.0
    return cfg["w1"] * activation + cfg["w2"] * p + cfg["w3"] * centrality


def parse_access_log(log_path: Path) -> Dict[str, List[str]]:
    """
    Parse access.log into {shadow_id: [timestamps]}.

    Format per line: ISO_TIMESTAMP SHADOW_ID [TICKET]
    Lines starting with # are skipped.
    """
    accesses: Dict[str, List[str]] = defaultdict(list)
    if not log_path.exists():
        return accesses

    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        ts, sid = parts[0], parts[1]
        accesses[sid].append(ts)

    return accesses


def compute_scores(
    shadow_dir: Path,
    access_log_path: Path,
    dependencies: Optional[Dict[str, List[str]]] = None,
    config: Optional[Dict] = None,
) -> Dict[str, float]:
    """
    Compute composite scores for all shadow docs in shadow_dir.

    Returns {shadow_id: composite_score} sorted descending.
    """
    import yaml

    cfg = config or CONFIG
    accesses = parse_access_log(access_log_path)
    now = datetime.now(timezone.utc)

    scores: Dict[str, float] = {}

    for fpath in sorted(shadow_dir.glob("*.md")):
        if fpath.name == "README.md":
            continue
        content = fpath.read_text()
        if not content.startswith("---"):
            continue
        _, fm_str, _ = content.split("---", 2)
        try:
            fm = yaml.safe_load(fm_str)
        except yaml.YAMLError:
            continue

        sid = fm.get("id", fpath.stem)
        pinned = fm.get("score", {}).get("pinned", False)
        doc_accesses = accesses.get(sid, [])
        act = compute_activation(doc_accesses, now, cfg["decay_d"])
        cent = compute_centrality(sid, dependencies)
        scores[sid] = composite_score(act, pinned, cent, cfg)

    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))


def entrenchment_compare(
    score_a: float,
    score_b: float,
    eps: float = 1e-9,
) -> int:
    """
    Compare two entrenchment scores.

    Returns -1 if a < b, 0 if |a-b| < eps, 1 if a > b.
    Used for property tests verifying AGM entrenchment postulates.
    """
    if abs(score_a - score_b) < eps:
        return 0
    return 1 if score_a > score_b else -1


def is_maximal_entrenchment(score: float, all_scores: Dict[str, float], eps: float = 1e-9) -> bool:
    """
    Check if a score is maximal entrenchment (no other score is higher).
    Pinned docs should have maximal entrenchment.
    """
    return all(entrenchment_compare(score, s, eps) >= 0 for s in all_scores.values())
