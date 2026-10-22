"""Smoke tests for ported epistemic modules.

AES T036: covers transition_validator, falsifiability_lint, epistemic_policy.
"""

import pytest

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
from lib.epistemic.epistemic_objects import (
    Proposition,
    PropositionRole,
    PropositionLegitimacy,
    RelationType,
    FalsificationStatus,
    LoopStatus,
    LoopCriticality,
    ClosureType,
    TensionType,
    TensionResolution,
    ArtefactType,
)


# ---------------------------------------------------------- transition_validator


class TestTransitionValidator:
    def test_all_states_defined(self):
        assert "derived" in VALID_STATES
        assert "promoted" in VALID_STATES
        assert "archived" in VALID_STATES

    def test_valid_transition(self):
        assert is_valid_transition("derived", "audited") is True

    def test_invalid_transition(self):
        assert is_valid_transition("derived", "promoted") is False

    def test_validate_transition_happy(self):
        ctx = ClaimTransitionContext(claim_id=1, from_status="audited", to_status="stabilized", has_audit=True)
        validate_transition(ctx)
        assert True, "validate_transition should not raise for valid transition"

    def test_validate_transition_blocks_contested_to_promoted(self):
        ctx = ClaimTransitionContext(claim_id=1, from_status="contested", to_status="promoted", has_audit=True)
        with pytest.raises(TransitionError, match="Invalid transition: contested -> promoted"):
            validate_transition(ctx)

    def test_validate_transition_requires_audit_for_promoted(self):
        ctx = ClaimTransitionContext(claim_id=1, from_status="stabilized", to_status="promoted", has_audit=False)
        with pytest.raises(TransitionError, match="without at least one audit"):
            validate_transition(ctx)

    def test_archived_is_terminal(self):
        assert is_terminal_state("archived") is True

    def test_requires_audit(self):
        assert requires_audit("promoted") is True
        assert requires_audit("audited") is False

    def test_get_allowed_transitions(self):
        assert "contested" in get_allowed_transitions("promoted")
        assert "deprecated" in get_allowed_transitions("promoted")


# ------------------------------------------------------------ falsifiability_lint


class TestFalsifiabilityLint:
    def test_lint_result_is_dataclass(self):
        r = LintResult(ok=["a"], conditional=["b"], failed=["c"])
        assert r.ok == ["a"]
        assert r.failed == ["c"]

    def test_extract_conditions_from_foundational(self):
        props = [
            Proposition(id="F1", statement="water boils at 100C", role=PropositionRole.FOUNDATIONAL, gmif_type="M6")
        ]
        conditions = extract_falsification_conditions(props)
        assert len(conditions) == 1
        assert conditions[0].proposition_id == "F1"

    def test_extract_conditions_from_derived_without_support(self):
        props = [
            Proposition(id="D1", statement="derived claim", role=PropositionRole.DERIVED, gmif_type="M6")
        ]
        conditions = extract_falsification_conditions(props)
        assert len(conditions) == 1

    def test_extract_conditions_skips_derived_with_support(self):
        props = [
            Proposition(id="D1", statement="derived claim", role=PropositionRole.DERIVED, gmif_type="M6", supporting_claim_ids=["F1"])
        ]
        conditions = extract_falsification_conditions(props)
        assert len(conditions) == 0

    def test_run_proposition_lint(self):
        props = [
            Proposition(id="F1", statement="foundational", role=PropositionRole.FOUNDATIONAL, gmif_type="M6"),
            Proposition(id="D1", statement="derived", role=PropositionRole.DERIVED, gmif_type="M6", supporting_claim_ids=["F1"]),
        ]
        result = run_proposition_lint(props)
        assert "F1" in result.conditional  # no falsification status set
        assert "D1" in result.ok

    def test_check_foundational_boundaries(self):
        props = [
            Proposition(id="F1", statement="test", role=PropositionRole.FOUNDATIONAL, gmif_type="M6")
        ]
        issues = check_foundational_boundaries(props)
        assert any("F1" in i for i in issues)

    def test_check_derived_support_ok(self):
        props = [
            Proposition(id="D1", statement="test", role=PropositionRole.DERIVED, gmif_type="M6", supporting_claim_ids=["F1"])
        ]
        assert check_derived_support(props) == []

    def test_check_derived_support_missing(self):
        props = [
            Proposition(id="D1", statement="test", role=PropositionRole.DERIVED, gmif_type="M6")
        ]
        issues = check_derived_support(props)
        assert any("D1" in i for i in issues)

    def test_evaluate_lint_for_promotion(self):
        props = [
            Proposition(id="F1", statement="test", role=PropositionRole.FOUNDATIONAL, gmif_type="M6")
        ]
        status, reasons = evaluate_lint_for_promotion(props)
        assert status == "BLOCK"


# -------------------------------------------------------------- epistemic_policy


