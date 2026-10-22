"""Unit tests for the regime package (T130-T134).

Covers: StateMachine lifecycle, append-only JSONL Ledger, PINA protocol
(REGIME-4 syntax, REGIME-7 staleness), ACORDAR / VAI_DORMIR rituals, CLI.
"""

import json
from datetime import datetime, timedelta

import pytest

from lib.epistemic.regime.acordar import Acordar
from lib.epistemic.regime.cli import main as cli_main
from lib.epistemic.regime.ledger import Ledger, LedgerEntryType
from lib.epistemic.regime.pina import PINADecision, PINAProtocol
from lib.epistemic.regime.state import CycleState, StateMachine


@pytest.fixture
def sm() -> StateMachine:
    machine = StateMachine()
    machine.start_cycle()
    return machine


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    return Ledger(ledger_path=tmp_path / "ledger.jsonl")


# ---------------------------------------------------------- state machine


def test_lifecycle_happy_path(sm):
    assert sm.current_cycle.state == CycleState.LOADED
    assert sm.activate()
    assert sm.govern()
    assert sm.hibernate()
    assert sm.resume()
    assert sm.current_cycle.state == CycleState.GOVERNING


def test_invalid_transition_blocks(sm):
    assert sm.govern() is False
    assert sm.current_cycle.state == CycleState.LOADED


def test_hibernate_requires_governing(sm):
    assert sm.hibernate() is False  # from LOADED
    sm.activate()
    assert sm.hibernate() is False  # from ACTIVE


def test_no_cycle_no_transitions():
    machine = StateMachine()
    assert machine.activate() is False
    assert machine.hibernate() is False


def test_end_cycle(sm):
    sm.end_cycle()
    assert sm.current_cycle.state == CycleState.INACTIVE


def test_load_when_no_cycle():
    machine = StateMachine()
    assert machine.load() is True
    assert machine.current_cycle.state == CycleState.LOADED


def test_load_when_already_loaded(sm):
    assert sm.load() is True
    assert sm.current_cycle.state == CycleState.LOADED


def test_can_claim_when_active(sm):
    assert sm.can_claim() is False  # LOADED -> not yet
    sm.activate()
    assert sm.can_claim() is True
    sm.govern()
    assert sm.can_claim() is True


def test_can_claim_when_no_cycle():
    assert StateMachine().can_claim() is False


def test_can_promote_requires_committed_and_legitimacy(sm):
    assert sm.can_promote() is False  # exploratory by default
    sm.set_exploratory(False)
    assert sm.can_promote() is False  # legitimacy not declared
    sm.declare_legitimacy(True)
    assert sm.can_promote() is True


def test_set_position(sm):
    sm.set_position("graph-1", "node-42")
    assert sm.current_cycle.current_graph == "graph-1"
    assert sm.current_cycle.current_node == "node-42"


def test_get_status_no_cycle():
    status = StateMachine().get_status()
    assert status == {"state": "NO_CYCLE", "active": False}


def test_get_status_with_cycle(sm):
    status = sm.get_status()
    assert status["state"] == "LOADED"
    assert status["active"] is True


# ----------------------------------------------------------------- ledger


def test_ledger_persists_jsonl(ledger):
    ledger.add_entry(LedgerEntryType.REGIME_EVENT, content="evt-1")
    ledger.add_entry(LedgerEntryType.CLAIM, content="claim-1")
    lines = ledger.ledger_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["content"] == "evt-1"


def test_ledger_is_append_only_on_disk(ledger):
    ledger.add_entry(LedgerEntryType.REGIME_EVENT, content="first")
    raw_before = ledger.ledger_path.read_text()
    ledger.add_entry(LedgerEntryType.REGIME_EVENT, content="second")
    raw_after = ledger.ledger_path.read_text()
    assert raw_after.startswith(raw_before)


def test_ledger_has_no_clear():
    assert not hasattr(Ledger, "clear")


def test_ledger_reload_from_disk(tmp_path):
    path = tmp_path / "ledger.jsonl"
    Ledger(ledger_path=path).add_entry(LedgerEntryType.AUDIT, content="kept")
    reloaded = Ledger(ledger_path=path)
    assert len(reloaded.get_audits()) == 1


def test_ledger_filters_and_stats(ledger):
    ledger.add_entry(LedgerEntryType.CLAIM, content="c", cycle_id="CY1")
    ledger.add_entry(LedgerEntryType.PINA_DECISION, content="d", cycle_id="CY1")
    assert len(ledger.get_claims(cycle_id="CY1")) == 1
    assert len(ledger.get_cycle_entries("CY1")) == 2
    assert ledger.get_stats()["total_entries"] == 2
    assert ledger.search("c")


def test_ledger_entry_with_gf_id(ledger):
    entry = ledger.add_entry(
        LedgerEntryType.NORMATIVE_CANDIDATE, content="rule", gf_id="NCA-abc123"
    )
    assert entry.gf_id == "NCA-abc123"


