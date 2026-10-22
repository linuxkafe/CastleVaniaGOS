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

class TestProcessadorBatch:
    def test_executar_sem_interacoes(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        proc = ProcessadorBatch(store)
        relatorio = proc.executar("sess-1", [])
        assert relatorio["sucesso"]
        assert relatorio["pedras_criadas"] == 0
        assert relatorio["ilhas_criadas"] == 0

    def test_identificar_pedras_baixa_salienca(self):
        store = ArmazenamentoIlhas.__new__(ArmazenamentoIlhas)
        proc = ProcessadorBatch(store)
        interacoes = [{"conteudo": "boring", "frequencia": 0.1, "intensidade": 0.1, "novidade": 0.1, "relevancia": 0.1}]
        pedras = proc._identificar_pedras(interacoes)
        assert len(pedras) == 0

    def test_identificar_pedras_alta_salienca(self):
        store = ArmazenamentoIlhas.__new__(ArmazenamentoIlhas)
        proc = ProcessadorBatch(store)
        interacoes = [{"conteudo": "important breakthrough!", "frequencia": 1.0, "intensidade": 1.0, "novidade": 1.0, "relevancia": 1.0}]
        pedras = proc._identificar_pedras(interacoes)
        assert len(pedras) == 1
        assert pedras[0].saliencia.valor >= 0.3

    def test_deve_transformar_em_ilha(self):
        store = ArmazenamentoIlhas.__new__(ArmazenamentoIlhas)
        proc = ProcessadorBatch(store)
        pedra_alta = Pedra(saliencia=Saliencia(valor=0.9), contagem_reacoes=10)
        assert proc._deve_transformar_em_ilha(pedra_alta) is True
        pedra_baixa = Pedra(saliencia=Saliencia(valor=0.7))
        assert proc._deve_transformar_em_ilha(pedra_baixa) is False

    def test_ciclo_completo_com_transformacao(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        interacoes = [
            {
                "tipo": "MENSAGEM",
                "conteudo": "descoberta revolucionaria sobre IA",
                "frequencia": 1.0, "intensidade": 1.0,
                "novidade": 1.0, "relevancia": 1.0,
            }
        ]
        relatorio = ir_dormir(store, "sess-1", interacoes)
        assert relatorio["sucesso"]
        assert relatorio["pedras_criadas"] == 1

    def test_ciclo_completo_varias_interacoes(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        interacoes = [
            {"tipo": "MENSAGEM", "conteudo": f"interacao {i}",
             "frequencia": 0.8, "intensidade": 0.7,
             "novidade": 0.6, "relevancia": 0.5}
            for i in range(5)
        ]
        relatorio = ir_dormir(store, "sess-2", interacoes)
        assert relatorio["sucesso"]
        assert relatorio["pedras_criadas"] >= 0

    def test_actualizar_ilhas_existentes_aplica_decay(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha(score_ativacao=0.5, estado=EstadoIlha.ATIVA)
        store.criar(ilha)
        proc = ProcessadorBatch(store)
        actualizadas = proc._actualizar_ilhas_existentes()
        reloaded = store.obter(ilha.id)
        assert reloaded is not None
        assert reloaded.score_ativacao < 0.5
        assert actualizadas >= 0
