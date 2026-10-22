"""
Loop Closure - Open loop management for epistemic governance

From prototype: manages unresolved questions/hypotheses with closure policies.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import uuid

from .epistemic_objects import (
    OpenLoop,
    ClosureRecord,
    TrustedCommitment,
    LoopStatus,
    LoopCriticality,
    ClosureType,
    TensionRecord,
    Proposition,
    PropositionRole,
    TensionResolution,
)


def generate_loop_id() -> str:
    return f"LOOP-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:6]}"


def open_loop_from_claim(
    claim_id: str, _claim_text: str, criticality: LoopCriticality = LoopCriticality.MEDIUM
) -> OpenLoop:
    """Create an open loop from a claim."""
    return OpenLoop(
        id=generate_loop_id(),
        source_type="claim",
        source_id=claim_id,
        status=LoopStatus.OPEN,
        criticality=criticality,
        closure_policy="claim_validation",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )


def open_loop_from_proposition(
    proposition: Proposition, criticality: LoopCriticality = LoopCriticality.MEDIUM
) -> OpenLoop:
    """Create an open loop from a proposition."""
    return OpenLoop(
        id=generate_loop_id(),
        source_type="proposition",
        source_id=proposition.id,
        status=LoopStatus.OPEN,
        criticality=criticality,
        closure_policy="proposition_validation",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )


def open_loop_from_tension(
    tension: TensionRecord, criticality: Optional[LoopCriticality] = None
) -> OpenLoop:
    """Create an open loop from a tension record."""
    if criticality is None:
        if tension.severity >= 3:
            criticality = LoopCriticality.HIGH
        elif tension.severity >= 2:
            criticality = LoopCriticality.MEDIUM
        else:
            criticality = LoopCriticality.LOW

    return OpenLoop(
        id=generate_loop_id(),
        source_type="tension",
        source_id=tension.id,
        status=LoopStatus.OPEN,
        criticality=criticality,
        closure_policy="tension_resolution",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )


def close_loop(
    loop: OpenLoop, closure_type: ClosureType, evidence: Optional[str] = None
) -> ClosureRecord:
    """Close an open loop with evidence-based closure."""
    loop.status = LoopStatus.CLOSED
    loop.updated_at = datetime.now().isoformat()

    return ClosureRecord(
        loop_id=loop.id,
        closure_type=closure_type,
        evidence=evidence,
        closed_at=datetime.now().isoformat(),
    )


def suspend_loop(loop: OpenLoop, reason: str) -> ClosureRecord:
    """Suspend an open loop."""
    loop.status = LoopStatus.SUSPENDED
    loop.updated_at = datetime.now().isoformat()

    return ClosureRecord(
        loop_id=loop.id,
        closure_type=ClosureType.SUSPENSION,
        evidence=reason,
        closed_at=datetime.now().isoformat(),
    )


def block_loop(loop: OpenLoop, reason: str) -> ClosureRecord:
    """Block an open loop."""
    loop.status = LoopStatus.BLOCKED
    loop.updated_at = datetime.now().isoformat()

    return ClosureRecord(
        loop_id=loop.id,
        closure_type=ClosureType.BLOCKED,
        evidence=reason,
        closed_at=datetime.now().isoformat(),
    )


def register_trusted_commitment(
    loop: OpenLoop, commitment_text: str, committed_by: str, materialization: str
) -> TrustedCommitment:
    """Register a trusted commitment for a loop."""
    loop.trusted_commitment = {
        "text": commitment_text,
        "committed_by": committed_by,
        "materialization": materialization,
    }
    loop.status = LoopStatus.SCHEDULED
    loop.updated_at = datetime.now().isoformat()

    return TrustedCommitment(
        id=f"TC-{uuid.uuid4().hex[:6]}",
        claim_id=loop.source_id,
        commitment_text=commitment_text,
        materialization=materialization,
        committed_by=committed_by,
        created_at=datetime.now().isoformat(),
    )


def can_promote(loops: List[OpenLoop]) -> Tuple[bool, List[str]]:
    """Check if loops can be promoted based on critical open loops."""
    blocked_loops = [
        l for l in loops if l.status == LoopStatus.OPEN and l.criticality == LoopCriticality.HIGH
    ]

    if blocked_loops:
        reasons = [f"Critical loop open: {l.id}" for l in blocked_loops]
        return False, reasons

    return True, []


def evaluate_loops_for_promotion(
    loops: List[OpenLoop], _trusted_commitments: Optional[List[TrustedCommitment]] = None
) -> Tuple[str, List[str]]:
    """
    Evaluate if loops can be promoted.

    Returns:
        Tuple of (status, reasons) where status is "PASS", "CONDITIONAL", or "BLOCK"
    """
    can_promote_flag, reasons = can_promote(loops)

    if not can_promote_flag:
        return "BLOCK", reasons

    open_loops = [l for l in loops if l.status == LoopStatus.OPEN]
    if open_loops:
        return "CONDITIONAL", [f"Open loops: {len(open_loops)}"]

    return "PASS", []


def apply_closure_policy(
    loop: OpenLoop, policy: str, evidence: Optional[str] = None, committed_by: Optional[str] = None
) -> ClosureRecord:
    """
    Apply a closure policy to an open loop.

    Args:
        loop: The open loop to close
        policy: One of "evidence_based", "trusted_commitment", "suspension", "block"
        evidence: Evidence for the closure
        committed_by: Required for "trusted_commitment" policy
    """
    if policy == "evidence_based":
        return close_loop(loop, ClosureType.EVIDENCE_BASED, evidence)

    elif policy == "trusted_commitment":
        if not committed_by:
            raise ValueError("committed_by required for trusted_commitment policy")

        register_trusted_commitment(
            loop,
            commitment_text=evidence or "",
            committed_by=committed_by,
            materialization="materialized",
        )
        return close_loop(loop, ClosureType.TRUSTED_COMMITMENT, evidence)

    elif policy == "suspension":
        return suspend_loop(loop, evidence or "suspended")

    elif policy == "block":
        return block_loop(loop, evidence or "blocked")

    else:
        return close_loop(loop, ClosureType.EVIDENCE_BASED, evidence or "default closure")


def get_loops_by_criticality(loops: List[OpenLoop]) -> Dict[str, List[OpenLoop]]:
    """Group loops by criticality level."""
    return {
        "high": [l for l in loops if l.criticality == LoopCriticality.HIGH],
        "medium": [l for l in loops if l.criticality == LoopCriticality.MEDIUM],
        "low": [l for l in loops if l.criticality == LoopCriticality.LOW],
    }


def get_open_critical_loops(loops: List[OpenLoop]) -> List[OpenLoop]:
    """Get all open loops with HIGH criticality."""
    return [
        l for l in loops if l.status == LoopStatus.OPEN and l.criticality == LoopCriticality.HIGH
    ]


def get_loop_summary(loops: List[OpenLoop]) -> Dict[str, Any]:
    """Get summary statistics of loops."""
    return {
        "total": len(loops),
        "open": len([l for l in loops if l.status == LoopStatus.OPEN]),
        "scheduled": len([l for l in loops if l.status == LoopStatus.SCHEDULED]),
        "suspended": len([l for l in loops if l.status == LoopStatus.SUSPENDED]),
        "blocked": len([l for l in loops if l.status == LoopStatus.BLOCKED]),
        "closed": len([l for l in loops if l.status == LoopStatus.CLOSED]),
        "promoted": len([l for l in loops if l.status == LoopStatus.PROMOTED]),
        "critical_high": len([l for l in loops if l.criticality == LoopCriticality.HIGH]),
        "critical_medium": len([l for l in loops if l.criticality == LoopCriticality.MEDIUM]),
        "critical_low": len([l for l in loops if l.criticality == LoopCriticality.LOW]),
    }


def summarize_closure_state(loops: List[OpenLoop], closures: List[ClosureRecord]) -> Dict[str, Any]:
    """Summarize the closure state of loops."""
    loop_summary = get_loop_summary(loops)

    closure_summary = {
        "total": len(closures),
        "evidence_based": len(
            [c for c in closures if c.closure_type == ClosureType.EVIDENCE_BASED]
        ),
        "trusted_commitment": len(
            [c for c in closures if c.closure_type == ClosureType.TRUSTED_COMMITMENT]
        ),
        "suspension": len([c for c in closures if c.closure_type == ClosureType.SUSPENSION]),
        "blocked": len([c for c in closures if c.closure_type == ClosureType.BLOCKED]),
    }

    return {
        "loops": loop_summary,
        "closures": closure_summary,
        "can_promote": can_promote(loops)[0],
    }


def create_loops_from_tensions(tensions: List[TensionRecord]) -> List[OpenLoop]:
    """Create open loops from unresolved tensions."""
    loops = []
    for tension in tensions:
        if tension.resolution_status != TensionResolution.RESOLVED:
            loop = open_loop_from_tension(tension)
            loops.append(loop)
    return loops
