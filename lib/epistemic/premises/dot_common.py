"""Shared DOT helpers for the premise parsers (T300 / R-19).

The two premise parsers (``aes/gf/propagate.py`` and
``lib/epistemic/premises/engine.py``) used to duplicate fragile DOT logic in
slightly different ways, which is exactly how R-19 was born: the project DOT
uses uppercase ``type=FOUNDATIONAL`` while the enums are lowercase, and node
ids sit on a separate line from their attributes. All shared normalization and
selection logic lives here so the two parsers cannot drift again.

Enum conventions:

* ``PropositionRole`` / ``RelationType`` are ``str`` enums whose **names** are
  uppercase (``FOUNDATIONAL``, ``DEPENDS_ON``) and whose **values** are
  lowercase (``foundational``, ``depends_on``). The DOT files use the names.
"""

from pathlib import Path
from typing import List, Optional

from lib.epistemic.epistemic_objects import (
    PropositionRole,
    RelationType,
)

#: Canonical premise graph file (T299 premisse CSS->playwright lives here).
CANONICAL_DOT = "project-graph.dot"


#: DOT structural/config line prefixes that break multi-line continuation.
#: A header line like ``digraph G {`` terminates on its own (never joins the
#: next statement), otherwise a node on the next line would be swallowed:
#: ``digraph G { "F1" [...]`` has no quoted head and gets dropped.
_STRUCTURAL_PREFIXES = (
    "digraph",
    "subgraph",
    "graph",
    "node",
    "edge",
    "rankdir",
    "compound",
    "newrank",
    "labelloc",
    "font",
    "color",
    "shape",
    "style",
)


def join_dot_lines(content: str) -> List[str]:
    """Merge DOT statements split across lines into single logical lines.

    The canonical project DOT writes each node as::

        "prem_repo_available"
            [label="...", type=FOUNDATIONAL, ...];

    i.e. the node id and its attribute list on separate lines, terminated by
    ``;``. This helper joins continuation lines up to the next ``;`` so the
    line-based parsers can consume one statement per entry. Structural lines
    (``digraph``/``subgraph``/``node``/``edge`` headers, ``}``) always break
    the continuation so they never swallow a following node.
    """
    merged: List[str] = []
    buf = ""
    for raw in content.split("\n"):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        if line.startswith(_STRUCTURAL_PREFIXES) or line in ("{", "}"):
            if buf.strip():
                merged.append(buf.strip())
            buf = ""
            if line.endswith(";"):
                merged.append(line)
            continue
        buf += " " + line
        if line.endswith(";"):
            merged.append(buf.strip())
            buf = ""
    if buf.strip():
        merged.append(buf.strip())
    return merged


def proposition_role(raw: Optional[str]) -> PropositionRole:
    """Map a DOT ``type=`` value to a PropositionRole, tolerating case.

    Falls back to DERIVED for unknown values (never raises).
    """
    key = (raw or "DERIVED").strip().upper()
    if key in PropositionRole.__members__:
        return PropositionRole[key]
    return PropositionRole.DERIVED


def relation_type(raw: str) -> RelationType:
    """Map a DOT ``label=`` edge value to a RelationType, tolerating case.

    Falls back to DEPENDS_ON for unknown values (never raises).
    """
    key = raw.strip().upper()
    if key in RelationType.__members__:
        return RelationType[key]
    return RelationType.DEPENDS_ON


def pick_canonical_dot(premises_dir: Path) -> Optional[Path]:
    """Choose the premise graph file deterministically.

    Prefers the canonical ``project-graph.dot``; otherwise a deterministic
    sorted pick. Returns ``None`` when no ``*.dot`` exists.
    """
    if not premises_dir.exists():
        return None
    canonical = premises_dir / CANONICAL_DOT
    if canonical.exists():
        return canonical
    dots = sorted(premises_dir.glob("*.dot"))
    return dots[0] if dots else None