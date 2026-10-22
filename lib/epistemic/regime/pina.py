"""PINA -- Protocol for Normative Incorporation (FR-5).

Ported from v3.0 with the ambrosio hostile-audit fixes applied:
- REGIME-4: decision syntax is ACCEPT / REJECT / DEFER <reason> (the v3.0
  letters A/B/C remain accepted for compatibility).
- REGIME-7: pending candidates can be flagged as stale (>24h) so DEFER loops
  cannot silently neutralize the protocol.

Rules: detection alone never triggers PINA; only Normative Candidates enter
the gate; human authorization is required; silence is not a decision.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from lib.epistemic.regime.ledger import Ledger, LedgerEntryType
from lib.epistemic.regime.state import StateMachine


class PINADecision(Enum):
    INCORPORATE = "A"
    DO_NOT_INCORPORATE = "B"
    DEFER = "C"


_DECISION_ALIASES = {
    "A": PINADecision.INCORPORATE,
    "ACCEPT": PINADecision.INCORPORATE,
    "B": PINADecision.DO_NOT_INCORPORATE,
    "REJECT": PINADecision.DO_NOT_INCORPORATE,
    "C": PINADecision.DEFER,
    "DEFER": PINADecision.DEFER,
}


@dataclass
class NormativeCandidateRecord:
    nca_id: str
    source_document: str
    faithful_statement: str
    location: str
    graph_scope: Optional[str] = None
    decision: Optional[PINADecision] = None
    reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    decided_at: Optional[datetime] = None
    cycle_id: Optional[str] = None


@dataclass
class PINAResult:
    success: bool
    nca_id: str
    message: str
    decision: Optional[str] = None
    active_invariants: int = 0


class PINAProtocol:
    """The PINA decision gate."""

    def __init__(self, state_machine: StateMachine, ledger: Optional[Ledger] = None):
        self.state_machine = state_machine
        self.ledger = ledger
        self._candidates: dict[str, NormativeCandidateRecord] = {}
        self._active_invariants: list[str] = []

    def _generate_nca_id(self, source_document: str, location: str) -> str:
        source_hash = hashlib.md5(source_document.encode()).hexdigest()[:6]
        loc_hash = hashlib.md5(location.encode()).hexdigest()[:4]
        timestamp = datetime.now().strftime("%y%m%d%H%M%S")
        return f"NCA-{source_hash}-{loc_hash}-{timestamp}"

    def propose_candidate(
        self,
        source_document: str,
        faithful_statement: str,
        location: str,
        graph_scope: Optional[str] = None,
    ) -> PINAResult:
        """Propose a Normative Candidate; it stays pending until a human decides."""
        nca_id = self._generate_nca_id(source_document, location)
        cycle = self.state_machine.current_cycle

        candidate = NormativeCandidateRecord(
            nca_id=nca_id,
            source_document=source_document,
            faithful_statement=faithful_statement,
            location=location,
            graph_scope=graph_scope,
            cycle_id=cycle.cycle_id if cycle else None,
        )
        self._candidates[nca_id] = candidate
        if cycle:
            cycle.nca_pending += 1

        if self.ledger:
            self.ledger.add_entry(
                entry_type=LedgerEntryType.NORMATIVE_CANDIDATE,
                content=faithful_statement,
                gf_id=nca_id,
                metadata={
                    "source": source_document,
                    "location": location,
                    "graph_scope": graph_scope,
                },
                cycle_id=candidate.cycle_id,
            )

        return PINAResult(
            success=True,
            nca_id=nca_id,
            message=(
                f"{nca_id} proposed. Awaiting human decision: "
                "ACCEPT (A), REJECT (B), DEFER (C) <reason>"
            ),
        )

    def decide(
        self, nca_id: str, decision: str, reason: Optional[str] = None
    ) -> PINAResult:
        """Record the human decision (REGIME-4 syntax; letters accepted)."""
        if nca_id not in self._candidates:
            return PINAResult(
                success=False, nca_id=nca_id, message=f"NCA {nca_id} not found"
            )

        resolved = _DECISION_ALIASES.get(decision.strip().upper())
        if resolved is None:
            return PINAResult(
                success=False,
                nca_id=nca_id,
                message=(
                    f"Invalid decision '{decision}'. "
                    "Use ACCEPT/A, REJECT/B, or DEFER/C."
                ),
            )

        candidate = self._candidates[nca_id]
        candidate.decision = resolved
        candidate.reason = reason
        candidate.decided_at = datetime.now()

        cycle = self.state_machine.current_cycle
        if cycle and cycle.nca_pending > 0:
            cycle.nca_pending -= 1

        if resolved == PINADecision.INCORPORATE:
            if nca_id not in self._active_invariants:
                self._active_invariants.append(nca_id)
            consequence = "Rule is now an ACTIVE INVARIANT governing reasoning"
        elif resolved == PINADecision.DO_NOT_INCORPORATE:
            if nca_id in self._active_invariants:
                self._active_invariants.remove(nca_id)
            consequence = (
                "Rule remains external text; may be discussed, cannot govern reasoning"
            )
        else:
            consequence = "Rule remains unresolved; dependent reasoning is blocked"

        if self.ledger:
            self.ledger.add_entry(
                entry_type=LedgerEntryType.PINA_DECISION,
                content=f"PINA decision: {resolved.value} for {nca_id}",
                gf_id=nca_id,
                metadata={
                    "decision": resolved.value,
                    "reason": reason,
                    "consequence": consequence,
                },
                cycle_id=candidate.cycle_id,
            )

        return PINAResult(
            success=True,
            nca_id=nca_id,
            message=consequence,
            decision=resolved.value,
            active_invariants=len(self._active_invariants),
        )

    def get_pending(self) -> list[dict]:
        """Undecided candidates -- silence keeps them here, never resolves them."""
        return [
            self._candidate_summary(c)
            for c in self._candidates.values()
            if c.decision is None
        ]

    def get_stale_pending(self, hours: int = 24) -> list[dict]:
        """REGIME-7: pending candidates older than `hours` (DEFER-loop guard)."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            self._candidate_summary(c)
            for c in self._candidates.values()
            if c.decision is None and c.created_at < cutoff
        ]

    def _candidate_summary(self, c: NormativeCandidateRecord) -> dict:
        return {
            "nca_id": c.nca_id,
            "source_document": c.source_document,
            "faithful_statement": c.faithful_statement,
            "location": c.location,
            "graph_scope": c.graph_scope,
            "created_at": c.created_at.isoformat(),
        }

    def get_active_invariants(self) -> list[dict]:
        return [
            {
                "nca_id": nca_id,
                "source_document": self._candidates[nca_id].source_document,
                "faithful_statement": self._candidates[nca_id].faithful_statement,
            }
            for nca_id in self._active_invariants
            if nca_id in self._candidates
        ]

    def is_invariant(self, nca_id: str) -> bool:
        return nca_id in self._active_invariants

    def get_status(self) -> dict:
        pending = self.get_pending()
        return {
            "pending_candidates": len(pending),
            "pending_list": pending,
            "stale_pending": len(self.get_stale_pending()),
            "active_invariants": len(self._active_invariants),
            "active_list": self._active_invariants,
        }