class TestEpistemicPolicy:
    def test_policy_values_are_reasonable(self):
        assert 0 < POLICY["min_consensus"] < 1
        assert 0 < POLICY["max_fragility"] < 1
        assert POLICY["evidence_threshold"] > 0
        assert POLICY["m4_block_threshold"] > 0

    def test_evaluate_no_claims_blocks(self):
        decision, reason = evaluate_epistemic_policy([])
        assert decision == "block"
        assert reason == "no_claims"

    def test_single_claim_factoid_allowed(self):
        decision, reason = evaluate_epistemic_policy([{"id": "c1", "source_id": "s1"}])
        assert decision == "allow"

    def test_block_on_contradiction(self):
        claims = [{"id": f"c{i}"} for i in range(10)]
        contradictions = [{"id": f"x{i}"} for i in range(5)]
        decision, reason = evaluate_epistemic_policy(claims, contradictions=contradictions)
        assert decision == "block"

    def test_block_on_cycles(self):
        claims = [{"id": "c1"}, {"id": "c2", "source_id": "s2"}, {"id": "c3", "source_id": "s3"}]
        lint = {"cycles": ["c1 -> c2 -> c1"]}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert reason == "circular_reasoning"

    def test_hallucinated_edges_block(self):
        claims = [{"id": "c1"}, {"id": "c2", "source_id": "s2"}, {"id": "c3", "source_id": "s3"}]
        lint = {"hallucinated_edges": ["c1->c2"]}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert reason == "hallucinated_relations"


# -------------------------------------------------------- vocabulary conformance (T036 AC6)


class TestVocabularyConformance:
    """Assert the enums preserve the exact spelling from the GF prototype.

    A conformance test does not *prove* correctness — it catches accidental
    renames during the next refactor. If you intentionally rename an enum
    member, update both strings here and in all call sites.
    """

    def test_proposition_role_values(self):
        assert PropositionRole.FOUNDATIONAL.value == "foundational"
        assert PropositionRole.ASSUMPTION.value == "assumption"
        assert PropositionRole.DERIVED.value == "derived"
        assert PropositionRole.CONSTRAINT.value == "constraint"

    def test_relation_type_values(self):
        assert RelationType.SUPPORTS.value == "supports"
        assert RelationType.DEPENDS_ON.value == "depends_on"
        assert RelationType.CONTRADICTS.value == "contradicts"
        assert RelationType.NARROWS.value == "narrows"
        assert RelationType.EXTENDS.value == "extends"
        # T302 (MINOR-1): CONSTRAINS é distinto de DEPENDS_ON (antes degradava
        # silenciosamente, invertendo a direcção de risco no propagator).
        assert RelationType.CONSTRAINS.value == "constrains"
        assert RelationType.CONSTRAINS != RelationType.DEPENDS_ON

    def test_loop_status_values(self):
        assert LoopStatus.OPEN.value == "OPEN"
        assert LoopStatus.CLOSED.value == "CLOSED"
        assert LoopStatus.SUSPENDED.value == "SUSPENDED"
        assert LoopStatus.BLOCKED.value == "BLOCKED"
        assert LoopStatus.PROMOTED.value == "PROMOTED"
        assert LoopStatus.SCHEDULED.value == "SCHEDULED"

    def test_loop_criticality_values(self):
        assert LoopCriticality.HIGH.value == "high"
        assert LoopCriticality.MEDIUM.value == "medium"
        assert LoopCriticality.LOW.value == "low"

    def test_closure_type_values(self):
        assert ClosureType.EVIDENCE_BASED.value == "evidence_based"
        assert ClosureType.TRUSTED_COMMITMENT.value == "trusted_commitment"
        assert ClosureType.SUSPENSION.value == "suspension"
        assert ClosureType.BLOCKED.value == "blocked"

    def test_falsification_status_values(self):
        assert FalsificationStatus.PENDING.value == "pending"
        assert FalsificationStatus.VALIDATED.value == "validated"
        assert FalsificationStatus.FAILED.value == "failed"
        assert FalsificationStatus.NOT_APPLICABLE.value == "not_applicable"

    def test_tension_type_values(self):
        assert TensionType.CONTRADICTION.value == "contradiction"
        assert TensionType.UNCERTAINTY.value == "uncertainty"
        assert TensionType.INCOMPLETENESS.value == "incompleteness"
        assert TensionType.COMPETING.value == "competing"

    def test_tension_resolution_values(self):
        assert TensionResolution.UNRESOLVED.value == "unresolved"
        assert TensionResolution.RESOLVED.value == "resolved"
        assert TensionResolution.SUSPENDED.value == "suspended"
        assert TensionResolution.ACCEPTED.value == "accepted"

    def test_artefact_type_values(self):
        assert ArtefactType.DOCUMENTO_SOMBRA.value == "DocumentoSombra"
        assert ArtefactType.OBJETO_DIGITAL.value == "ObjetoDigital"
        assert ArtefactType.CAPSULA_CONCEPTUAL.value == "CapsulaConceptual"

    def test_proposition_legitimacy_values(self):
        assert PropositionLegitimacy.SUSPENDED.value == "LEGITIMACY_SUSPENDED"
        assert PropositionLegitimacy.ASSERTED.value == "LEGITIMACY_ASSERTED"

    def test_proposition_legitimacy_default_is_suspended(self):
        p = Proposition(id="x", statement="x", role=PropositionRole.DERIVED, gmif_type="M6")
        assert p.legitimacy == PropositionLegitimacy.SUSPENDED
