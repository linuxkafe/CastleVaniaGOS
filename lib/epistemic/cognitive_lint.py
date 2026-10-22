"""Cognitive Lint (Lint Cognitivo) — FR-6 output gate.

Ported from Grilo Falante v3 (grilo_falante.backend.services.cognitive_lint)
as part of AES T128 self-containment effort.

The lint judges *form* (rhetorical patterns), never *content truth* — making it a
truth validator would violate the project's core non-goal. Likewise, ACCEPT means
"no blocking pattern found", never epistemic legitimacy: legitimacy is asserted
only by humans (FR-3), and every result says so in epistemic_note.
"""

import re
from dataclasses import dataclass, field
from enum import Enum

_EPISTEMIC_NOTE = (
    "ACCEPT is not epistemic legitimacy; "
    "legitimacy is asserted only by humans (FR-3)."
)


class LintState(str, Enum):
    ACCEPT = "accept"
    CONDITIONAL = "conditional"
    REJECT = "reject"
    REEXECUTE = "reexecute"


@dataclass
class LintResult:
    state: LintState
    message: str
    issues: list[str] = field(default_factory=list)
    epistemic_note: str = _EPISTEMIC_NOTE


class LintBlocked(Exception):
    def __init__(self, result: LintResult):
        self.result = result
        super().__init__(f"{result.message}: {'; '.join(result.issues)}")


class CognitiveLint:
    """Pattern-based output gate.

    REJECT      — a blocking pattern matched; output must not pass.
    CONDITIONAL — warning patterns matched; output passes flagged for review.
    REEXECUTE   — input is unlintable (empty/whitespace).
    ACCEPT      — no pattern matched. Not a legitimacy claim.
    """

    BLOCK_PATTERNS = [
        (r"\b(just|simply)\b.*\?", "Leading question pattern - don't assume answer"),
        (
            r"\b(can|can't|could|couldn't|would|should)\s+we\s+(just|simply)\s",
            "Bypass pattern - don't skip validation",
        ),
        (
            r"\bThis\s+is\s+(obviously|clearly|trivially)\s",
            "Fluency assumption - evidence required",
        ),
        (r"\bTrust\s+me\b", "Authority claim without evidence"),
        (r"\bBelieve\s+me\b", "Authority claim without evidence"),
        (r"^\s*\(?(?:Note|TODO|FIXME|HACK)\b", "Unresolved marker"),
        (r"\b(100%\s+de\s+certeza|certamente)\b", "C001 No False Certainty"),
        (
            r"\b(?:estudo|pesquisa|relat[óo]rio)\s+(?:diz|mostra|provou)\b",
            "C002 No Unattributed Claims",
        ),
    ]

    WARN_PATTERNS = [
        (r"\b(maybe|perhaps|possibly|probably)\b", "Hedging detected"),
        (r"\bI\s+think\b", "Subjective qualifier"),
        (r"\bIt\s+seems\b", "Weak assertion"),
        (r"\bmight\s+be\b", "Hedging detected"),
        (r"\bcould\s+be\b", "Hedging detected"),
    ]

    def lint(self, text: str) -> LintResult:
        if not text or not text.strip():
            return LintResult(
                state=LintState.REEXECUTE,
                message="Nothing to lint - producer must re-run",
            )

        block_issues = [
            message
            for pattern, message in self.BLOCK_PATTERNS
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        ]
        if block_issues:
            return LintResult(
                state=LintState.REJECT,
                message="Blocking pattern detected",
                issues=block_issues,
            )

        warn_issues = [
            message
            for pattern, message in self.WARN_PATTERNS
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        ]
        if warn_issues:
            return LintResult(
                state=LintState.CONDITIONAL,
                message="Warning patterns detected - review advised",
                issues=warn_issues,
            )

        return LintResult(
            state=LintState.ACCEPT, message="No blocking patterns detected"
        )

    def gate(self, text: str) -> LintResult:
        result = self.lint(text)
        if result.state == LintState.REJECT:
            raise LintBlocked(result)
        return result

    def is_blocking(self, text: str) -> bool:
        return self.lint(text).state == LintState.REJECT
