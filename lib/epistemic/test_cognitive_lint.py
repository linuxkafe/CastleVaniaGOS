"""Unit tests for Cognitive Lint (FR-6) — ported from Grilo Falante."""
import pytest
from lib.epistemic.cognitive_lint import (
    CognitiveLint,
    LintBlocked,
    LintResult,
    LintState,
)


@pytest.fixture
def lint() -> CognitiveLint:
    return CognitiveLint()


def test_clean_text_is_accepted(lint):
    result = lint.lint("The measurement returned 42 units, recorded in source X.")
    assert result.state == LintState.ACCEPT


def test_accept_does_not_assert_legitimacy(lint):
    result = lint.lint("A plain, well-formed sentence with a citation [1].")
    assert result.state == LintState.ACCEPT
    assert "legitimacy" in result.epistemic_note.lower()


def test_empty_text_requires_reexecution(lint):
    assert lint.lint("").state == LintState.REEXECUTE


def test_whitespace_only_requires_reexecution(lint):
    assert lint.lint("   \n\t  ").state == LintState.REEXECUTE


def test_warning_yields_conditional(lint):
    result = lint.lint("Maybe the cache invalidation is the cause.")
    assert result.state == LintState.CONDITIONAL
    assert result.issues


def test_block_yields_reject(lint):
    result = lint.lint("Trust me, the value is correct.")
    assert result.state == LintState.REJECT


@pytest.mark.parametrize("text", [
    "Can't we just skip the check?",
    "Could we simply bypass validation here",
    "This is obviously the right architecture.",
    "Trust me, it works.",
    "Believe me, this is fine.",
    "TODO: verify this claim later",
    "Temos 100% de certeza no resultado.",
    "O estudo provou que o método funciona.",
])
def test_blocking_patterns_reject(lint, text):
    assert lint.lint(text).state == LintState.REJECT


def test_all_blocking_issues_are_collected(lint):
    result = lint.lint("Trust me. Believe me. This is obviously fine.")
    assert result.state == LintState.REJECT
    assert len(result.issues) >= 3


@pytest.mark.parametrize("text", [
    "Maybe this holds for larger inputs.",
    "I think the parser handles unicode.",
    "It seems the retry fires twice.",
    "The cause might be the scheduler.",
    "It could be a race condition.",
])
def test_warning_patterns_conditional(lint, text):
    assert lint.lint(text).state == LintState.CONDITIONAL


def test_warnings_never_block(lint):
    result = lint.lint("Perhaps possibly maybe — I think it seems unclear.")
    assert result.state == LintState.CONDITIONAL


def test_case_insensitive_matching(lint):
    assert lint.lint("TRUST ME, it is fine.").state == LintState.REJECT


def test_gate_raises_on_reject(lint):
    with pytest.raises(LintBlocked):
        lint.gate("Trust me, no need to verify.")


def test_gate_passes_through_non_blocking(lint):
    result = lint.gate("Plain statement with provenance [source].")
    assert isinstance(result, LintResult)
    assert result.state in (LintState.ACCEPT, LintState.CONDITIONAL)


def test_gate_raises_carries_issues(lint):
    with pytest.raises(LintBlocked) as exc:
        lint.gate("Believe me.")
    assert exc.value.result.issues


def test_is_blocking_helper(lint):
    assert lint.is_blocking("Trust me.") is True
    assert lint.is_blocking("Plain statement.") is False


def test_lint_judges_form_not_truth(lint):
    result = lint.lint("The moon is made of cheese, per reference [9].")
    assert result.state == LintState.ACCEPT
