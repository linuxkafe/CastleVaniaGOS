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

class TestCalculadorSimilaridade:
    def test_mesma_ilha(self):
        calc = CalculadorSimilaridade()
        ilha = Ilha(nome="test", descricao="same content")
        score = calc.calcular(ilha, ilha)
        assert score > 0
        assert score == pytest.approx(0.4)

    def test_ilhas_diferentes_sem_overlap(self):
        calc = CalculadorSimilaridade()
        i1 = Ilha(nome="foo", descricao="bar baz")
        i2 = Ilha(nome="qux", descricao="quux corge")
        assert calc.calcular(i1, i2) == 0.0

    def test_ilhas_similares(self):
        calc = CalculadorSimilaridade()
        i1 = Ilha(nome="machine learning", descricao="deep neural networks")
        i1.lacunas_identificadas = ["falta dados"]
        i2 = Ilha(nome="deep learning", descricao="neural networks training")
        i2.lacunas_identificadas = ["falta dados"]
        score = calc.calcular(i1, i2)
        assert score > 0

    def test_membros_compartilhados(self):
        calc = CalculadorSimilaridade()
        i1 = Ilha()
        i2 = Ilha()
        m = MembroIlha(member_id="m1", tipo="claim", saliencia=0.5)
        i1.adicionar_membro(m)
        i2.adicionar_membro(m)
        score = calc.calcular(i1, i2)
        assert score > 0


class TestGestorRelacoes:
    def test_criar_relacao(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorRelacoes(store, GestorIlhas(store))
        i1 = Ilha(id="ILHA-001", nome="A")
        i2 = Ilha(id="ILHA-002", nome="B")
        store.criar(i1)
        store.criar(i2)
        assert gestor.criar_relacao("ILHA-001", "ILHA-002", TipoRelacao.RELATED_TO) is True
        reloaded = store.obter("ILHA-001")
        assert reloaded is not None
        assert reloaded.tem_relacao("ILHA-002")

    def test_criar_relacao_duplicada(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorRelacoes(store, GestorIlhas(store))
        i1 = Ilha(id="ILHA-001", nome="A")
        i2 = Ilha(id="ILHA-002", nome="B")
        store.criar(i1)
        store.criar(i2)
        assert gestor.criar_relacao("ILHA-001", "ILHA-002", TipoRelacao.RELATED_TO) is True
        assert gestor.criar_relacao("ILHA-001", "ILHA-002", TipoRelacao.COMPLEMENTA) is True
        reloaded = store.obter("ILHA-001")
        assert reloaded is not None
        assert len(reloaded.relacoes) == 1

    def test_encontrar_similares(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorRelacoes(store, GestorIlhas(store))
        i1 = Ilha(id="ILHA-001", nome="machine learning", descricao="neural networks")
        i2 = Ilha(id="ILHA-002", nome="deep learning", descricao="neural training")
        i3 = Ilha(id="ILHA-003", nome="cooking", descricao="food recipes")
        for i in [i1, i2, i3]:
            store.criar(i)
        similares = gestor.encontrar_similares("ILHA-001", limit=5, threshold=0.0)
        ids = {s["ilha_id"] for s in similares}
        assert "ILHA-002" in ids
        assert "ILHA-003" in ids

    def test_remover_relacao(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorRelacoes(store, GestorIlhas(store))
        i1 = Ilha(id="ILHA-001", nome="A")
        i2 = Ilha(id="ILHA-002", nome="B")
        store.criar(i1)
        store.criar(i2)
        gestor.criar_relacao("ILHA-001", "ILHA-002", TipoRelacao.RELATED_TO)
        assert gestor.remover_relacao("ILHA-001", "ILHA-002") is True
        assert len(i1.relacoes) == 0

    def test_sugerir_agregacao(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        gestor = GestorRelacoes(store, GestorIlhas(store))
        i1 = Ilha(id="ILHA-001", nome="machine learning", descricao="neural networks")
        i2 = Ilha(id="ILHA-002", nome="deep learning", descricao="neural networks")
        store.criar(i1)
        store.criar(i2)
        sugestoes = gestor.sugerir_agregacao(threshold_similaridade=0.0)
        assert len(sugestoes) >= 1