def test_ledger_corrupt_line_skipped(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"entry_id":"e1","entry_type":"CLAIM","content":"ok"}\nnot-json\n{"entry_id":"e2","entry_type":"CLAIM","content":"also-ok"}\n')
    ledger = Ledger(ledger_path=path)
    assert len(ledger._entries) == 2


def test_ledger_empty_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("")
    ledger = Ledger(ledger_path=path)
    assert len(ledger._entries) == 0


def test_ledger_empty_lines_skipped(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text('\n\n{"entry_id":"e1","entry_type":"CLAIM","content":"ok"}\n\n')
    ledger = Ledger(ledger_path=path)
    assert len(ledger._entries) == 1


def test_ledger_stats_empty(ledger):
    stats = ledger.get_stats()
    assert stats["total_entries"] == 0
    assert stats["first_entry"] is None
    assert stats["last_entry"] is None


# ------------------------------------------------------------------- PINA


def make_pina(sm, ledger):
    return PINAProtocol(state_machine=sm, ledger=ledger)


def test_pina_propose_creates_pending(sm, ledger):
    pina = make_pina(sm, ledger)
    result = pina.propose_candidate("doc.md", "All claims must cite sources", "§2")
    assert result.success
    assert len(pina.get_pending()) == 1
    assert ledger.get_nca()


def test_pina_silence_is_not_a_decision(sm, ledger):
    pina = make_pina(sm, ledger)
    pina.propose_candidate("doc.md", "rule", "§1")
    assert len(pina.get_pending()) == 1
    assert pina.get_active_invariants() == []


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("A", PINADecision.INCORPORATE),
        ("ACCEPT", PINADecision.INCORPORATE),
        ("B", PINADecision.DO_NOT_INCORPORATE),
        ("REJECT", PINADecision.DO_NOT_INCORPORATE),
        ("C", PINADecision.DEFER),
        ("DEFER", PINADecision.DEFER),
    ],
)
def test_pina_accepts_letters_and_words(sm, ledger, decision, expected):
    pina = make_pina(sm, ledger)
    nca_id = pina.propose_candidate("doc.md", "rule", "§1").nca_id
    result = pina.decide(nca_id, decision, reason="test rationale")
    assert result.success
    assert result.decision == expected.value


def test_pina_incorporate_activates_invariant(sm, ledger):
    pina = make_pina(sm, ledger)
    nca_id = pina.propose_candidate("doc.md", "rule", "§1").nca_id
    pina.decide(nca_id, "ACCEPT", reason="ratified")
    assert pina.is_invariant(nca_id)
    assert len(pina.get_active_invariants()) == 1


def test_pina_invalid_decision_rejected(sm, ledger):
    pina = make_pina(sm, ledger)
    nca_id = pina.propose_candidate("doc.md", "rule", "§1").nca_id
    assert pina.decide(nca_id, "MAYBE").success is False


def test_pina_unknown_nca_rejected(sm, ledger):
    assert make_pina(sm, ledger).decide("NCA-nope", "A").success is False


def test_pina_reason_recorded_in_ledger(sm, ledger):
    pina = make_pina(sm, ledger)
    nca_id = pina.propose_candidate("doc.md", "rule", "§1").nca_id
    pina.decide(nca_id, "DEFER", reason="awaiting owner input")
    decisions = [
        e
        for e in ledger.get_cycle_entries(sm.current_cycle.cycle_id)
        if e.entry_type == LedgerEntryType.PINA_DECISION.value
    ]
    assert decisions and decisions[0].metadata["reason"] == "awaiting owner input"


def test_pina_stale_pending_flagged(sm, ledger):
    pina = make_pina(sm, ledger)
    nca_id = pina.propose_candidate("doc.md", "rule", "§1").nca_id
    pina._candidates[nca_id].created_at = datetime.now() - timedelta(hours=25)
    stale = pina.get_stale_pending(hours=24)
    assert [c["nca_id"] for c in stale] == [nca_id]
    assert pina.get_stale_pending(hours=48) == []


def test_pina_double_decide_does_not_crash(sm, ledger):
    pina = make_pina(sm, ledger)
    nca_id = pina.propose_candidate("doc.md", "rule", "§1").nca_id
    assert pina.decide(nca_id, "ACCEPT").success
    assert pina.decide(nca_id, "REJECT").success  # overwrites
    assert not pina.is_invariant(nca_id)


def test_pina_get_status_with_pending(sm, ledger):
    pina = make_pina(sm, ledger)
    pina.propose_candidate("doc.md", "rule", "§1")
    status = pina.get_status()
    assert status["pending_candidates"] == 1
    assert status["active_invariants"] == 0


def test_pina_candidate_summary_includes_scope(sm, ledger):
    pina = make_pina(sm, ledger)
    pina.propose_candidate("doc.md", "rule", "§1", graph_scope="scope-x")
    pending = pina.get_pending()
    assert pending[0]["graph_scope"] == "scope-x"


# ---------------------------------------------------------------- ACORDAR


