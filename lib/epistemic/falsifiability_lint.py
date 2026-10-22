"""
Falsifiability Lint - Epistemic validation based on Popperian principles

From prototype: validates propositions against falsification conditions
for promotion readiness.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .epistemic_objects import (
    Proposition,
    FalsificationCondition,
    FalsificationStatus,
    PropositionRole,
    PropositionLegitimacy,
)


@dataclass
class LintResult:
    ok: List[str]
    conditional: List[str]
    failed: List[str]


def extract_falsification_conditions(
    propositions: List[Proposition],
) -> List[FalsificationCondition]:
    """Extract falsification conditions from foundational and derived propositions."""
    conditions = []

    for prop in propositions:
        if prop.role == PropositionRole.FOUNDATIONAL:
            condition = FalsificationCondition(
                id=f"FC-{prop.id[:12]}",
                proposition_id=prop.id,
                condition_text=f"Condition that would falsify: {prop.statement[:100]}",
                evidence_needed="Evidence contradicting the foundational claim",
                status=FalsificationStatus.PENDING,
            )
            conditions.append(condition)

        elif prop.role == PropositionRole.DERIVED:
            supporting = prop.supporting_claim_ids
            if not supporting:
                condition = FalsificationCondition(
                    id=f"FC-{prop.id[:12]}",
                    proposition_id=prop.id,
                    condition_text="Derived proposition without supporting claims",
                    evidence_needed="Chain of evidence from foundational to derived",
                    status=FalsificationStatus.PENDING,
                )
                conditions.append(condition)

    return conditions


def run_proposition_lint(propositions: List[Proposition]) -> LintResult:
    """Run linting on propositions based on falsification principles."""
    result = LintResult(ok=[], conditional=[], failed=[])

    fc_list = extract_falsification_conditions(propositions)
    fc_map = {fc.proposition_id: fc for fc in fc_list}

    for prop in propositions:
        if prop.role == PropositionRole.FOUNDATIONAL:
            fc = fc_map.get(prop.id)

            if fc is None:
                result.conditional.append(prop.id)
                continue

            if fc.status == FalsificationStatus.VALIDATED:
                result.ok.append(prop.id)
            elif fc.status == FalsificationStatus.FAILED:
                result.failed.append(prop.id)
            else:
                result.conditional.append(prop.id)

        elif prop.role == PropositionRole.DERIVED:
            if not prop.supporting_claim_ids:
                result.failed.append(prop.id)
            else:
                result.ok.append(prop.id)
        else:
            result.ok.append(prop.id)

    return result


def check_foundational_boundaries(propositions: List[Proposition]) -> List[str]:
    """Check that foundational propositions have boundary conditions."""
    issues = []

    foundational = [p for p in propositions if p.role == PropositionRole.FOUNDATIONAL]

    for prop in foundational:
        if not prop.falsification_conditions and not prop.boundary_conditions:
            issues.append(f"{prop.id}: no falsification conditions defined")

        if not prop.boundary_conditions:
            issues.append(f"{prop.id}: no boundary conditions defined")

    return issues


def check_derived_support(propositions: List[Proposition]) -> List[str]:
    """Check that derived propositions have supporting claims."""
    issues = []

    derived = [p for p in propositions if p.role == PropositionRole.DERIVED]

    for prop in derived:
        if not prop.supporting_claim_ids:
            issues.append(f"{prop.id}: derived proposition without supporting claims")

    return issues


def evaluate_lint_for_promotion(
    propositions: List[Proposition], lint_result: Optional[LintResult] = None
) -> Tuple[str, List[str]]:
    """
    Evaluate if propositions can be promoted based on lint results.

    Returns:
        Tuple of (status, reasons) where status is "PASS", "CONDITIONAL", or "BLOCK"
    """
    if lint_result is None:
        lint_result = run_proposition_lint(propositions)

    reasons = []

    if lint_result.failed:
        reasons.append(f"Failed propositions: {len(lint_result.failed)}")

    foundational = [p for p in propositions if p.role == PropositionRole.FOUNDATIONAL]
    for prop in foundational:
        if prop.legitimacy and str(prop.legitimacy) == PropositionLegitimacy.SUSPENDED.value:
            reasons.append(f"Foundational proposition {prop.id} has suspended legitimacy")

    boundary_issues = check_foundational_boundaries(propositions)
    if boundary_issues:
        reasons.extend(boundary_issues[:5])

    derived_issues = check_derived_support(propositions)
    if derived_issues:
        reasons.extend(derived_issues[:5])

    if reasons:
        return "BLOCK", reasons

    if lint_result.conditional:
        return "CONDITIONAL", [f"Conditional propositions: {len(lint_result.conditional)}"]

    return "PASS", []
