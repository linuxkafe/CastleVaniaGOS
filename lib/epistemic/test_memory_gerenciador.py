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

class TestArmazenamentoIlhas:
    def test_criar_e_obter(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha(nome="Minha Ilha")
        store.criar(ilha)
        lida = store.obter(ilha.id)
        assert lida is not None
        assert lida.id == ilha.id
        assert lida.nome == "Minha Ilha"

    def test_obter_inexistente(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        assert store.obter("ILHA-nao-existe") is None

    def test_listar(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        i1 = Ilha(nome="A")
        i2 = Ilha(nome="B")
        store.criar(i1)
        store.criar(i2)
        todas = store.listar()
        assert len(todas) == 2

    def test_listar_por_estado(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        store.criar(Ilha(nome="A", estado=EstadoIlha.ATIVA))
        store.criar(Ilha(nome="B", estado=EstadoIlha.DORMINTE))
        ativas = store.listar(estado="ATIVA")
        dormintes = store.listar(estado="DORMINTE")
        assert len(ativas) == 1
        assert len(dormintes) == 1

    def test_listar_ativas(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        store.criar(Ilha(nome="A", score_ativacao=0.8))
        store.criar(Ilha(nome="B", score_ativacao=0.2))
        ativas = store.listar_ativas(threshold=0.5)
        assert len(ativas) == 1

    def test_remover(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha()
        store.criar(ilha)
        assert store.remover(ilha.id) is True
        assert store.obter(ilha.id) is None
        assert store.remover("inexistente") is False


class TestGestorIlhas:
    def test_criar_ilha_de_pedra(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorIlhas(store)
        p = Pedra(saliencia=Saliencia.calcular(0.9, 0.8, 0.7, 0.6))
        ilha = gestor.criar_ilha_de_pedra(p)
        assert ilha.estado == EstadoIlha.EMBRIONARIA
        assert store.obter(ilha.id) is not None

    def test_adicionar_remover_membro(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorIlhas(store)
        ilha = Ilha()
        store.criar(ilha)
        m = MembroIlha(member_id="m1", tipo="claim", saliencia=0.5)
        assert gestor.adicionar_membro(ilha.id, m) is True
        assert gestor.remover_membro(ilha.id, "m1") is True

    def test_combinar_ilhas(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorIlhas(store)
        i1 = Ilha(nome="A")
        i2 = Ilha(nome="B")
        i2.adicionar_membro(MembroIlha(member_id="m1", tipo="claim", saliencia=0.5))
        store.criar(i1)
        store.criar(i2)
        combinada = gestor.combinar_ilhas(i1.id, i2.id)
        assert combinada is not None
        assert combinada.tem_membro("m1")
        assert store.obter(i2.id).estado == EstadoIlha.DORMINTE

    def test_resumo_sistema(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorIlhas(store)
        store.criar(Ilha(nome="A", score_ativacao=0.8))
        store.criar(Ilha(nome="B", score_ativacao=0.05))
        resumo = gestor.get_resumo_sistema()
        assert resumo["total_ilhas"] == 2
        assert resumo["activas"] == 1

    def test_actualizar_estado(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorIlhas(store)
        ilha = Ilha()
        store.criar(ilha)
        assert gestor.actualizar_estado_ilha(ilha.id, EstadoIlha.CONSOLIDADA) is True
        assert store.obter(ilha.id).estado == EstadoIlha.CONSOLIDADA

    def test_adicionar_lacuna(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorIlhas(store)
        ilha = Ilha()
        store.criar(ilha)
        assert gestor.adicionar_lacuna(ilha.id, "falta informacao") is True
        assert "falta informacao" in store.obter(ilha.id).lacunas_identificadas
