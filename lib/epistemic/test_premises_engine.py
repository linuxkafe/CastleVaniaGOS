"""Tests for PremisesEngine — DOT parsing, propagation, loop persistence."""

import json
from pathlib import Path

import pytest

from lib.epistemic.premises.engine import (
    PremisesEngine,
    _parse_dot,
)
from lib.epistemic.premises.dot_common import relation_type


SIMPLE_DOT = '''digraph G {
    "F1" [type=FOUNDATIONAL label="Water boils at 100C"];
    "D1" [type=DERIVED label="Derived claim one"];
    "D2" [type=DERIVED label="Derived claim two"];
    "D1" -> "F1" [label=DEPENDS_ON];
    "D2" -> "D1" [label=DEPENDS_ON];
}
'''

SIMPLE_DOT_WITH_SUPPORTS = '''digraph G {
    "A" [type=ASSUMPTION label="Assumption A"];
    "B" [type=DERIVED label="Derived B"];
    "B" -> "A" [label=SUPPORTS];
}
'''


def test_parse_simple_dot(tmp_path):
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT)
    props, deps = _parse_dot(d)
    assert len(props) == 3
    assert len(deps) == 2
    ids = {p.id for p in props}
    assert "F1" in ids
    assert "D1" in ids
    assert "D2" in ids


def test_parse_dot_with_supports(tmp_path):
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT_WITH_SUPPORTS)
    props, deps = _parse_dot(d)
    assert len(props) == 2
    assert len(deps) == 1
    assert deps[0].relation_type == relation_type("SUPPORTS")


def test_resolve_relation_type():
    """T302: unificado no resolvedor comum de dot_common (AC-4).

    _resolve_relation_type de engine.py foi removido — o parser usa agora
    dot_common.relation_type(), que resolve por __members__ e mantém o
    fallback DEPENDS_ON para valores genuinamente desconhecidos.
    """
    assert relation_type("DEPENDS_ON").value == "depends_on"
    assert relation_type("SUPPORTS").value == "supports"
    assert relation_type("CONTRADICTS").value == "contradicts"
    assert relation_type("CONSTRAINS").value == "constrains"
    assert relation_type("UNKNOWN").value == "depends_on"


def test_engine_no_premises(tmp_path):
    engine = PremisesEngine(premises_dir=tmp_path)
    assert engine.load_premises() is False
    result = engine.verify_and_propagate()
    assert result["opened_loops"] == 0
    assert "No premise graph" in result["message"]


def test_engine_clean_propagation(tmp_path):
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT)
    engine = PremisesEngine(premises_dir=tmp_path, loop_store_path=tmp_path / "loops" / "active.json")
    loaded = engine.load_premises()
    assert loaded
    result = engine.verify_and_propagate()
    # No falsification conditions => no fallen premises => no loops
    assert result["opened_loops"] == 0
    assert "No fallen premises" in result["message"]


def test_engine_with_failed_fc(tmp_path):
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT)
    fc_dir = tmp_path / "fc"
    fc_dir.mkdir()
    fc_file = fc_dir / "FC-001.json"
    fc_file.write_text(json.dumps({
        "id": "FC-001",
        "proposition_id": "F1",
        "condition_text": "Water must boil at 100C at sea level",
        "status": "failed",
        "evidence_needed": "Experiment shows different boiling point",
    }))
    loops_dir = tmp_path / "loops"
    loops_dir.mkdir()
    store_path = loops_dir / "active.json"
    engine = PremisesEngine(premises_dir=tmp_path, loop_store_path=store_path)
    loaded = engine.load_premises()
    assert loaded
    result = engine.verify_and_propagate()
    assert result["opened_loops"] > 0
    assert "Opened" in result["message"]
    assert store_path.exists()
    data = json.loads(store_path.read_text())
    assert len(data["loops"]) >= result["opened_loops"]
    for loop in data["loops"]:
        assert loop["status"] == "OPEN"
        assert loop["criticality"] == "high"


def test_engine_blockers(tmp_path):
    engine = PremisesEngine(loop_store_path=tmp_path / "active.json")
    assert engine.count_blocking_loops() == 0
    assert engine.get_blockers() == []

    store = tmp_path / "active.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps({
        "loops": [
            {"id": "L1", "source_id": "F1", "status": "OPEN", "criticality": "HIGH", "closure_policy": "premise_fallen"},
            {"id": "L2", "source_id": "D1", "status": "OPEN", "criticality": "LOW", "closure_policy": "tension"},
            {"id": "L3", "source_id": "D2", "status": "CLOSED", "criticality": "HIGH", "closure_policy": "resolved"},
        ]
    }))
    engine2 = PremisesEngine(loop_store_path=store)
    assert engine2.count_blocking_loops() == 1
    blockers = engine2.get_blockers()
    assert len(blockers) == 1
    assert "F1" in blockers[0]


def test_engine_idempotent(tmp_path):
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT)
    fc_dir = tmp_path / "fc"
    fc_dir.mkdir()
    fc_file = fc_dir / "FC-001.json"
    fc_file.write_text(json.dumps({
        "id": "FC-001",
        "proposition_id": "F1",
        "condition_text": "Water must boil at 100C",
        "status": "FAILED",
    }))
    store_path = tmp_path / "loops" / "active.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    engine = PremisesEngine(premises_dir=tmp_path, loop_store_path=store_path)
    result1 = engine.verify_and_propagate()
    result2 = engine.verify_and_propagate()
    assert result1["opened_loops"] > 0
    assert result2["opened_loops"] == 0


def test_has_premises(tmp_path):
    engine = PremisesEngine(premises_dir=tmp_path)
    assert engine.has_premises() is False
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT)
    engine2 = PremisesEngine(premises_dir=tmp_path)
    engine2.load_premises()
    assert engine2.has_premises() is True


def test_get_failed_conditions(tmp_path):
    fc_dir = tmp_path / "fc"
    fc_dir.mkdir()
    fc_file = fc_dir / "FC-001.json"
    fc_file.write_text(json.dumps({
        "id": "FC-001",
        "proposition_id": "F1",
        "condition_text": "test",
        "status": "FAILED",
    }))
    fc_file2 = fc_dir / "FC-002.json"
    fc_file2.write_text(json.dumps({
        "id": "FC-002",
        "proposition_id": "D1",
        "condition_text": "test2",
        "status": "PENDING",
    }))
    d = tmp_path / "graph.dot"
    d.write_text(SIMPLE_DOT)
    engine = PremisesEngine(premises_dir=tmp_path)
    engine.load_premises()
    failed = engine.get_failed_conditions()
    assert len(failed) == 1
    assert failed[0].id == "FC-001"
