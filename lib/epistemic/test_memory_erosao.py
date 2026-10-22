"""Unit tests for the ILHA/PEDRA memory system.

Split from test_memory.py for maintainability (T163).
"""

from pathlib import Path
from datetime import datetime, timedelta

import pytest

from lib.epistemic.memory.estados import (
    EstadoIlha,
    EstadoPedra,
    EstadoClaim,
    TipoInteracao,
    TipoRelacao,
)
from lib.epistemic.memory.models import (
    Saliencia,
    Pedra,
    MembroIlha,
    RelacaoIlha,
    HistoricoReativacao,
    Ilha,
    Claim,
)
from lib.epistemic.memory.saliencia import (
    CalculadorSaliencia,
    CalculadorFrequencia,
    CalculadorIntensidade,
    CalculadorNovidade,
    CalculadorRelevancia,
    calcular_saliencia_completa,
)
from lib.epistemic.memory.erosao import (
    DinamicaErosao,
    GestorReativacoes,
)
from lib.epistemic.memory.gerenciador import (
    ArmazenamentoIlhas,
    GestorIlhas,
)
from lib.epistemic.memory.relacoes import (
    CalculadorSimilaridade,
    GestorRelacoes,
)
from lib.epistemic.memory.dormir import (
    ProcessadorBatch,
    ir_dormir,
)

class TestDinamicaErosao:
    def test_aplicar_decay_reduz_score(self):
        from lib.epistemic.memory.models import Ilha
        ilha = Ilha(score_ativacao=1.0)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        erosao.aplicar_decay_todas(dias=1)
        assert ilha.score_ativacao == pytest.approx(0.95)

    def test_decay_multiplos_dias(self):
        ilha = Ilha(score_ativacao=1.0)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        erosao.aplicar_decay_todas(dias=10)
        assert ilha.score_ativacao == pytest.approx(0.95 ** 10)

    def test_estado_transita_para_erodindo(self):
        ilha = Ilha(score_ativacao=0.05)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        erosao._actualizar_estado(ilha)
        assert ilha.estado == EstadoIlha.ERODENDO

    def test_estado_transita_para_dorminte(self):
        ilha = Ilha(score_ativacao=0.005)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        erosao._actualizar_estado(ilha)
        assert ilha.estado == EstadoIlha.DORMINTE

    def test_reativar_ilha_aumenta_score(self):
        ilha = Ilha(score_ativacao=0.05, estado=EstadoIlha.ERODENDO)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        result = erosao.reativar_ilha(ilha.id, boost=0.5)
        assert result is not None
        assert ilha.score_ativacao == 0.55
        assert ilha.estado == EstadoIlha.ATIVA

    def test_reativar_ilha_inexistente(self):
        erosao = DinamicaErosao()
        assert erosao.reativar_ilha("nao-existe") is None

    def test_calcular_tempo_para_decay(self):
        ilha = Ilha(score_ativacao=1.0)
        erosao = DinamicaErosao()
        dias = erosao.calcular_tempo_para_decay(ilha, target_score=0.5)
        assert dias is not None
        assert dias > 0

    def test_estatisticas_decay(self):
        erosao = DinamicaErosao()
        erosao.registar_ilha(Ilha(score_ativacao=0.8, estado=EstadoIlha.ATIVA))
        erosao.registar_ilha(Ilha(score_ativacao=0.05, estado=EstadoIlha.ERODENDO))
        stats = erosao.get_estatisticas_decay()
        assert stats["total_ilhas"] == 2
        assert stats["por_estado"]["ATIVA"] == 1
        assert stats["por_estado"]["ERODENDO"] == 1


class TestGestorReativacoes:
    def test_reativacao_aplica_boost_correto(self):
        ilha = Ilha(score_ativacao=0.05, estado=EstadoIlha.DORMINTE)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        gestor = GestorReativacoes(erosao)
        result = gestor.registar_reativacao(ilha.id, tipo="edicao")
        assert result is not None
        assert result.score_ativacao == pytest.approx(0.15)
        assert len(result.historico_reativacoes) == 1

    def test_tipos_diferentes_boost_diferente(self):
        ilha = Ilha(score_ativacao=0.0, estado=EstadoIlha.DORMINTE)
        erosao = DinamicaErosao(ilhas={ilha.id: ilha})
        gestor = GestorReativacoes(erosao)
        gestor.registar_reativacao(ilha.id, tipo="consulta")
        assert ilha.score_ativacao == 0.05
