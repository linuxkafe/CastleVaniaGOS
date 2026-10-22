"""Comprehensive tests for loop_closure.py (T166).

Covers: loop creation, state transitions, promotion gates, closure policies,
grouping, summary statistics, tension-based loop creation.
"""

import pytest
from datetime import datetime

from lib.epistemic.epistemic_objects import (
    OpenLoop,
    ClosureRecord,
    TrustedCommitment,
    LoopStatus,
    LoopCriticality,
    ClosureType,
    TensionRecord,
    TensionType,
    Proposition,
    PropositionRole,
    TensionResolution,
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


# ── helpers ──────────────────────────────────────────────────────────────


def _loop(status=LoopStatus.OPEN, criticality=LoopCriticality.MEDIUM, **kw):
    return OpenLoop(
        id=kw.pop("id", generate_loop_id()),
        source_type=kw.pop("source_type", "claim"),
        source_id=kw.pop("source_id", "CLM-001"),
        status=status,
        criticality=criticality,
        closure_policy=kw.pop("closure_policy", "claim_validation"),
        created_at=kw.pop("created_at", datetime.now().isoformat()),
        updated_at=kw.pop("updated_at", datetime.now().isoformat()),
        **kw,
    )


def _tension(severity=2, resolution_status=TensionResolution.UNRESOLVED):
    return TensionRecord(
        id=f"TEN-{generate_loop_id()}",
        left_proposition_id="PROP-L",
        right_proposition_id="PROP-R",
        tension_type=TensionType.CONTRADICTION,
        severity=severity,
        resolution_status=resolution_status,
    )


# ── generate_loop_id ─────────────────────────────────────────────────────


class TestGenerateLoopId:
    def test_format(self):
        lid = generate_loop_id()
        assert lid.startswith("LOOP-")
        parts = lid.split("-")
        assert len(parts) == 3  # LOOP-YYMMDD-XXXXXX

    def test_unique(self):
        ids = {generate_loop_id() for _ in range(100)}
        assert len(ids) == 100


# ── open_loop_from_claim ─────────────────────────────────────────────────


class TestOpenLoopFromClaim:
    def test_creates_loop(self):
        loop = open_loop_from_claim("CLM-001", "test claim")
        assert loop.source_type == "claim"
        assert loop.source_id == "CLM-001"
        assert loop.status == LoopStatus.OPEN

    def test_default_criticality(self):
        loop = open_loop_from_claim("CLM-001", "text")
        assert loop.criticality == LoopCriticality.MEDIUM

    def test_custom_criticality(self):
        loop = open_loop_from_claim("CLM-001", "text", LoopCriticality.HIGH)
        assert loop.criticality == LoopCriticality.HIGH


# ── open_loop_from_proposition ───────────────────────────────────────────


class TestOpenLoopFromProposition:
    def test_creates_loop(self):
        prop = Proposition(id="PROP-001", statement="test", role=PropositionRole.FOUNDATIONAL, gmif_type="M1")
        loop = open_loop_from_proposition(prop)
        assert loop.source_type == "proposition"
        assert loop.source_id == "PROP-001"
        assert loop.status == LoopStatus.OPEN


# ── open_loop_from_tension ───────────────────────────────────────────────


class TestOpenLoopFromTension:
    def test_severity_3_maps_to_high(self):
        t = _tension(severity=3)
        loop = open_loop_from_tension(t)
        assert loop.criticality == LoopCriticality.HIGH

    def test_severity_5_maps_to_high(self):
        t = _tension(severity=5)
        loop = open_loop_from_tension(t)
        assert loop.criticality == LoopCriticality.HIGH

    def test_severity_2_maps_to_medium(self):
        t = _tension(severity=2)
        loop = open_loop_from_tension(t)
        assert loop.criticality == LoopCriticality.MEDIUM

    def test_severity_1_maps_to_low(self):
        t = _tension(severity=1)
        loop = open_loop_from_tension(t)
        assert loop.criticality == LoopCriticality.LOW

    def test_explicit_criticality_overrides(self):
        t = _tension(severity=5)
        loop = open_loop_from_tension(t, criticality=LoopCriticality.LOW)
        assert loop.criticality == LoopCriticality.LOW

    def test_source_type_is_tension(self):
        t = _tension()
        loop = open_loop_from_tension(t)
        assert loop.source_type == "tension"
        assert loop.source_id == t.id


# ── close_loop ───────────────────────────────────────────────────────────


class TestCloseLoop:
    def test_sets_status_closed(self):
        loop = _loop()
        close_loop(loop, ClosureType.EVIDENCE_BASED, "tested")
        assert loop.status == LoopStatus.CLOSED

    def test_returns_closure_record(self):
        loop = _loop()
        record = close_loop(loop, ClosureType.EVIDENCE_BASED, "evidence")
        assert record.loop_id == loop.id
        assert record.closure_type == ClosureType.EVIDENCE_BASED
        assert record.evidence == "evidence"
        assert record.closed_at is not None

    def test_updates_timestamp(self):
        loop = _loop()
        old_ts = loop.updated_at
        close_loop(loop, ClosureType.EVIDENCE_BASED)
        assert loop.updated_at >= old_ts


# ── suspend_loop ─────────────────────────────────────────────────────────


class TestSuspendLoop:
    def test_sets_status_suspended(self):
        loop = _loop()
        suspend_loop(loop, "reason")
        assert loop.status == LoopStatus.SUSPENDED

    def test_record_has_suspension_type(self):
        loop = _loop()
        record = suspend_loop(loop, "reason")
        assert record.closure_type == ClosureType.SUSPENSION
        assert record.evidence == "reason"

    def test_default_reason(self):
        loop = _loop()
        record = suspend_loop(loop, "suspended")
        assert record.evidence == "suspended"


# ── block_loop ───────────────────────────────────────────────────────────


class TestBlockLoop:
    def test_sets_status_blocked(self):
        loop = _loop()
        block_loop(loop, "blocked reason")
        assert loop.status == LoopStatus.BLOCKED

    def test_record_has_blocked_type(self):
        loop = _loop()
        record = block_loop(loop, "blocked")
        assert record.closure_type == ClosureType.BLOCKED

    def test_stores_reason(self):
        loop = _loop()
        record = block_loop(loop, "blocked")
        assert record.evidence == "blocked"


# ── register_trusted_commitment ──────────────────────────────────────────


class TestRegisterTrustedCommitment:
    def test_sets_status_scheduled(self):
        loop = _loop()
        register_trusted_commitment(loop, "commitment", "user-1", "materialized")
        assert loop.status == LoopStatus.SCHEDULED

    def test_stores_commitment_on_loop(self):
        loop = _loop()
        register_trusted_commitment(loop, "text", "user-1", "mat")
        assert loop.trusted_commitment is not None
        assert loop.trusted_commitment["text"] == "text"
        assert loop.trusted_commitment["committed_by"] == "user-1"

    def test_returns_trusted_commitment(self):
        loop = _loop()
        tc = register_trusted_commitment(loop, "text", "user-1", "mat")
        assert tc.claim_id == loop.source_id
        assert tc.commitment_text == "text"
        assert tc.id.startswith("TC-")


# ── can_promote ──────────────────────────────────────────────────────────


class TestCanPromote:
    def test_empty_loops_can_promote(self):
        ok, reasons = can_promote([])
        assert ok is True
        assert reasons == []

    def test_open_medium_loop_can_promote(self):
        loops = [_loop(status=LoopStatus.OPEN, criticality=LoopCriticality.MEDIUM)]
        ok, reasons = can_promote(loops)
        assert ok is True

    def test_open_high_loop_blocks(self):
        loops = [_loop(status=LoopStatus.OPEN, criticality=LoopCriticality.HIGH)]
        ok, reasons = can_promote(loops)
        assert ok is False
        assert len(reasons) == 1
        assert "Critical loop open" in reasons[0]

    def test_closed_high_loop_does_not_block(self):
        loops = [_loop(status=LoopStatus.CLOSED, criticality=LoopCriticality.HIGH)]
        ok, reasons = can_promote(loops)
        assert ok is True

    def test_multiple_high_loops_all_reported(self):
        loops = [
            _loop(id="LOOP-1", criticality=LoopCriticality.HIGH),
            _loop(id="LOOP-2", criticality=LoopCriticality.HIGH),
        ]
        ok, reasons = can_promote(loops)
        assert ok is False
        assert len(reasons) == 2

    def test_mixed_criticalities(self):
        loops = [
            _loop(id="LOOP-1", criticality=LoopCriticality.HIGH),
            _loop(id="LOOP-2", criticality=LoopCriticality.LOW),
        ]
        ok, reasons = can_promote(loops)
        assert ok is False  # high blocks regardless of low


# ── evaluate_loops_for_promotion ─────────────────────────────────────────


class TestEvaluateLoopsForPromotion:
    def test_empty_returns_pass(self):
        status, reasons = evaluate_loops_for_promotion([])
        assert status == "PASS"
        assert reasons == []

    def test_high_open_returns_block(self):
        loops = [_loop(criticality=LoopCriticality.HIGH)]
        status, reasons = evaluate_loops_for_promotion(loops)
        assert status == "BLOCK"
        assert "Critical loop open" in reasons[0]

    def test_medium_open_returns_conditional(self):
        loops = [_loop(criticality=LoopCriticality.MEDIUM)]
        status, reasons = evaluate_loops_for_promotion(loops)
        assert status == "CONDITIONAL"
        assert "Open loops: 1" in reasons[0]

    def test_all_closed_returns_pass(self):
        loops = [_loop(status=LoopStatus.CLOSED)]
        status, reasons = evaluate_loops_for_promotion(loops)
        assert status == "PASS"


# ── apply_closure_policy ─────────────────────────────────────────────────


class TestApplyClosurePolicy:
    def test_evidence_based(self):
        loop = _loop()
        record = apply_closure_policy(loop, "evidence_based", "tested")
        assert record.closure_type == ClosureType.EVIDENCE_BASED
        assert loop.status == LoopStatus.CLOSED

    def test_trusted_commitment(self):
        loop = _loop()
        record = apply_closure_policy(
            loop, "trusted_commitment", evidence="promise", committed_by="user-1"
        )
        assert record.closure_type == ClosureType.TRUSTED_COMMITMENT
        assert loop.status == LoopStatus.CLOSED
        assert loop.trusted_commitment is not None

    def test_trusted_commitment_requires_committed_by(self):
        loop = _loop()
        with pytest.raises(ValueError, match="committed_by required"):
            apply_closure_policy(loop, "trusted_commitment", evidence="promise")

    def test_suspension(self):
        loop = _loop()
        record = apply_closure_policy(loop, "suspension", "delayed")
        assert record.closure_type == ClosureType.SUSPENSION
        assert loop.status == LoopStatus.SUSPENDED

    def test_block(self):
        loop = _loop()
        record = apply_closure_policy(loop, "block", "wontfix")
        assert record.closure_type == ClosureType.BLOCKED
        assert loop.status == LoopStatus.BLOCKED

    def test_unknown_policy_defaults_to_evidence_based(self):
        loop = _loop()
        record = apply_closure_policy(loop, "unknown_policy", "fallback")
        assert record.closure_type == ClosureType.EVIDENCE_BASED
        assert loop.status == LoopStatus.CLOSED

    def test_suspension_default_reason(self):
        loop = _loop()
        record = apply_closure_policy(loop, "suspension")
        assert record.evidence == "suspended"

    def test_block_default_reason(self):
        loop = _loop()
        record = apply_closure_policy(loop, "block")
        assert record.evidence == "blocked"


# ── get_loops_by_criticality ─────────────────────────────────────────────


class TestGetLoopsByCriticality:
    def test_groups_correctly(self):
        loops = [
            _loop(id="L1", criticality=LoopCriticality.HIGH),
            _loop(id="L2", criticality=LoopCriticality.MEDIUM),
            _loop(id="L3", criticality=LoopCriticality.LOW),
            _loop(id="L4", criticality=LoopCriticality.HIGH),
        ]
        groups = get_loops_by_criticality(loops)
        assert len(groups["high"]) == 2
        assert len(groups["medium"]) == 1
        assert len(groups["low"]) == 1

    def test_empty(self):
        groups = get_loops_by_criticality([])
        assert groups == {"high": [], "medium": [], "low": []}


# ── get_open_critical_loops ──────────────────────────────────────────────


class TestGetOpenCriticalLoops:
    def test_filters_correctly(self):
        loops = [
            _loop(id="L1", status=LoopStatus.OPEN, criticality=LoopCriticality.HIGH),
            _loop(id="L2", status=LoopStatus.CLOSED, criticality=LoopCriticality.HIGH),
            _loop(id="L3", status=LoopStatus.OPEN, criticality=LoopCriticality.LOW),
        ]
        result = get_open_critical_loops(loops)
        assert len(result) == 1
        assert result[0].id == "L1"

    def test_empty(self):
        assert get_open_critical_loops([]) == []


# ── get_loop_summary ─────────────────────────────────────────────────────


class TestGetLoopSummary:
    def test_counts_statuses(self):
        loops = [
            _loop(status=LoopStatus.OPEN),
            _loop(status=LoopStatus.OPEN),
            _loop(status=LoopStatus.CLOSED),
            _loop(status=LoopStatus.SUSPENDED),
            _loop(status=LoopStatus.BLOCKED),
            _loop(status=LoopStatus.SCHEDULED),
            _loop(status=LoopStatus.PROMOTED),
        ]
        s = get_loop_summary(loops)
        assert s["total"] == 7
        assert s["open"] == 2
        assert s["closed"] == 1
        assert s["suspended"] == 1
        assert s["blocked"] == 1
        assert s["scheduled"] == 1
        assert s["promoted"] == 1

    def test_counts_criticalities(self):
        loops = [
            _loop(criticality=LoopCriticality.HIGH),
            _loop(criticality=LoopCriticality.HIGH),
            _loop(criticality=LoopCriticality.MEDIUM),
        ]
        s = get_loop_summary(loops)
        assert s["critical_high"] == 2
        assert s["critical_medium"] == 1
        assert s["critical_low"] == 0

    def test_empty(self):
        s = get_loop_summary([])
        assert s["total"] == 0


# ── summarize_closure_state ──────────────────────────────────────────────


class TestSummarizeClosureState:
    def test_includes_loop_and_closure_summary(self):
        loops = [_loop(status=LoopStatus.OPEN, criticality=LoopCriticality.MEDIUM)]
        closures = [
            ClosureRecord(
                loop_id="x", closure_type=ClosureType.EVIDENCE_BASED,
                evidence="e", closed_at=datetime.now().isoformat()
            )
        ]
        result = summarize_closure_state(loops, closures)
        assert result["loops"]["total"] == 1
        assert result["closures"]["total"] == 1
        assert result["closures"]["evidence_based"] == 1
        assert result["can_promote"] is True

    def test_blocks_when_high_open(self):
        loops = [_loop(criticality=LoopCriticality.HIGH)]
        result = summarize_closure_state(loops, [])
        assert result["can_promote"] is False


# ── create_loops_from_tensions ───────────────────────────────────────────


class TestCreateLoopsFromTensions:
    def test_creates_loops_for_unresolved(self):
        tensions = [_tension(severity=3), _tension(severity=1)]
        loops = create_loops_from_tensions(tensions)
        assert len(loops) == 2
        assert all(l.source_type == "tension" for l in loops)

    def test_skips_resolved(self):
        tensions = [
            _tension(resolution_status=TensionResolution.RESOLVED),
            _tension(resolution_status=TensionResolution.UNRESOLVED),
        ]
        loops = create_loops_from_tensions(tensions)
        assert len(loops) == 1

    def test_empty(self):
        assert create_loops_from_tensions([]) == []

    def test_severity_mapping(self):
        tensions = [
            _tension(severity=5),
            _tension(severity=2),
            _tension(severity=1),
        ]
        loops = create_loops_from_tensions(tensions)
        assert loops[0].criticality == LoopCriticality.HIGH
        assert loops[1].criticality == LoopCriticality.MEDIUM
        assert loops[2].criticality == LoopCriticality.LOW
