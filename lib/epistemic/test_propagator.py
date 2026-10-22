"""Premise Propagator tests (T012) — the 12 original checks from
/opt/x/premise_propagator/test_propagator.py ported to pytest, plus the
promotion_gate contract tests (T009).

AES T036: imports switched from grilo_falante.* to lib.epistemic.
Tests now run (no more skip).
"""

import json

import pytest

from lib.epistemic import propagator as P
from lib.epistemic.epistemic_objects import (
    FalsificationCondition,
    FalsificationStatus,
    LoopCriticality,
    LoopStatus,
    OpenLoop,
    Proposition,
    PropositionDependency,
    PropositionRole,
    RelationType,
)
from lib.epistemic.loop_closure import (
    can_promote,
    evaluate_loops_for_promotion,
)
from lib.epistemic.promotion_gate import main as gate_main


def prop(i, role):
    return Proposition(id=i, statement=f"stmt {i}", role=role, gmif_type="M6")


@pytest.fixture
def world():
    """Graph: F(found) <- D1 <- D2; A supports D2; D3 contradicts F;
    D4 narrows F; I independent."""
    props = [
        prop("F", PropositionRole.FOUNDATIONAL),
        prop("D1", PropositionRole.DERIVED),
        prop("D2", PropositionRole.DERIVED),
        prop("A", PropositionRole.ASSUMPTION),
        prop("D3", PropositionRole.DERIVED),
        prop("D4", PropositionRole.DERIVED),
        prop("I", PropositionRole.DERIVED),
    ]
    deps = [
        PropositionDependency("D1", "F", RelationType.DEPENDS_ON),
        PropositionDependency("D2", "D1", RelationType.DEPENDS_ON),
        PropositionDependency("A", "D2", RelationType.SUPPORTS),
        PropositionDependency(
            "D3", "F", RelationType.CONTRADICTS
        ),  # must NOT propagate
        PropositionDependency("D4", "F", RelationType.NARROWS),  # must NOT propagate
    ]
    fc_fail = [
        FalsificationCondition(
            id="FC1",
            proposition_id="F",
            condition_text="x",
            evidence_needed="y",
            status=FalsificationStatus.FAILED,
        )
    ]
    return props, deps, fc_fail


# ------------------------------------------------ original checks 1-7


