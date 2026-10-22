"""Append-only regime ledger.

Ported from Grilo Falante v3, which rewrote the whole JSON file on every
save and exposed clear() -- both violations of the ledger's own append-only
semantics (ambrosio: "append-only historical record"). This version appends
one JSON line per entry and offers no erasure API: history can be read and
filtered, never rewritten.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class LedgerEntryType(Enum):
    CLAIM = "CLAIM"
    NORMATIVE_CANDIDATE = "NORMATIVE_CANDIDATE"
    DIGITAL_OBJECT = "DIGITAL_OBJECT"
    AUDIT = "AUDIT"
    TRANSITION = "TRANSITION"
    PINA_DECISION = "PINA_DECISION"
    LINT_RESULT = "LINT_RESULT"
    REGIME_EVENT = "REGIME_EVENT"
    CONSOLIDATION = "CONSOLIDATION"
    ILHA_SLEEP = "ILHA_SLEEP"


@dataclass
class LedgerEntry:
    entry_id: str
    entry_type: str
    gf_id: Optional[str] = None
    content: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cycle_id: Optional[str] = None


class Ledger:
    """Persistent, append-only audit trail (JSONL: one entry per line)."""

    def __init__(self, ledger_path: Optional[Path] = None):
        self.ledger_path = Path(ledger_path) if ledger_path else Path("ledger.jsonl")
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[LedgerEntry] = []
        self._load()

    def _load(self):
        if not self.ledger_path.exists():
            return
        for line in self.ledger_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self._entries.append(LedgerEntry(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue

    def _append(self, entry: LedgerEntry):
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def add_entry(
        self,
        entry_type: LedgerEntryType,
        content: str = "",
        gf_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        entry_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            entry_id=entry_id or self._generate_entry_id(entry_type),
            entry_type=entry_type.value,
            gf_id=gf_id,
            content=content,
            metadata=metadata or {},
            cycle_id=cycle_id,
        )
        self._entries.append(entry)
        self._append(entry)
        return entry

    def _generate_entry_id(self, entry_type: LedgerEntryType) -> str:
        timestamp = datetime.now().strftime("%y%m%d%H%M%S%f")
        return f"{entry_type.value[:3].upper()}-{timestamp}"

    def get_claims(self, cycle_id: Optional[str] = None) -> list[LedgerEntry]:
        entries = self._by_type(LedgerEntryType.CLAIM)
        if cycle_id:
            entries = [e for e in entries if e.cycle_id == cycle_id]
        return entries

    def get_nca(self) -> list[LedgerEntry]:
        return self._by_type(LedgerEntryType.NORMATIVE_CANDIDATE)

    def get_audits(self) -> list[LedgerEntry]:
        return self._by_type(LedgerEntryType.AUDIT)

    def get_regime_events(self) -> list[LedgerEntry]:
        return self._by_type(LedgerEntryType.REGIME_EVENT)

    def get_transitions(self) -> list[LedgerEntry]:
        return self._by_type(LedgerEntryType.TRANSITION)

    def _by_type(self, entry_type: LedgerEntryType) -> list[LedgerEntry]:
        return [e for e in self._entries if e.entry_type == entry_type.value]

    def search(self, query: str) -> list[LedgerEntry]:
        q = query.lower()
        return [
            e
            for e in self._entries
            if q in e.content.lower() or q in str(e.metadata).lower()
        ]

    def get_cycle_entries(self, cycle_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.cycle_id == cycle_id]

    def get_stats(self) -> dict:
        by_type = {
            t.value: sum(1 for e in self._entries if e.entry_type == t.value)
            for t in LedgerEntryType
        }
        return {
            "total_entries": len(self._entries),
            "by_type": by_type,
            "cycles": len({e.cycle_id for e in self._entries if e.cycle_id}),
            "first_entry": self._entries[0].timestamp if self._entries else None,
            "last_entry": self._entries[-1].timestamp if self._entries else None,
        }
