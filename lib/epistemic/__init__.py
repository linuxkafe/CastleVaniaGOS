"""
lib.epistemic — AES-native epistemic core (ported from Grilo Falante v3).

This package is the canonical home of the epistemic governance regime.
It was ported from Grilo Falante (https://github.com/rodolfomatos/grilo_falante)
as part of AES T036 (ADR-001 unification). The GF repo is the upstream;
this package is the source of truth for the epistemic core.

Imports should use the full package path:
    from lib.epistemic.epistemic_objects import Proposition, OpenLoop
    from lib.epistemic.loop_closure import can_promote
"""

from lib.epistemic.epistemic_objects import (
    PropositionRole,
    PropositionLegitimacy,
    RelationType,
    TensionType,
    TensionResolution,
    LoopStatus,
    LoopCriticality,
    ClosureType,
    FalsificationStatus,
    ArtefactType,
    FalsificationCondition,
    Proposition,
    PropositionDependency,
    TensionRecord,
    OpenLoop,
    ClosureRecord,
    TrustedCommitment,
    Artefact,
)

from lib.epistemic.loop_closure import (
    generate_loop_id,
    open_loop_from_claim,
    open_loop_from_proposition,
    open_loop_from_tension,
    close_loop,
    suspend_loop,
    block_loop,
    register_trusted_commitment,
    can_promote,
    evaluate_loops_for_promotion,
    apply_closure_policy,
    get_loops_by_criticality,
    get_open_critical_loops,
    get_loop_summary,
    summarize_closure_state,
    create_loops_from_tensions,
)

from lib.epistemic.transition_validator import (
    ALLOWED_TRANSITIONS,
    VALID_STATES,
    TransitionError,
    ClaimTransitionContext,
    validate_transition,
    is_valid_transition,
    get_allowed_transitions,
    is_terminal_state,
    requires_audit,
)

from lib.epistemic.falsifiability_lint import (
    LintResult,
    extract_falsification_conditions,
    run_proposition_lint,
    check_foundational_boundaries,
    check_derived_support,
    evaluate_lint_for_promotion,
)

from lib.epistemic.epistemic_policy import (
    POLICY,
    evaluate_epistemic_policy,
)

from lib.epistemic.propagator import (
    ReopenRecord,
    PropagationResult,
    build_risk_graph,
    seed_fallen,
    propagate,
    propose_claim_contestations,
)

__all__ = [
    "PropositionRole",
    "PropositionLegitimacy",
    "RelationType",
    "TensionType",
    "TensionResolution",
    "LoopStatus",
    "LoopCriticality",
    "ClosureType",
    "FalsificationStatus",
    "ArtefactType",
    "FalsificationCondition",
    "Proposition",
    "PropositionDependency",
    "TensionRecord",
    "OpenLoop",
    "ClosureRecord",
    "TrustedCommitment",
    "Artefact",
    "generate_loop_id",
    "open_loop_from_claim",
    "open_loop_from_proposition",
    "open_loop_from_tension",
    "close_loop",
    "suspend_loop",
    "block_loop",
    "register_trusted_commitment",
    "can_promote",
    "evaluate_loops_for_promotion",
    "apply_closure_policy",
    "get_loops_by_criticality",
    "get_open_critical_loops",
    "get_loop_summary",
    "summarize_closure_state",
    "create_loops_from_tensions",
    "ALLOWED_TRANSITIONS",
    "VALID_STATES",
    "TransitionError",
    "ClaimTransitionContext",
    "validate_transition",
    "is_valid_transition",
    "get_allowed_transitions",
    "is_terminal_state",
    "requires_audit",
    "LintResult",
    "extract_falsification_conditions",
    "run_proposition_lint",
    "check_foundational_boundaries",
    "check_derived_support",
    "evaluate_lint_for_promotion",
    "POLICY",
    "evaluate_epistemic_policy",
    "ReopenRecord",
    "PropagationResult",
    "build_risk_graph",
    "seed_fallen",
    "propagate",
    "propose_claim_contestations",
]
