"""
Temporal validity for shadow documents.

Tracks when shadow docs were created, last accessed, and whether they're
still temporally relevant. Supports queries like:
  - "What was true about X last week?"
  - "Is this claim still current?"
  - "When was this knowledge last verified?"

Temporal decay model:
  - Fresh docs (< 7 days): full relevance
  - Aging docs (7-30 days): exponential decay
  - Stale docs (> 30 days): heavily decayed, flagged for review
  - Archived docs: use archived_at as valid_until

References:
  - MemPalace temporal knowledge graph
  - ACT-R decay function (Anderson 2007)
  - AES shadow doc lifecycle (consolidate.py)

Usage:
    from lib.memory.temporal import TemporalIndex
    index = TemporalIndex()
    current = index.current_docs()
    valid_at = index.docs_valid_at(datetime(2026, 7, 20))
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

# AES_ROOT de entrada tem precedencia sobre a localizacao do ficheiro. Sem isto,
# uma copia instalada (skills/, /usr/local/lib/aes) resolve a raiz da instalacao
# em vez da raiz do projecto, e nao encontra aes/shadow. Mesmo padrao de
# scripts/epistemic-debt-rules.sh:7 e scripts/safe-shell.sh:11.
AES_ROOT = Path(
    os.environ.get("AES_ROOT") or Path(__file__).resolve().parent.parent.parent
)
SHADOW_DIR = AES_ROOT / "aes" / "shadow"
ARCHIVE_DIR = SHADOW_DIR / "archive"

# Temporal decay parameters
FRESH_DAYS = 7       # Full relevance for docs < 7 days old
STALE_DAYS = 30      # Heavily decayed after 30 days
DECAY_LAMBDA = 0.05  # Exponential decay rate


@dataclass
class TemporalDoc:
    """Temporal metadata for a shadow document."""
    doc_id: str
    created: datetime
    last_accessed: datetime
    epistemic_state: str  # SUPORTADA, NÃO-SUPORTADA, NÃO-VERIFICÁVEL
    archived_at: Optional[datetime] = None
    archived_score: Optional[float] = None
    source_ticket: Optional[str] = None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def age_days(self) -> float:
        now = datetime.now(timezone.utc)
        return (now - self.created).total_seconds() / 86400

    @property
    def staleness_days(self) -> float:
        now = datetime.now(timezone.utc)
        return (now - self.last_accessed).total_seconds() / 86400

    def temporal_decay(self, at: Optional[datetime] = None) -> float:
        """Compute temporal decay factor at a given time.

        Returns a value in [0, 1]:
          - 1.0 for fresh docs (< FRESH_DAYS)
          - exp(-lambda * age) for aging docs
        """
        reference = at or datetime.now(timezone.utc)
        age = (reference - self.last_accessed).total_seconds() / 86400
        if age <= FRESH_DAYS:
            return 1.0
        return math.exp(-DECAY_LAMBDA * (age - FRESH_DAYS))

    def is_valid_at(self, at: datetime) -> bool:
        """Check if this doc was valid at a given point in time."""
        if self.created > at:
            return False
        if self.archived_at and self.archived_at < at:
            return False
        return True

    def valid_window(self) -> Tuple[datetime, Optional[datetime]]:
        """Return (valid_from, valid_until) window."""
        return self.created, self.archived_at


class TemporalIndex:
    """Index of all shadow docs with temporal metadata."""

    def __init__(self):
        self._docs: Dict[str, TemporalDoc] = {}
        self._loaded = False

    def _load(self) -> None:
        """Load temporal metadata from all shadow docs."""
        if self._loaded:
            return

        for directory in [SHADOW_DIR, ARCHIVE_DIR]:
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
                    fm = yaml.safe_load(parts[1])
                except yaml.YAMLError:
                    continue

                doc_id = fm.get("id", fpath.stem)
                created = _parse_dt(fm.get("created"))
                last_accessed = _parse_dt(fm.get("last_accessed")) or created
                epistemic_state = fm.get("epistemic_state", "NÃO-VERIFICÁVEL")
                archived_at = _parse_dt(fm.get("archived_at"))
                archived_score = fm.get("archived_score")
                provenance = fm.get("provenance")
                # provenance pode ser um mapping (o normal) ou um escalar. Um
                # escalar nao tem .get e rebentava o indice inteiro com
                # AttributeError. Nao se inventa semantica para o escalar:
                # devolve None e o doc continua visivel para o decay.
                source_ticket = (
                    provenance.get("source_ticket")
                    if isinstance(provenance, dict)
                    else None
                )

                if created is None:
                    continue

                self._docs[doc_id] = TemporalDoc(
                    doc_id=doc_id,
                    created=created,
                    last_accessed=last_accessed or created,
                    epistemic_state=epistemic_state,
                    archived_at=archived_at,
                    archived_score=archived_score,
                    source_ticket=source_ticket,
                )

        self._loaded = True

    def docs(self) -> Dict[str, TemporalDoc]:
        """All temporal docs."""
        self._load()
        return self._docs

    def current_docs(self) -> List[TemporalDoc]:
        """Docs that are not archived (still in hot index or active)."""
        self._load()
        return [d for d in self._docs.values() if not d.is_archived]

    def archived_docs(self) -> List[TemporalDoc]:
        """Docs that have been archived."""
        self._load()
        return [d for d in self._docs.values() if d.is_archived]

    def docs_valid_at(self, at: datetime) -> List[TemporalDoc]:
        """Docs that were valid at a specific point in time."""
        self._load()
        return [d for d in self._docs.values() if d.is_valid_at(at)]

    def docs_by_epistemic_state(self, state: str) -> List[TemporalDoc]:
        """Docs filtered by epistemic state."""
        self._load()
        return [d for d in self._docs.values() if d.epistemic_state == state]

    def decay_report(self) -> Dict[str, float]:
        """Compute temporal decay for all docs."""
        self._load()
        return {doc_id: doc.temporal_decay() for doc_id, doc in self._docs.items()}

    def stale_docs(self, threshold: float = 0.3) -> List[TemporalDoc]:
        """Docs with temporal decay below threshold (stale, need review)."""
        self._load()
        return [d for d in self._docs.values()
                if d.temporal_decay() < threshold]

    def summary(self) -> Dict:
        """Summary statistics of the temporal index."""
        self._load()
        current = self.current_docs()
        archived = self.archived_docs()
        decays = self.decay_report()

        return {
            "total": len(self._docs),
            "current": len(current),
            "archived": len(archived),
            "avg_decay": round(sum(decays.values()) / len(decays), 3) if decays else 0,
            "stale_count": len(self.stale_docs()),
            "epistemic_states": {
                state: len(self.docs_by_epistemic_state(state))
                for state in ["SUPORTADA", "NÃO-SUPORTADA", "NÃO-VERIFICÁVEL"]
            },
        }


def _parse_dt(value) -> Optional[datetime]:
    """Parse a datetime from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # datetime e subclasse de date, por isso este ramo so apanha uma data pura.
    # YAML converte `created: 2026-07-09` (sem aspas) num datetime.date, que
    # caia fora dos dois ramos seguintes e devolvia None — e o caller faz
    # `if created is None: continue`, o que eliminava o doc do indice sem
    # nenhum registo. Sem este ramo, 7 shadow docs reais desapareciam.
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        # Try ISO format
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return None
