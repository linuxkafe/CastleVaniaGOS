"""
Premise Propagator — premise-fallen → downstream reopen (cascade)

SOURCE: Ported from Grilo Falante v3 (T036). This is the CANONICAL copy.
The GF repo holds the historical version; all active development is in AES.

The missing edge in the regime. The atoms already exist:
- `Proposition.role` (FOUNDATIONAL / ASSUMPTION / DERIVED / CONSTRAINT)
- `PropositionDependency` with `RelationType.DEPENDS_ON` / `SUPPORTS`
- `FalsificationCondition` per proposition (the Popperian falsifier)
- `OpenLoop` + `loop_closure.can_promote()` (blocks promotion on HIGH open loops)
- the claim state machine (`promoted -> contested` is a legal reopen edge)

What was NOT wired: when a premise FALLS — a FalsificationCondition flips to
FAILED, or a foundational/assumption proposition is explicitly contested —
nothing walked the DEPENDS_ON / SUPPORTS edges to reopen the DERIVED propositions
that rested on it. This module closes exactly that gap and nothing more.

It does NOT decide truth and it does NOT reconcile (R4 of the regime). It opens
HIGH-criticality OpenLoops over the affected propositions WITH provenance, and it
*proposes* — never applies — claim contestations. The existing
`loop_closure.can_promote()` then blocks promotion while those critical loops are
open. Human authority (PINA / review) resolves them.

Design decisions (hostile-analysis driven — stated, not hidden):

1. Only LOAD-BEARING relations propagate: DEPENDS_ON and SUPPORTS. CONTRADICTS,
   NARROWS and EXTENDS do NOT cascade. Over-propagation makes the gate noisy and
   trains rubber-stamping — the precise failure the regime exists to prevent.
2. `LEGITIMACY_SUSPENDED` is the INITIAL state of a proposition, not a fall; it is
   never, by itself, a trigger. Triggers are: a FAILED FalsificationCondition, or
   an explicit `contested_ids` signal from the caller (tension resolution / human).
3. Cascade criticality is HIGH across the whole reachable load-bearing closure: a
   fallen premise makes everything that rests on it suspect, and HIGH is what
   `can_promote` blocks on. Noise is controlled by EDGE SELECTION (1), not by
   downgrading criticality of distant dependents — downgrading would let a 2-hop
   dependent of a failed foundational claim be promoted silently.
4. Every opened loop carries a `ReopenRecord` with the propagation path: no reopen
   without provenance (the claim protocol, applied to reopening).
5. Cycle-safe (visited set per seed) and idempotent against existing OPEN loops.

T048: Refactored to use JTMS (Justification-based Truth Maintenance System)
internally. The propagator builds a JTMS from propositions/dependencies, tells
seeds OUT, and emits OpenLoops for OUT nodes. This provides:
- IN/OUT labels (belief semantics)
- Multiple justifications per node (minimal retraction)
- Dependency-directed retraction (premise restoration)
- Odd-cycle NOGOOD detection
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Iterable

from .epistemic_objects import (
    Proposition,
    PropositionDependency,
    RelationType,
    FalsificationCondition,
    FalsificationStatus,
    OpenLoop,
    LoopStatus,
    LoopCriticality,
)
from .loop_closure import generate_loop_id
from .transition_validator import ClaimTransitionContext, is_valid_transition
from .tms import JTMS, NodeLabel


CLOSURE_POLICY_PREMISE_FALLEN = "premise_fallen"


@dataclass
class ReopenRecord:
    """Provenance for a single reopen. No reopen without one."""

    affected_proposition_id: str
    fallen_proposition_id: str
    trigger: str  # e.g. "falsification_failed:FC-...", "contested"
    path: List[str]  # fallen seed -> ... -> affected (in risk-propagation order)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PropagationResult:
    opened_loops: List[OpenLoop]
    reopen_records: List[ReopenRecord]
    affected_proposition_ids: Set[str]
    seeds: Dict[str, str]  # fallen proposition id -> reason


def build_risk_graph(dependencies: Iterable[PropositionDependency]) -> Dict[str, Set[str]]:
    """
    Map each proposition to the set it ENDANGERS if it falls.

    PropositionDependency is `from --relation--> to`.
      - `from DEPENDS_ON to`  : if `to` falls, `from` is at risk  => edge to -> from
      - `from SUPPORTS to`    : if `from falls, `to` is at risk  => edge from -> to
      - `from CONSTRAINS to`  : if `from` (the constraint) falls, `to`
        (the constrained) is at risk => edge from -> to (T302, same direction
        as SUPPORTS but a distinct semantic, kept explicit).
    CONTRADICTS / NARROWS / EXTENDS are not load-bearing here (see design note 1).
    """
    risk: Dict[str, Set[str]] = defaultdict(set)
    for dep in dependencies:
        if dep.relation_type == RelationType.DEPENDS_ON:
            risk[dep.to_proposition].add(dep.from_proposition)
        elif dep.relation_type == RelationType.SUPPORTS:
            risk[dep.from_proposition].add(dep.to_proposition)
        elif dep.relation_type == RelationType.CONSTRAINS:
            # T302 (MINOR-1): if the constraint (`from`) falls, the
            # constrained (`to`) is at risk — same edge direction as SUPPORTS
            # but a distinct semantic, kept explicit (not an alias).
            risk[dep.from_proposition].add(dep.to_proposition)
    return risk


def seed_fallen(
    propositions: Iterable[Proposition],
    falsification_conditions: Iterable[FalsificationCondition],
    contested_ids: Optional[Iterable[str]] = None,
) -> Dict[str, str]:
    """Return {proposition_id: reason} for every premise that has fallen."""
    contested = set(contested_ids or [])
    failed_by_prop: Dict[str, List[str]] = defaultdict(list)
    for fc in falsification_conditions:
        if fc.status == FalsificationStatus.FAILED:
            failed_by_prop[fc.proposition_id].append(fc.id)

    seeds: Dict[str, str] = {}
    known_ids = {p.id for p in propositions}
    for pid, fc_ids in failed_by_prop.items():
        seeds[pid] = f"falsification_failed:{','.join(fc_ids)}"
    for cid in contested:
        seeds.setdefault(cid, "contested")
    # Keep only ids we can reason about, but never drop a contested id the
    # caller explicitly asserted even if it is not in `propositions`.
    return {k: v for k, v in seeds.items() if k in known_ids or k in contested}


def _cascade_nodes(
    propositions: Iterable[Proposition],
    dependencies: Iterable[PropositionDependency],
    seeds: Dict[str, str],
) -> Set[str]:
    """Compute the cascade of affected nodes using the old risk-graph BFS method.
    This ensures behavior-equivalence with the original propagator."""
    risk = build_risk_graph(dependencies)
    propositions = list(propositions)
    known_ids = {p.id for p in propositions}
    
    cascade: Set[str] = set()
    queue = deque(seed_id for seed_id in seeds if seed_id in known_ids)
    while queue:
        node = queue.popleft()
        if node in cascade:
            continue
        cascade.add(node)
        for nxt in risk.get(node, ()):
            if nxt not in cascade and nxt in known_ids:
                queue.append(nxt)
    return cascade


def _build_jtms(
    propositions: Iterable[Proposition],
    dependencies: Iterable[PropositionDependency],
    seeds: Dict[str, str],
    cascade: Set[str],
) -> JTMS:
    """Build a JTMS from propositions and dependencies, then tell seeds OUT.
    Only adds justifications for nodes in the cascade to maintain behavior-equivalence."""
    jtms = JTMS()

    # Add all cascade nodes (includes seeds)
    for node_id in cascade:
        jtms.add_node(node_id)

    # Add justifications from load-bearing dependencies, but only within cascade
    for dep in dependencies:
        if dep.relation_type == RelationType.DEPENDS_ON:
            # from DEPENDS_ON to: if `to` falls, `from` is at risk
            # Justification: to IN -> from IN
            if dep.to_proposition in cascade and dep.from_proposition in cascade:
                jtms.add_justification(
                    antecedents={dep.to_proposition},
                    consequent=dep.from_proposition,
                    jtype="DEPENDS_ON",
                )
        elif dep.relation_type == RelationType.SUPPORTS:
            # from SUPPORTS to: if `from` falls, `to` is at risk
            # Justification: from IN -> to IN
            if dep.from_proposition in cascade and dep.to_proposition in cascade:
                jtms.add_justification(
                    antecedents={dep.from_proposition},
                    consequent=dep.to_proposition,
                    jtype="SUPPORTS",
                )
        elif dep.relation_type == RelationType.CONSTRAINS:
            # T302 (MINOR-1): from CONSTRAINS to — if the constraint (`from`)
            # falls, the constrained (`to`) falls. Same direction as SUPPORTS
            # but a distinct semantic, kept explicit (not an alias).
            if dep.from_proposition in cascade and dep.to_proposition in cascade:
                jtms.add_justification(
                    antecedents={dep.from_proposition},
                    consequent=dep.to_proposition,
                    jtype="CONSTRAINS",
                )
        # CONTRADICTS / NARROWS / EXTENDS are not load-bearing (see design note 1)

    # Tell seeds OUT (premise fallen)
    for seed_id, reason in seeds.items():
        if seed_id in cascade:
            jtms.tell_out(seed_id, reason)

    return jtms


def propagate(
    propositions: Iterable[Proposition],
    dependencies: Iterable[PropositionDependency],
    falsification_conditions: Iterable[FalsificationCondition],
    contested_ids: Optional[Iterable[str]] = None,
    existing_loops: Optional[Iterable[OpenLoop]] = None,
) -> PropagationResult:
    """
    Walk load-bearing edges downstream from every fallen premise and open a
    HIGH-criticality OpenLoop (with provenance) on each affected DERIVED
    proposition. Idempotent against existing OPEN loops; cycle-safe.

    Uses JTMS internally for IN/OUT semantics, multi-justification, and retraction.
    """
    propositions = list(propositions)
    seeds = seed_fallen(propositions, falsification_conditions, contested_ids)

    existing_open = {
        l.source_id for l in (existing_loops or []) if l.status == LoopStatus.OPEN
    }

    cascade = _cascade_nodes(propositions, dependencies, seeds)
    jtms = _build_jtms(propositions, dependencies, seeds, cascade)

    # Collect OUT nodes that are not seeds and not already open
    opened: Dict[str, OpenLoop] = {}
    records: List[ReopenRecord] = []

    # Get labels from JTMS
    labels = jtms.get_all_labels()

    # Build risk graph for path provenance (same as before)
    risk = build_risk_graph(dependencies)

    for seed_id, reason in seeds.items():
        # Find all OUT nodes reachable from this seed via load-bearing edges
        visited: Set[str] = set()
        queue: deque = deque((nxt, [seed_id, nxt]) for nxt in risk.get(seed_id, ()))
        while queue:
            node, path = queue.popleft()
            if node in visited:
                continue
            visited.add(node)

            # A node that is itself a fallen seed is handled as its own seed;
            # do not open a dependent-loop on it, but keep propagating through it.
            is_seed = node in seeds
            if not is_seed and labels.get(node) == NodeLabel.OUT and node not in opened and node not in existing_open:
                opened[node] = OpenLoop(
                    id=generate_loop_id(),
                    source_type="proposition",
                    source_id=node,
                    status=LoopStatus.OPEN,
                    criticality=LoopCriticality.HIGH,
                    closure_policy=CLOSURE_POLICY_PREMISE_FALLEN,
                )
                records.append(
                    ReopenRecord(
                        affected_proposition_id=node,
                        fallen_proposition_id=seed_id,
                        trigger=reason,
                        path=path,
                    )
                )

            for nxt in risk.get(node, ()):
                if nxt not in visited:
                    queue.append((nxt, path + [nxt]))

    return PropagationResult(
        opened_loops=list(opened.values()),
        reopen_records=records,
        affected_proposition_ids=set(opened.keys()),
        seeds=seeds,
    )


def retract(
    propositions: Iterable[Proposition],
    dependencies: Iterable[PropositionDependency],
    falsification_conditions: Iterable[FalsificationCondition],
    retracted_seed_id: str,
    existing_loops: Optional[Iterable[OpenLoop]] = None,
) -> PropagationResult:
    """
    Retract a previously fallen premise (e.g., its falsification condition flipped
    from FAILED back to UNKNOWN). Returns the set of loops that should be CLOSED
    (nodes that are now IN again).

    Uses JTMS dependency-directed retraction: removes the justification corresponding
    to the retracted seed, recomputes labels, and returns affected nodes.
    """
    propositions = list(propositions)
    seeds = seed_fallen(propositions, falsification_conditions)

    # Build cascade including the retracted seed (it was previously fallen)
    # so that its dependents are included in the JTMS
    all_seeds = dict(seeds)
    all_seeds[retracted_seed_id] = "retracted"
    cascade = _cascade_nodes(propositions, dependencies, all_seeds)
    jtms = _build_jtms(propositions, dependencies, all_seeds, cascade)

    # Tell the retracted seed IN (it was previously OUT)
    jtms.tell_in(retracted_seed_id)

    # Get new labels
    labels = jtms.get_all_labels()

    # Nodes that are now IN but were previously OUT (loops to close)
    closed_nodes = {nid for nid, lbl in labels.items() if lbl == NodeLabel.IN}

    # Build risk graph for provenance
    risk = build_risk_graph(dependencies)

    # Find which seeds led to which OUT nodes (for record keeping)
    # Simplified: we just return the closed nodes
    records = []
    for node_id in closed_nodes:
        if node_id not in seeds:
            records.append(
                ReopenRecord(
                    affected_proposition_id=node_id,
                    fallen_proposition_id=retracted_seed_id,
                    trigger=f"retracted:{retracted_seed_id}",
                    path=[retracted_seed_id, node_id],
                )
            )

    return PropagationResult(
        opened_loops=[],  # No new loops opened on retraction
        reopen_records=records,
        affected_proposition_ids=closed_nodes,
        seeds=seeds,
    )


def propose_claim_contestations(
    affected_proposition_ids: Iterable[str],
    claim_status_by_prop: Dict[str, "tuple[int | str, str]"],
) -> List[ClaimTransitionContext]:
    """
    Propose (never apply) `promoted -> contested` transitions for the claims whose
    propositions were reopened. The caller / PINA / human applies them. Only
    proposes transitions the state machine already deems legal.

    `claim_status_by_prop`: {proposition_id: (claim_id, current_status)}
    """
    proposals: List[ClaimTransitionContext] = []
    for pid in affected_proposition_ids:
        entry = claim_status_by_prop.get(pid)
        if not entry:
            continue
        claim_id, status = entry
        if status == "promoted" and is_valid_transition("promoted", "contested"):
            proposals.append(
                ClaimTransitionContext(
                    claim_id=claim_id,
                    from_status="promoted",
                    to_status="contested",
                    has_audit=True,
                )
            )
    return proposals