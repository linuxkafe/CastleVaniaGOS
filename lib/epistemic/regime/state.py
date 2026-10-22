"""Regime state machine (ported from Grilo Falante v3).

Lifecycle: INACTIVE -> LOADED -> ACTIVE -> GOVERNING <-> HIBERNATED.
ACTIVE is reachable only via the ACORDAR ritual; GOVERNING only from ACTIVE --
direct jumps are refused, because bypassing the wake-up ritual was one of the
state-machine inconsistencies found by v3.0's hostile analysis.

GMIFLevel is deliberately NOT ported here: the source enum was a third
conflicting GMIF naming variant; GMIF belongs to T010/T014 under decision D1.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


class LegitimacyState(Enum):
    SUSPENDED = "LEGITIMACY_SUSPENDED"
    ASSERTED = "LEGITIMACY_ASSERTED"


class ValidationState(Enum):
    ACCEPT = "ACCEPT"
    CONDITIONAL = "CONDITIONAL"
    REJECT = "REJECT"
    REEXECUTE = "REEXECUTE"


class CycleState(Enum):
    INACTIVE = "INACTIVE"
    LOADED = "LOADED"
    ACTIVE = "ACTIVE"
    GOVERNING = "GOVERNING"
    HIBERNATED = "HIBERNATED"


@dataclass
class CycleContext:
    cycle_id: str
    state: CycleState = CycleState.INACTIVE
    started_at: datetime = field(default_factory=datetime.now)
    last_transition: Optional[datetime] = None
    current_graph: Optional[str] = None
    current_node: Optional[str] = None
    claims_count: int = 0
    nca_pending: int = 0
    is_exploratory: bool = True
    legitimacy_declared: bool = False
    temporal_anchor: Optional[str] = None
    intention: Optional[str] = None
    ledger_entry_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "last_transition": (
                self.last_transition.isoformat() if self.last_transition else None
            ),
            "current_graph": self.current_graph,
            "current_node": self.current_node,
            "claims_count": self.claims_count,
            "nca_pending": self.nca_pending,
            "is_exploratory": self.is_exploratory,
            "legitimacy_declared": self.legitimacy_declared,
            "temporal_anchor": self.temporal_anchor,
            "intention": self.intention,
        }


_TRANSITIONS = {
    CycleState.INACTIVE: [CycleState.LOADED],
    CycleState.LOADED: [CycleState.ACTIVE, CycleState.INACTIVE],
    CycleState.ACTIVE: [CycleState.GOVERNING, CycleState.LOADED],
    CycleState.GOVERNING: [CycleState.HIBERNATED, CycleState.ACTIVE],
    CycleState.HIBERNATED: [CycleState.GOVERNING],
}


class StateMachine:
    """Manages regime cycle transitions; invalid transitions return False."""

    def __init__(self):
        self.current_cycle: Optional[CycleContext] = None

    def start_cycle(self) -> CycleContext:
        self.current_cycle = CycleContext(cycle_id=self._generate_cycle_id())
        self.transition_to(CycleState.LOADED)
        return self.current_cycle

    def transition_to(self, new_state: CycleState) -> bool:
        if self.current_cycle is None:
            return False
        if new_state not in _TRANSITIONS.get(self.current_cycle.state, []):
            return False
        self.current_cycle.state = new_state
        self.current_cycle.last_transition = datetime.now()
        return True

    def load(self) -> bool:
        if self.current_cycle is None:
            self.start_cycle()
        return self.current_cycle.state == CycleState.LOADED

    def activate(self) -> bool:
        return self.transition_to(CycleState.ACTIVE)

    def govern(self) -> bool:
        return self.transition_to(CycleState.GOVERNING)

    def hibernate(self) -> bool:
        return self.transition_to(CycleState.HIBERNATED)

    def resume(self) -> bool:
        if self.current_cycle and self.current_cycle.state == CycleState.HIBERNATED:
            return self.transition_to(CycleState.GOVERNING)
        return False

    def end_cycle(self):
        if self.current_cycle:
            self.current_cycle.state = CycleState.INACTIVE

    def can_claim(self) -> bool:
        return self.current_cycle is not None and self.current_cycle.state in (
            CycleState.ACTIVE,
            CycleState.GOVERNING,
        )

    def can_promote(self) -> bool:
        if not self.current_cycle:
            return False
        return (
            not self.current_cycle.is_exploratory
            and self.current_cycle.legitimacy_declared
        )

    def set_exploratory(self, is_exploratory: bool):
        if self.current_cycle:
            self.current_cycle.is_exploratory = is_exploratory

    def declare_legitimacy(self, declared: bool = True):
        if self.current_cycle:
            self.current_cycle.legitimacy_declared = declared

    def set_position(self, graph_id: str, node_id: str):
        if self.current_cycle:
            self.current_cycle.current_graph = graph_id
            self.current_cycle.current_node = node_id

    def set_temporal_anchor(self, anchor: str):
        if self.current_cycle:
            self.current_cycle.temporal_anchor = anchor

    def set_intention(self, intention: str):
        if self.current_cycle:
            self.current_cycle.intention = intention

    def increment_claims(self):
        if self.current_cycle:
            self.current_cycle.claims_count += 1

    def _generate_cycle_id(self) -> str:
        return f"CYCLE-{datetime.now().strftime('%y%m%d')}-{uuid4().hex[:8]}"

    def get_status(self) -> dict:
        if self.current_cycle is None:
            return {"state": "NO_CYCLE", "active": False}
        return {
            **self.current_cycle.to_dict(),
            "active": self.current_cycle.state != CycleState.INACTIVE,
            "can_claim": self.can_claim(),
            "can_promote": self.can_promote(),
        }
