"""Tests for regime CLI uncovered paths (T176)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from lib.epistemic.regime.cli import main, _rebuild_pina, _load_machine
from lib.epistemic.regime.ledger import Ledger, LedgerEntryType
from lib.epistemic.regime.state import StateMachine


@pytest.fixture
def env(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    ledger_path = tmp_path / "ledger.jsonl"
    ilhas_path = tmp_path / "ilhas"
    ilhas_path.mkdir()
    monkeypatch.setenv("AES_REGIME_STATE", str(state_path))
    monkeypatch.setenv("AES_REGIME_LEDGER", str(ledger_path))
    monkeypatch.setenv("AES_ILHAS_DIR", str(ilhas_path))
    shadow_path = tmp_path / "shadow"
    monkeypatch.setenv("AES_SHADOW_DIR", str(shadow_path))
    return state_path, ledger_path, ilhas_path


class TestRebuildPina:
    def test_rebuilds_from_ledger(self, tmp_path):
        state_path = tmp_path / "state.json"
        ledger_path = tmp_path / "ledger.jsonl"
        machine = StateMachine()
        machine.start_cycle()
        ledger = Ledger(ledger_path=ledger_path)
        ledger.add_entry(
            LedgerEntryType.NORMATIVE_CANDIDATE,
            content="test statement",
            gf_id="NCA-001",
            cycle_id=machine.current_cycle.cycle_id,
            metadata={"source": "test", "location": "test.md"},
        )
        pina = _rebuild_pina(machine, ledger)
        assert "NCA-001" in pina._candidates

    def test_marks_decided_ncas(self, tmp_path):
        state_path = tmp_path / "state.json"
        ledger_path = tmp_path / "ledger.jsonl"
        machine = StateMachine()
        machine.start_cycle()
        ledger = Ledger(ledger_path=ledger_path)
        cycle_id = machine.current_cycle.cycle_id
        ledger.add_entry(
            LedgerEntryType.NORMATIVE_CANDIDATE,
            content="test",
            gf_id="NCA-001",
            cycle_id=cycle_id,
            metadata={"source": "test", "location": "test.md"},
        )
        ledger.add_entry(
            LedgerEntryType.PINA_DECISION,
            content="accepted",
            gf_id="NCA-001",
            cycle_id=cycle_id,
            metadata={"decision": "A"},
        )
        pina = _rebuild_pina(machine, ledger)
        assert pina._candidates["NCA-001"].decided_at is not None
        assert "NCA-001" in pina._active_invariants


class TestMemoryCommands:
    def test_memory_list_empty(self, env, capsys):
        state_path, ledger_path, ilhas_path = env
        rc = main(["memory-list"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Total: 0 islands" in captured.out

    def test_memory_list_active_only(self, env, capsys):
        state_path, ledger_path, ilhas_path = env
        rc = main(["memory-list", "--active-only"])
        assert rc == 0

    def test_memory_show_not_found(self, env, capsys):
        state_path, ledger_path, ilhas_path = env
        rc = main(["memory-show", "NONEXISTENT"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_memory_sleep_no_cycle(self, env, capsys):
        state_path, ledger_path, ilhas_path = env
        rc = main(["memory-sleep"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "No active cycle" in captured.out

    def test_memory_sleep_with_cycle(self, env, capsys):
        state_path, ledger_path, ilhas_path = env
        # Create a state file with an active cycle
        from datetime import datetime
        state_data = {
            "cycle_id": "test-cycle",
            "state": "ACTIVE",
            "started_at": datetime.now().isoformat(),
            "claims_count": 0,
            "nca_pending": 0,
            "is_exploratory": True,
            "legitimacy_declared": False,
            "temporal_anchor": "2026-07-22",
            "intention": "test",
        }
        state_path.write_text(json.dumps(state_data))
        rc = main(["memory-sleep"])
        assert rc == 0


class TestStatusCommand:
    def test_status_no_cycle(self, env, capsys):
        rc = main(["status"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "NO_CYCLE" in captured.out


class TestAcordarCommand:
    def test_acordar_creates_cycle(self, env, capsys):
        rc = main(["acordar", "--anchor", "2026-07-22", "--intention", "test"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "State:" in captured.out


class TestVaiDormirCommand:
    def test_vai_dormir_no_interacao(self, env, capsys):
        # Need an active cycle first
        main(["acordar", "--anchor", "2026-07-22", "--intention", "test"])
        rc = main(["vai-dormir"])
        assert rc == 0


class TestResumeCommand:
    def test_resume_with_tarefa(self, env, capsys):
        # Start and sleep first
        main(["acordar", "--anchor", "2026-07-22", "--intention", "test"])
        main(["vai-dormir"])
        rc = main(["resume", "--tarefa", "re-entry task"])
        assert rc == 0
        captured = capsys.readouterr()
        # Should print bundle info if tarefa provided
        assert "Bundle:" in captured.out or "message" in captured.out.lower()


class TestFallbackReturn:
    def test_unknown_command_returns_2(self, env):
        # argparse will reject unknown commands, but test the fallback
        # by using a valid command that falls through (impossible with argparse)
        # Instead, test that main returns non-zero for invalid args
        with pytest.raises(SystemExit):
            main(["nonexistent-command"])
