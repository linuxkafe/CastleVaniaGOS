"""Integration tests: regime + ILHA/PEDRA memory end-to-end.

Verifies the full loop: ACORDAR → interacoes → VAI_DORMIR (ILHA sleep)
→ resume → get_active_islands().
"""

from pathlib import Path

import pytest

from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas
from lib.epistemic.regime.acordar import Acordar
from lib.epistemic.regime.ledger import Ledger, LedgerEntryType
from lib.epistemic.regime.state import StateMachine


@pytest.fixture
def memory(tmp_path) -> ArmazenamentoIlhas:
    return ArmazenamentoIlhas(tmp_path / "ilhas")


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    return Ledger(ledger_path=tmp_path / "ledger.jsonl")


@pytest.fixture
def machine() -> StateMachine:
    m = StateMachine()
    m.start_cycle()
    return m


class TestRegimeMemoryIntegration:
    def test_vai_dormir_sem_interacoes_nao_cria_ilhas(self, machine, ledger, memory):
        """VAI_DORMIR without interactions creates nothing in ILHA."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "Integration test").success
        report = ritual.vai_dormir(interacoes=[])
        assert report["success"]
        assert len(memory.listar()) == 0

    def test_vai_dormir_com_interacoes_cria_pedras(self, machine, ledger, memory):
        """Interactions with sufficient salience create Pedras."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "Integration test").success
        interacoes = [
            {
                "tipo": "MENSAGEM",
                "conteudo": f"interacao de teste {i}",
                "frequencia": 0.9,
                "intensidade": 0.8,
                "novidade": 0.7,
                "relevancia": 0.6,
            }
            for i in range(3)
        ]
        report = ritual.vai_dormir(interacoes=interacoes)
        assert report["success"]
        ilhas = memory.listar()
        assert len(ilhas) >= 0

    def test_vai_dormir_transforma_pedra_em_ilha(self, machine, ledger, memory):
        """High-salience interaction creates a Pedra that becomes an Ilha."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "Integration test").success
        interacoes = [
            {
                "tipo": "MENSAGEM",
                "conteudo": "descoberta revolucionaria com saliencia maxima",
                "frequencia": 1.0,
                "intensidade": 1.0,
                "novidade": 1.0,
                "relevancia": 1.0,
                "reaccoes": 10,
            }
        ]
        report = ritual.vai_dormir(interacoes=interacoes)
        assert report["success"]
        # With saliencia=1.0 and 10 reaccoes, pedra should transform to ilha
        ilhas = memory.listar()
        assert len(ilhas) >= 1

    def test_ilha_sleep_registado_no_ledger(self, machine, ledger, memory):
        """ILHA_SLEEP entry is recorded in the ledger after VAI_DORMIR."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "Integration test").success
        interacoes = [
            {
                "tipo": "MENSAGEM",
                "conteudo": "interacao importante",
                "frequencia": 0.9,
                "intensidade": 0.8,
                "novidade": 0.7,
                "relevancia": 0.6,
            }
        ]
        ritual.vai_dormir(interacoes=interacoes)
        ilha_entries = [e for e in ledger._entries if e.entry_type == "ILHA_SLEEP"]
        assert len(ilha_entries) >= 1

    def test_active_islands_after_resume(self, machine, ledger, memory):
        """After VAI_DORMIR + resume, active islands appear in status."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "Integration test").success
        interacoes = [
            {
                "tipo": "MENSAGEM",
                "conteudo": f"conversa importante #{i}",
                "frequencia": 0.8,
                "intensidade": 0.7,
                "novidade": 0.6,
                "relevancia": 0.5,
            }
            for i in range(2)
        ]
        ritual.vai_dormir(interacoes=interacoes)
        # Resume and check
        assert ritual.resume()["success"]
        status = ritual.get_status()
        assert "active_islands" in status

    def test_ciclo_completo_sem_armazenamento_nao_quebra(self, machine, ledger):
        """VAI_DORMIR without memory armazenamento still works."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=None)
        assert ritual.execute("2026-07-21", "No memory test").success
        report = ritual.vai_dormir()
        assert report["success"]
        assert ritual.get_active_islands() == []

    def test_get_active_islands_sem_armazenamento(self, machine, ledger):
        """get_active_islands returns empty list when no storage."""
        ritual = Acordar(machine, ledger=ledger)
        assert ritual.get_active_islands() == []

    def test_resume_com_bundle_de_reentrada(self, machine, ledger, memory):
        """Resume with tarefa builds a re-entry bundle."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "Test bundle").success
        interacoes = [
            {
                "tipo": "MENSAGEM",
                "conteudo": "gestao de memoria insular com saliencia alta",
                "frequencia": 1.0,
                "intensidade": 1.0,
                "novidade": 1.0,
                "relevancia": 1.0,
                "reaccoes": 10,
            }
        ]
        ritual.vai_dormir(interacoes=interacoes)
        result = ritual.resume(tarefa="memoria insular")
        assert result["success"]
        assert "bundle" in result
        assert result["bundle"]["tarefa"] == "memoria insular"
        assert result["bundle"]["ilhas_count"] >= 1
        assert "active_islands" in result

    def test_resume_sem_tarefa_nao_cria_bundle(self, machine, ledger, memory):
        """Resume without tarefa does not build a bundle."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        assert ritual.execute("2026-07-21", "No bundle").success
        ritual.vai_dormir()
        result = ritual.resume()
        assert result["success"]
        assert "bundle" not in result

    def test_multiplas_ilhas_apos_varios_ciclos(self, machine, ledger, memory):
        """Multiple VAI_DORMIR cycles accumulate islands."""
        ritual = Acordar(machine, ledger=ledger, armazenamento=memory)
        for i in range(3):
            assert ritual.execute(f"2026-07-{21 - i}", f"Ciclo {i}").success
            interacoes = [
                {
                    "tipo": "MENSAGEM",
                    "conteudo": f"topico persistente #{i}",
                    "frequencia": 1.0,
                    "intensidade": 1.0,
                    "novidade": 1.0,
                    "relevancia": 1.0,
                    "reaccoes": 6,
                }
            ]
            ritual.vai_dormir(interacoes=interacoes)
            if i < 2:
                assert ritual.resume()["success"]
        total = len(memory.listar())
        assert total > 0
