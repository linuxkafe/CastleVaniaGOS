"""
Governance Orchestrator — Wires epistemic mechanisms into the pipeline.

Consults GraphLinter, GMIFClassifier, EvidenceEngine, and GraphStore
before decisions. Zero LLM calls. Pure Python composition.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .graph_store import KnowledgeGraphStore, InMemoryGraphStore, GraphNode
from .graph_linter import GraphLinter, LintIssue
from .gmif_classifier import classify_claim, ClassificationResult
from .evidence_engine import EvidenceEngine, EvidenceScore
from .gmif import GMIFLevel


@dataclass
class GovernedClaimResult:
    """Result of claim governance consultation."""
    claim_id: str
    lint_issues: List[LintIssue]
    gmif_result: ClassificationResult
    evidence_score: EvidenceScore
    overall_decision: str  # allow, warn, block
    issues: List[str] = field(default_factory=list)


class GovernanceOrchestrator:
    """
    Deterministic orchestrator that consults governance mechanisms
    before decisions in the pipeline.

    Order of checks per claim:
    1. GraphLinter → L1-L8 issues
    2. GMIFClassifier → level + confidence
    3. EvidenceEngine → evidence score
    4. Consolidation → overall decision
    """

    def __init__(
        self,
        store: Optional[KnowledgeGraphStore] = None,
        enforce: bool = False,
    ):
        self.store = store or InMemoryGraphStore()
        self.linter = GraphLinter(self.store)
        self.evidence_engine = EvidenceEngine(self.store)
        self.enforce = enforce
        self._lint_cache: Optional[Dict[str, List[LintIssue]]] = None

    def govern_claim(
        self,
        claim_text: str,
        claim_id: str = "unknown",
        frontmatter: Optional[Dict] = None,
        claimed_level: Optional[GMIFLevel] = None,
    ) -> GovernedClaimResult:
        """
        Consult all mechanisms for a claim and return consolidated decision.
        """
        issues: List[str] = []

        # 1. GraphLinter — run once, reuse across claims
        if self._lint_cache is None:
            self._lint_cache = self.linter.run_all_checks(self.store)
        lint_issues_all = self._lint_cache
        # Flatten and filter to issues affecting this claim
        claim_lint_issues = []
        for code, code_issues in lint_issues_all.items():
            for issue in code_issues:
                if claim_id in issue.affected_nodes or claim_text in issue.affected_nodes:
                    claim_lint_issues.append(issue)
                    issues.append(f"{issue.code}: {issue.description}")

        # 2. GMIFClassifier
        gmif_result = classify_claim(claim_text, frontmatter, claimed_level)

        # 3. EvidenceEngine
        evidence_score = self.evidence_engine.compute(
            claim_id, frontmatter
        )

        # 4. Consolidation
        overall = self._consolidate(
            lint_issues=claim_lint_issues,
            gmif_result=gmif_result,
            evidence_score=evidence_score,
        )

        return GovernedClaimResult(
            claim_id=claim_id,
            lint_issues=claim_lint_issues,
            gmif_result=gmif_result,
            evidence_score=evidence_score,
            overall_decision=overall,
            issues=issues,
        )

    def run_graph_lint(self) -> Dict[str, List[LintIssue]]:
        """Run full graph lint and return all issues."""
        if self._lint_cache is None:
            self._lint_cache = self.linter.run_all_checks(self.store)
        return self._lint_cache

    def invalidate_cache(self) -> None:
        """Invalidate the lint cache (call after graph mutations)."""
        self._lint_cache = None

    def _consolidate(
        self,
        lint_issues: List[LintIssue],
        gmif_result: ClassificationResult,
        evidence_score: EvidenceScore,
    ) -> str:
        """Consolidate all checks into overall decision."""
        # Block conditions
        has_error = any(i.severity == "error" for i in lint_issues)
        low_confidence = gmif_result.confidence < 0.2
        low_evidence = evidence_score.score < 0.2

        if has_error or low_confidence or low_evidence:
            return "block" if self.enforce else "warn"

        # Warn conditions
        has_warning = any(i.severity == "warning" for i in lint_issues)
        if has_warning:
            return "warn"

        return "allow"
