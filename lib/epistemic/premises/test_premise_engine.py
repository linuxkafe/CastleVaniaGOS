"""T300 (R-19) regression tests — resurrected premise gate.

Covers:
- DOT parsing tolerates uppercase role/relation names (FOUNDATIONAL, DEPENDS_ON)
- DOT parsing tolerates the canonical multi-line node layout
  (`"id"` on one line, `[attrs]` on the next)
- canonical dot selection prefers project-graph.dot
- both parsers (aes.gf.propagate bridge + PremisesEngine) agree
"""

import json
from pathlib import Path

import pytest

AES_ROOT = Path(__file__).resolve().parents[3]
PREMISES_DIR = AES_ROOT / "aes" / "premises"

from aes.gf.propagate import parse_premise_graph as bridge_parse
from aes.gf.propagate import load_premises_and_conditions
from lib.epistemic.epistemic_objects import PropositionRole, RelationType
from lib.epistemic.premises.engine import _dot_path as engine_dot_path
from lib.epistemic.premises.engine import _parse_dot as engine_parse
from lib.epistemic.premises.engine import PremisesEngine


def test_canonical_dot_selected_by_engine():
    """P4: engine must read project-graph.dot, not sorted()[0] (T003)."""
    dot = engine_dot_path()
    assert dot is not None
    assert dot.name == "project-graph.dot"


def test_bridge_parses_uppercase_roles():
    """P1/P5: uppercase DOT types parse without ValueError, real roles kept."""
    props, _ = bridge_parse(PREMISES_DIR / "project-graph.dot")
    roles = {p.role for p in props}
    assert PropositionRole.FOUNDATIONAL in roles
    assert PropositionRole.ASSUMPTION in roles
    assert PropositionRole.CONSTRAINT in roles
    assert PropositionRole.DERIVED in roles


def test_bridge_parses_uppercase_relations():
    """P2: uppercase edge labels parse without ValueError."""
    _, deps = bridge_parse(PREMISES_DIR / "project-graph.dot")
    rels = {d.relation_type for d in deps}
    assert RelationType.DEPENDS_ON in rels
    assert RelationType.SUPPORTS in rels


def test_bridge_parses_constrains_relation():
    """T302 (MINOR-1): CONSTRAINS no longer degrades to DEPENDS_ON."""
    bridge_deps = bridge_parse(PREMISES_DIR / "project-graph.dot")[1]
    engine_deps = engine_parse(engine_dot_path())[1]
    bridge_rels = {d.relation_type for d in bridge_deps}
    engine_rels = {d.relation_type for d in engine_deps}

    # Ambos os parsers reconhecem CONSTRAINS (AC-2).
    assert RelationType.CONSTRAINS in bridge_rels
    assert RelationType.CONSTRAINS in engine_rels

    # O edge prem_deadline -> prem_build_possible é CONSTRAINS nos dois.
    for rel, deps in ((bridge_rels, bridge_deps), (engine_rels, engine_deps)):
        edge = [d for d in deps
                if d.from_proposition == "prem_deadline"
                and d.to_proposition == "prem_build_possible"]
        assert edge, "edge prem_deadline->prem_build_possible not found"
        assert edge[0].relation_type == RelationType.CONSTRAINS


def test_bridge_parses_multiline_nodes():
    """Canonical layout has id and attrs on separate lines — both parsed."""
    props, _ = bridge_parse(PREMISES_DIR / "project-graph.dot")
    ids = {p.id for p in props}
    assert "prem_css_playwright_truth" in ids
    assert "prem_build_possible" in ids
    # config lines (node [style=...]) must not become propositions
    assert "node" not in ids
    assert "edge" not in ids


def test_bridge_loads_real_premises():
    """T298/T299 graph is actually loadable (7 props, css premise present)."""
    props, deps, fcs = load_premises_and_conditions()
    assert len(props) == 7
    assert len(deps) == 9
    assert any(p.id == "prem_css_playwright_truth" for p in props)
    assert len(fcs) >= 1


def test_engine_agrees_with_bridge():
    """Both parsers must agree on the canonical graph."""
    bridge_props, bridge_deps = bridge_parse(PREMISES_DIR / "project-graph.dot")
    engine_props, engine_deps = engine_parse(engine_dot_path())
    assert {p.id for p in bridge_props} == {p.id for p in engine_props}
    assert len(bridge_deps) == len(engine_deps)


def test_unknown_role_falls_back_no_crash(tmp_path):
    """Unknown type must not crash — falls back to DERIVED."""
    dot = tmp_path / "bad.dot"
    dot.write_text(
        'digraph g {\n'
        '    "a" [label="A", type=NOT_A_ROLE];\n'
        '    "b" [label="B"];\n'
        '}\n'
    )
    props, _ = bridge_parse(dot)
    modes = {p.role for p in props}
    assert modes == {PropositionRole.DERIVED}


def test_fc_pending_parsed():
    """FalsificationStatus must parse lowercase 'pending'."""
    from aes.gf.propagate import parse_falsification_conditions
    fcs = parse_falsification_conditions(PREMISES_DIR / "fc")
    assert any(fc.status.value == "pending" for fc in fcs)


def test_run_propagation_check_is_dry():
    """--check (dry_run) must not persist loops even with contested ids."""
    import os
    from aes.gf.propagate import run_propagation

    store_path = PREMISES_DIR.parent / "loops" / "active.json"
    before = store_path.read_text() if store_path.exists() else None

    old = os.environ.get("AES_CONTESTED_IDS")
    os.environ["AES_CONTESTED_IDS"] = "prem_build_possible"
    try:
        result = run_propagation(dry_run=True)
    finally:
        if old is None:
            os.environ.pop("AES_CONTESTED_IDS", None)
        else:
            os.environ["AES_CONTESTED_IDS"] = old

    after = store_path.read_text() if store_path.exists() else None
    assert before == after, "dry_run persisted loops"
    assert "Dry run" in result["message"]