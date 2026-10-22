"""Tests for lib/epistemic/premises/wiring.py — regime/ILHA integration hooks."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from lib.epistemic.premises.wiring import run_propagation_for_regime, propagate_into_ilha


class TestRunPropagationForRegime:
    def test_returns_skipped_when_no_graph(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.epistemic.premises.wiring.PremisesEngine") as MockEngine:
                inst = MockEngine.return_value
                inst.load_premises.return_value = False
                result = run_propagation_for_regime(premises_dir=tmpdir)
                assert result["propagation"] == "skipped"
                assert "No premise graph found" in result["message"]

    def test_returns_clean_when_no_loops(self):
        with patch("lib.epistemic.premises.wiring.PremisesEngine") as MockEngine:
            inst = MockEngine.return_value
            inst.load_premises.return_value = True
            inst.verify_and_propagate.return_value = {"opened_loops": 0, "affected": [], "seeds": {}}
            inst.get_blockers.return_value = []
            result = run_propagation_for_regime()
            assert result["propagation"] == "clean"
            assert result["blocker_count"] == 0

    def test_returns_completed_when_loops_opened(self):
        with patch("lib.epistemic.premises.wiring.PremisesEngine") as MockEngine:
            inst = MockEngine.return_value
            inst.load_premises.return_value = True
            inst.verify_and_propagate.return_value = {"opened_loops": 2, "affected": ["P1"], "seeds": {"P2": "conflict"}}
            inst.get_blockers.return_value = ["P1"]
            result = run_propagation_for_regime()
            assert result["propagation"] == "completed"
            assert result["blocker_count"] == 1

    def test_returns_blockers_from_engine(self):
        with patch("lib.epistemic.premises.wiring.PremisesEngine") as MockEngine:
            inst = MockEngine.return_value
            inst.load_premises.return_value = True
            inst.verify_and_propagate.return_value = {"opened_loops": 1, "affected": ["P1"], "seeds": {}}
            inst.get_blockers.return_value = ["P1", "P2"]
            result = run_propagation_for_regime()
            assert result["blockers"] == ["P1", "P2"]
            assert result["blocker_count"] == 2


class TestPropagateIntoIlha:
    def test_returns_zero_when_no_affected_or_seeds(self):
        armazenamento = MagicMock()
        count = propagate_into_ilha(armazenamento, "s1", {"affected": [], "seeds": {}})
        assert count == 0

    def test_returns_zero_when_no_islands(self):
        armazenamento = MagicMock()
        armazenamento.listar.return_value = []
        result = propagate_into_ilha(armazenamento, "s1", {"affected": ["P1"], "seeds": {}})
        assert result == 0

    def test_returns_zero_when_armazenamento_has_no_listar(self):
        armazenamento = MagicMock(spec=[])  # no listar method
        result = propagate_into_ilha(armazenamento, "s1", {"affected": ["P1"], "seeds": {}})
        assert result == 0

    @patch("lib.epistemic.memory.nanopub_bridge.criar_claims")
    def test_creates_claims_for_affected(self, mock_criar):
        mock_criar.return_value = 1
        armazenamento = MagicMock()
        armazenamento.listar.return_value = [{"id": "ilha1"}]
        count = propagate_into_ilha(armazenamento, "s1", {"affected": ["P1"], "seeds": {}})
        assert count == 1
        mock_criar.assert_called_once()
        interacoes = mock_criar.call_args[0][0]
        assert len(interacoes) == 1
        assert interacoes[0]["sd_id"] == "PROPAGATION-P1"
        assert interacoes[0]["epistemic_state"] == "INFERIDA"

    @patch("lib.epistemic.memory.nanopub_bridge.criar_claims")
    def test_creates_claims_for_seeds(self, mock_criar):
        mock_criar.return_value = 1
        armazenamento = MagicMock()
        armazenamento.listar.return_value = [{"id": "ilha1"}]
        count = propagate_into_ilha(armazenamento, "s1", {"affected": [], "seeds": {"P2": "conflict"}})
        assert count == 1
        interacoes = mock_criar.call_args[0][0]
        assert len(interacoes) == 1
        assert interacoes[0]["sd_id"] == "PROPAGATION-SEED-P2"
        assert interacoes[0]["epistemic_state"] == "FALSIFICADO"

    @patch("lib.epistemic.memory.nanopub_bridge.criar_claims")
    def test_skips_seed_when_already_in_affected(self, mock_criar):
        mock_criar.return_value = 1
        armazenamento = MagicMock()
        armazenamento.listar.return_value = [{"id": "ilha1"}]
        count = propagate_into_ilha(armazenamento, "s1", {"affected": ["P1"], "seeds": {"P1": "conflict"}})
        assert count == 1
        interacoes = mock_criar.call_args[0][0]
        assert len(interacoes) == 1
        assert interacoes[0]["sd_id"] == "PROPAGATION-P1"

    @patch("lib.epistemic.memory.nanopub_bridge.criar_claims")
    def test_returns_zero_when_no_interacoes_after_dedup(self, mock_criar):
        mock_criar.return_value = 1
        armazenamento = MagicMock()
        armazenamento.listar.return_value = [{"id": "ilha1"}]
        count = propagate_into_ilha(armazenamento, "s1", {"affected": ["P1"], "seeds": {"P1": "conflict"}})
        assert count == 1
        assert mock_criar.call_args[0][0][0]["sd_id"] == "PROPAGATION-P1"