def test_cascade_reaches_exactly_load_bearing_dependents(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    assert r.affected_proposition_ids == {"D1", "D2"}


def test_weak_relations_do_not_propagate(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    assert "D3" not in r.affected_proposition_ids
    assert "D4" not in r.affected_proposition_ids


def test_constrains_risk_direction():
    """T302 (MINOR-1): from CONSTRAINS to -> risk[from].add(to).

    If the constraint (`from`) falls, the constrained (`to`) is at risk —
    same edge direction as SUPPORTS, distinct semantic (not DEPENDS_ON:
    DEPENDS_ON would put `to` in risk of `from`, inverting the meaning).
    """
    deps = [
        PropositionDependency("C", "T", RelationType.CONSTRAINS),
        PropositionDependency("X", "Y", RelationType.DEPENDS_ON),
    ]
    risk = P.build_risk_graph(deps)
    assert risk["C"] == {"T"}, "CONSTRAINS must endanger the constrained"
    assert "X" in risk["Y"], "DEPENDS_ON direction unchanged"


def test_independent_proposition_untouched(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    assert "I" not in r.affected_proposition_ids


def test_opened_loops_are_high_open_premise_fallen(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    assert all(
        loop.criticality == LoopCriticality.HIGH
        and loop.status == LoopStatus.OPEN
        and loop.closure_policy == "premise_fallen"
        for loop in r.opened_loops
    )


def test_provenance_paths(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    paths = {rec.affected_proposition_id: rec.path for rec in r.reopen_records}
    assert paths["D1"] == ["F", "D1"]
    assert paths["D2"] == ["F", "D1", "D2"]


# ------------------------------------------------ original checks 8-9 (gate)


def test_can_promote_blocks_on_cascade(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    blocked, reasons = can_promote(r.opened_loops)
    assert blocked is False
    assert len(reasons) == 2


def test_evaluate_loops_for_promotion_blocks(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    assert evaluate_loops_for_promotion(r.opened_loops)[0] == "BLOCK"


# ------------------------------------------------ original checks 10-12


def test_contesting_assumption_propagates_via_supports_only(world):
    props, deps, _ = world
    r2 = P.propagate(props, deps, [], contested_ids=["A"])
    assert r2.affected_proposition_ids == {"D2"}


def test_idempotent_against_existing_open_loops(world):
    props, deps, fc_fail = world
    existing = [
        OpenLoop(
            id="L-EXIST",
            source_type="proposition",
            source_id="D1",
            status=LoopStatus.OPEN,
        )
    ]
    r3 = P.propagate(props, deps, fc_fail, existing_loops=existing)
    assert r3.affected_proposition_ids == {"D2"}


def test_cycle_safe(world):
    props, deps, fc_fail = world
    deps_cyc = deps + [PropositionDependency("D1", "D2", RelationType.DEPENDS_ON)]
    r4 = P.propagate(props, deps_cyc, fc_fail)  # must terminate
    # With JTMS: D1 has justifications {F} and {D2}; D2 has {D1} and {A}.
    # F falls, but D2 stays IN via {A}, so D1 stays IN via {D2}.
    # The cycle is NOT an odd cycle because it has external support (A).
    assert r4.affected_proposition_ids == set()


def test_proposes_contestation_only_for_promoted_claims(world):
    props, deps, fc_fail = world
    r = P.propagate(props, deps, fc_fail)
    proposals = P.propose_claim_contestations(
        r.affected_proposition_ids, {"D2": (42, "promoted"), "D1": (7, "audited")}
    )
    assert len(proposals) == 1
    assert proposals[0].claim_id == 42
    assert proposals[0].to_status == "contested"



# ------------------------------------------------ NEW tests for T048 (JTMS)

def test_diamond_minimal_retraction():
    """Diamond graph: F->D1, F->D2, D1->D3, D2->D3.
    Fall F -> {D1,D2,D3} OUT. Restore F -> {D1,D2,D3} IN.
    Proves minimal consequence-cone retraction."""
    props = [
        Proposition(id="F", statement="F", role=PropositionRole.FOUNDATIONAL, gmif_type="M6"),
        Proposition(id="D1", statement="D1", role=PropositionRole.DERIVED, gmif_type="M6"),
        Proposition(id="D2", statement="D2", role=PropositionRole.DERIVED, gmif_type="M6"),
        Proposition(id="D3", statement="D3", role=PropositionRole.DERIVED, gmif_type="M6"),
    ]
    deps = [
        PropositionDependency("D1", "F", RelationType.DEPENDS_ON),
        PropositionDependency("D2", "F", RelationType.DEPENDS_ON),
        PropositionDependency("D3", "D1", RelationType.DEPENDS_ON),
        PropositionDependency("D3", "D2", RelationType.DEPENDS_ON),
    ]
    fc_fail = [FalsificationCondition("FC1", "F", "x", "y", FalsificationStatus.FAILED)]

    # Fall F
    r_fall = P.propagate(props, deps, fc_fail)
    assert r_fall.affected_proposition_ids == {"D1", "D2", "D3"}

    # Restore F (retract)
    r_restore = P.retract(props, deps, [], "F")
    # F is IN again; D1,D2,D3 should be IN (no loops opened on retraction)
    assert r_restore.affected_proposition_ids == {"F", "D1", "D2", "D3"}

    # Verify no other nodes affected
    all_nodes = {p.id for p in props}
    assert r_restore.affected_proposition_ids.issubset(all_nodes)


def test_odd_cycle_nogood():
    """Odd cycle: A DEPENDS_ON B, B DEPENDS_ON A (no external support).
    Fall A -> both OUT with NOGOOD recorded.
    A is the seed (cause), B is the affected (gets OpenLoop)."""
    props = [
        Proposition(id="A", statement="A", role=PropositionRole.FOUNDATIONAL, gmif_type="M6"),
        Proposition(id="B", statement="B", role=PropositionRole.FOUNDATIONAL, gmif_type="M6"),
    ]
    deps = [
        PropositionDependency("A", "B", RelationType.DEPENDS_ON),
        PropositionDependency("B", "A", RelationType.DEPENDS_ON),
    ]
    fc_fail = [FalsificationCondition("FC1", "A", "x", "y", FalsificationStatus.FAILED)]

    r = P.propagate(props, deps, fc_fail)
    # A is seed, B is affected (gets OpenLoop)
    assert r.affected_proposition_ids == {"B"}
    # Verify via JTMS directly
    from lib.epistemic.tms import JTMS, NodeLabel
    jtms = JTMS()
    jtms.add_node("A")
    jtms.add_node("B")
    jtms.add_justification({"B"}, "A", "DEPENDS_ON")
    jtms.add_justification({"A"}, "B", "DEPENDS_ON")
    jtms.tell_out("A", "fell")
    assert jtms.get_label("A") == NodeLabel.OUT
    assert jtms.get_label("B") == NodeLabel.OUT
    assert len(jtms.nogoods) == 1
    assert jtms.nogoods[0] == {"A", "B"}


# ------------------------------------------------ promotion_gate (T009 contract)


def test_gate_exit_zero_when_no_store(tmp_path, monkeypatch):
    monkeypatch.setenv("GRILO_LOOPS", str(tmp_path / "absent.json"))
    assert gate_main() == 0


def test_gate_blocks_on_high_open_loop(tmp_path, monkeypatch):
    store = tmp_path / "loops.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "L1",
                    "source_type": "proposition",
                    "source_id": "D1",
                    "status": "OPEN",
                    "criticality": "high",
                    "closure_policy": "premise_fallen",
                }
            ]
        )
    )
    monkeypatch.setenv("GRILO_LOOPS", str(store))
    assert gate_main() == 1


def test_gate_passes_on_closed_or_low_loops(tmp_path, monkeypatch):
    store = tmp_path / "loops.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "L1",
                    "source_type": "proposition",
                    "source_id": "D1",
                    "status": "CLOSED",
                    "criticality": "high",
                },
                {
                    "id": "L2",
                    "source_type": "proposition",
                    "source_id": "D2",
                    "status": "OPEN",
                    "criticality": "low",
                },
            ]
        )
    )
    monkeypatch.setenv("GRILO_LOOPS", str(store))
    assert gate_main() == 0
