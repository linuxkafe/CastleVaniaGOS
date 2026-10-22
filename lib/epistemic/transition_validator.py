"""
Claim State Machine — Transition validation for epistemic claims

Defines valid states and transitions for claims in the governance regime.

State diagram:
    derived -> audited -> stabilized -> promoted
                ↘ contested ↗
                deprecated/archived
"""

from dataclasses import dataclass
from typing import Set, Dict, Optional, Iterable

from .epistemic_objects import (
    Proposition,
    PropositionDependency,
    FalsificationCondition,
    RelationType,
    FalsificationStatus,
)


ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "derived": {"audited", "working", "stabilized"},
    "working": {"audited", "stabilized"},
    "audited": {"stabilized", "contested"},
    "stabilized": {"promoted", "contested"},
    "promoted": {"deprecated", "contested"},
    "contested": {"audited", "deprecated", "archived"},
    "deprecated": {"archived"},
    "archived": set(),
}

VALID_STATES = set(ALLOWED_TRANSITIONS.keys())


class TransitionError(Exception):
    pass


@dataclass
class ClaimTransitionContext:
    claim_id: str
    from_status: str
    to_status: str
    has_audit: bool
    has_artifact_ref: bool = True
    is_contested: bool = False


def validate_transition(ctx: ClaimTransitionContext) -> None:
    """
    Validate if a claim state transition is allowed by governance rules.
    Raises TransitionError if rules are violated.
    """
    if ctx.from_status not in VALID_STATES:
        raise TransitionError(f"Unknown source state: {ctx.from_status}")

    if ctx.to_status not in VALID_STATES:
        raise TransitionError(f"Unknown target state: {ctx.to_status}")

    allowed = ALLOWED_TRANSITIONS.get(ctx.from_status, set())
    if ctx.to_status not in allowed:
        allowed_str = ", ".join(allowed) if allowed else "None"
        raise TransitionError(
            f"Invalid transition: {ctx.from_status} -> {ctx.to_status}. Allowed: {allowed_str}"
        )

    if ctx.to_status == "promoted" and not ctx.has_audit:
        raise TransitionError("Cannot promote a claim without at least one audit registered.")

    if ctx.to_status == "canonical":
        raise TransitionError("State 'canonical' is not supported in this version of the regime.")

    if ctx.from_status == "contested" and ctx.to_status == "promoted":
        raise TransitionError("A contested claim must go through 'audited' before being promoted.")


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Check if a transition is valid without raising an exception."""
    if from_status not in VALID_STATES or to_status not in VALID_STATES:
        return False
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def get_allowed_transitions(from_status: str) -> Set[str]:
    """Get set of allowed target states from a given state."""
    return ALLOWED_TRANSITIONS.get(from_status, set())


def is_terminal_state(status: str) -> bool:
    """Check if a state is terminal (no outgoing transitions)."""
    return len(ALLOWED_TRANSITIONS.get(status, set())) == 0


def requires_audit(to_status: str) -> bool:
    """Check if transitioning to a state requires an audit."""
    return to_status == "promoted"