def test_acordar_requires_anchor_and_intention(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    assert ritual.execute("", "intent").success is False
    assert ritual.execute("2026-06-11", "").success is False
    assert sm.current_cycle.state == CycleState.LOADED


def test_acordar_activates_regime(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    result = ritual.execute("2026-06-11", "port the rituals", mode="committed")
    assert result.success
    assert sm.current_cycle.state == CycleState.GOVERNING
    assert sm.current_cycle.temporal_anchor == "2026-06-11"
    assert ledger.get_regime_events()


def test_acordar_without_cycle_fails():
    ritual = Acordar(state_machine=StateMachine())
    assert ritual.execute("2026-06-11", "x").success is False


def test_acordar_exploratory_mode(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    ritual.execute("2026-06-11", "explore", mode="exploratory")
    assert sm.current_cycle.is_exploratory is True


def test_acordar_committed_mode(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    ritual.execute("2026-06-11", "commit", mode="committed")
    assert sm.current_cycle.is_exploratory is False


def test_acordar_whitespace_only_anchor(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    assert ritual.execute("   ", "intent").success is False


# ------------------------------------------------------------- VAI_DORMIR


def governed(sm, ledger):
    Acordar(state_machine=sm, ledger=ledger).execute("2026-06-11", "test")
    return Acordar(state_machine=sm, ledger=ledger)


def test_vai_dormir_consolidates_and_hibernates(sm, ledger):
    ritual = governed(sm, ledger)
    report = ritual.vai_dormir()
    assert report["success"]
    assert sm.current_cycle.state == CycleState.HIBERNATED
    types = [e.entry_type for e in ledger.get_cycle_entries(sm.current_cycle.cycle_id)]
    assert LedgerEntryType.CONSOLIDATION.value in types


def test_vai_dormir_blocked_outside_governing(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    assert ritual.vai_dormir()["success"] is False


def test_resume_after_hibernation(sm, ledger):
    ritual = governed(sm, ledger)
    ritual.vai_dormir()
    assert ritual.resume()["success"]
    assert sm.current_cycle.state == CycleState.GOVERNING


def test_resume_without_hibernation_fails(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    assert ritual.resume()["success"] is False


def test_consolidate_includes_stats(sm, ledger):
    ritual = governed(sm, ledger)
    summary = ritual.consolidate()
    assert "claims_count" in summary
    assert "temporal_anchor" in summary


def test_vai_dormir_cycle_id_in_report(sm, ledger):
    ritual = governed(sm, ledger)
    report = ritual.vai_dormir()
    assert "cycle_id" in report


def test_get_status_after_acordar(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    ritual.execute("2026-06-11", "test")
    status = ritual.get_status()
    assert status["temporal_anchor_declared"] is True
    assert status["intention_declared"] is True


def test_get_status_before_acordar(sm, ledger):
    ritual = Acordar(state_machine=sm, ledger=ledger)
    status = ritual.get_status()
    assert status["temporal_anchor_declared"] is False
    assert status["intention_declared"] is False


# -------------------------------------------------------------------- CLI


def run_cli(*args, cwd, monkeypatch, capsys):
    monkeypatch.setenv("AES_REGIME_STATE", str(cwd / "state.json"))
    monkeypatch.setenv("AES_REGIME_LEDGER", str(cwd / "l.jsonl"))
    code = cli_main(list(args))
    return code, capsys.readouterr().out


def test_cli_full_ritual_flow(tmp_path, monkeypatch, capsys):
    code, out = run_cli(
        "acordar", "--anchor", "2026-06-11", "--intention", "cli test",
        cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 0
    assert "GOVERNING" in out

    code, out = run_cli("status", cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0
    assert "GOVERNING" in out

    code, out = run_cli(
        "vai-dormir", cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 0
    assert "HIBERNATED" in out

    code, out = run_cli("resume", cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0


def test_cli_pina_flow(tmp_path, monkeypatch, capsys):
    run_cli(
        "acordar", "--anchor", "2026-06-11", "--intention", "pina",
        cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    code, out = run_cli(
        "pina-propose", "--source", "doc.md", "--statement", "rule", "--location", "§1",
        cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 0
    nca_id = out.strip().splitlines()[-1].split()[0]
    code, out = run_cli(
        "pina-decide", "--nca-id", nca_id, "--decision", "ACCEPT", "--reason", "ok",
        cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 0
    assert "INVARIANT" in out.upper()


def test_cli_vai_dormir_without_acordar_fails(tmp_path, monkeypatch, capsys):
    code, out = run_cli(
        "vai-dormir", cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 1


def test_cli_status_no_cycle(tmp_path, monkeypatch, capsys):
    code, out = run_cli(
        "status", cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 0


def test_cli_resume_without_hibernation(tmp_path, monkeypatch, capsys):
    code, out = run_cli(
        "resume", cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys,
    )
    assert code == 1


def test_cli_invalid_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AES_REGIME_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("AES_REGIME_LEDGER", str(tmp_path / "l.jsonl"))
    with pytest.raises(SystemExit) as exc:
        cli_main(["invalid-cmd"])
    assert exc.value.code == 2
