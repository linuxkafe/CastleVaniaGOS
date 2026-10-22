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

class TestSaliencia:
    def test_calcula_valor_pesos_padrao(self):
        s = Saliencia.calcular(frequencia=1.0, intensidade=1.0, novidade=0.5, relevancia=0.5)
        assert s.valor == pytest.approx(0.8)
        assert s.frequencia == 1.0
        assert s.intensidade == 1.0

    def test_clampa_valor_entre_0_e_1(self):
        s = Saliencia.calcular(frequencia=2.0, intensidade=-1.0, novidade=0.5, relevancia=0.5)
        assert s.valor == pytest.approx(0.5)
        assert s.frequencia == 2.0

    def test_pesos_personalizados(self):
        s = Saliencia.calcular(frequencia=1.0, intensidade=0, novidade=0, relevancia=0, pesos={"frequencia": 1.0, "intensidade": 0, "novidade": 0, "relevancia": 0})
        assert s.valor == pytest.approx(1.0)

    def test_para_dict_redondo(self):
        s = Saliencia.calcular(frequencia=0.5, intensidade=0.5, novidade=0.5, relevancia=0.5)
        d = s.para_dict()
        assert d["valor"] == 0.5

    def test_de_dict(self):
        original = Saliencia.calcular(0.8, 0.6, 0.4, 0.2)
        copia = Saliencia.de_dict(original.para_dict())
        assert copia.valor == original.valor
        assert copia.frequencia == original.frequencia


class TestPedra:
    def test_criacao_com_id_unico(self):
        p1 = Pedra()
        p2 = Pedra()
        assert p1.id != p2.id
        assert p1.id.startswith("PEDRA-")

    def test_reativar_incrementa_reacoes(self):
        p = Pedra(contagem_reacoes=0)
        p.reativar()
        assert p.contagem_reacoes == 1

    def test_transformar_em_ilha_muda_estado(self):
        p = Pedra(saliencia=Saliencia(valor=0.9))
        ilha = p.transformar_em_ilha()
        assert p.estado == EstadoPedra.TRANSFORMADA
        assert p.impacto_criou_ilha
        assert ilha.id.startswith("ILHA-")
        assert p.id in ilha.artefactos_fundadores

    def test_agregar_a_ilha(self):
        p = Pedra()
        p.agregar_a_ilha("ILHA-abc")
        assert p.estado == EstadoPedra.AGREGADA
        assert p.esta_agregada()
        assert not p.esta_transformada()

    def test_serializacao_redonda(self):
        p = Pedra(
            tipo_interacao=TipoInteracao.CLAIM,
            saliencia=Saliencia.calcular(0.8, 0.6, 0.4, 0.2),
            conteudo_original="teste de serializacao",
            contagem_reacoes=3,
        )
        d = p.para_dict()
        p2 = Pedra.de_dict(d)
        assert p2.id == p.id
        assert p2.tipo_interacao == p.tipo_interacao
        assert p2.saliencia.valor == p.saliencia.valor
        assert p2.conteudo_original == p.conteudo_original
        assert p2.contagem_reacoes == 3


class TestIlha:
    def test_criacao_com_id_unico(self):
        i1 = Ilha()
        i2 = Ilha()
        assert i1.id != i2.id
        assert i1.id.startswith("ILHA-")

    def test_criar_de_pedra(self):
        p = Pedra(
            saliencia=Saliencia.calcular(0.9, 0.8, 0.7, 0.6),
            conteudo_original="pedra fundadora",
        )
        ilha = Ilha.criar_de_pedra(p)
        assert p.id in ilha.artefactos_fundadores
        assert ilha.score_ativacao == p.saliencia.valor
        assert "pedra fundadora" in ilha.descricao

    def test_adicionar_membro_unicidade(self):
        ilha = Ilha()
        m1 = MembroIlha(member_id="m1", tipo="claim", saliencia=0.5)
        m2 = MembroIlha(member_id="m1", tipo="claim", saliencia=0.5)
        ilha.adicionar_membro(m1)
        ilha.adicionar_membro(m2)
        assert len(ilha.membros) == 1

    def test_remover_membro(self):
        ilha = Ilha()
        m = MembroIlha(member_id="m1", tipo="claim", saliencia=0.5)
        ilha.adicionar_membro(m)
        assert ilha.remover_membro("m1") is True
        assert len(ilha.membros) == 0
        assert ilha.remover_membro("m1") is False

    def test_ultima_reativacao_sem_historico(self):
        ilha = Ilha()
        assert ilha.ultima_reativacao == ilha.data_criacao

    def test_ultima_reativacao_com_historico(self):
        ilha = Ilha()
        antiga = datetime(2020, 1, 1)
        recente = datetime(2025, 6, 15)
        ilha.historico_reativacoes = [
            HistoricoReativacao(data=antiga),
            HistoricoReativacao(data=recente),
        ]
        assert ilha.ultima_reativacao == recente

    def test_calcular_score_sem_historico(self):
        ilha = Ilha()
        assert ilha.calcular_score() == 0.0

    def test_adicionar_relacao_unicidade(self):
        ilha = Ilha()
        r1 = RelacaoIlha(ilha_id="ILHA-abc", tipo=TipoRelacao.RELATED_TO, forca=0.5)
        r2 = RelacaoIlha(ilha_id="ILHA-abc", tipo=TipoRelacao.COMPLEMENTA, forca=0.8)
        ilha.adicionar_relacao(r1)
        ilha.adicionar_relacao(r2)
        assert len(ilha.relacoes) == 1

    def test_aplicar_decay(self):
        ilha = Ilha(score_ativacao=1.0)
        ilha.aplicar_decay(factor=0.5)
        assert ilha.score_ativacao == 0.5

    def test_e_ativa_e_dorminte(self):
        ilha = Ilha(score_ativacao=0.6)
        assert ilha.e_ativa(threshold=0.5)
        assert not ilha.e_dorminte(threshold=0.1)
        ilha.score_ativacao = 0.05
        assert ilha.e_dorminte(threshold=0.1)

    def test_serializacao_redonda(self):
        ilha = Ilha(
            nome="Test Island",
            descricao="A test island with multiple members",
            score_ativacao=0.75,
            grau_consolidacao=0.5,
            estado=EstadoIlha.ATIVA,
        )
        ilha.adicionar_membro(MembroIlha(member_id="m1", tipo="claim", saliencia=0.8))
        d = ilha.para_dict()
        ilha2 = Ilha.de_dict(d)
        assert ilha2.id == ilha.id
        assert ilha2.nome == ilha.nome
        assert ilha2.score_ativacao == ilha.score_ativacao
        assert len(ilha2.membros) == 1


class TestClaim:
    def test_criacao_com_id_unico(self):
        c1 = Claim()
        c2 = Claim()
        assert c1.id != c2.id
        assert c1.id.startswith("CLM-")

    def test_serializacao_redonda(self):
        c = Claim(
            texto="test claim",
            tipo="fact",
            gmif_level="M1",
            gmif_confidence=0.9,
            session_id="sess-1",
        )
        d = c.para_dict()
        c2 = Claim.de_dict(d)
        assert c2.id == c.id
        assert c2.texto == "test claim"
        assert c2.gmif_level == "M1"
