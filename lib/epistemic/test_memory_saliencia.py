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

class TestCalculadorSaliencia:
    def test_calcula_com_pesos_padrao(self):
        calc = CalculadorSaliencia()
        s = calc.calcular(frequencia=1.0, intensidade=1.0, novidade=0.0, relevancia=0.0)
        assert s.valor == pytest.approx(0.6)

    def test_calcula_normaliza_pesos(self):
        calc = CalculadorSaliencia(pesos={"frequencia": 2, "intensidade": 0, "novidade": 0, "relevancia": 0})
        s = calc.calcular(frequencia=1.0, intensidade=1.0, novidade=0, relevancia=0)
        assert s.valor == pytest.approx(1.0)

    def test_calcular_de_interacao(self):
        calc = CalculadorSaliencia()
        s = calc.calcular_de_interacao({"frequencia": 0.8, "intensidade": 0.6, "novidade": 0.4, "relevancia": 0.2})
        assert s.valor == pytest.approx(0.54)


class TestCalculadorFrequencia:
    def test_sem_interacoes_retorna_default(self):
        assert CalculadorFrequencia.calcular([], "test") == 0.5

    def test_conteudo_presente_aumenta_frequencia(self):
        interacoes = [{"conteudo": "hello world"}] * 10
        freq = CalculadorFrequencia.calcular(interacoes, "hello", janela=10)
        assert freq == 1.0

    def test_conteudo_ausente_retorna_baixo(self):
        interacoes = [{"conteudo": "foo bar"}] * 10
        freq = CalculadorFrequencia.calcular(interacoes, "hello", janela=10)
        assert freq == 0.0


class TestCalculadorIntensidade:
    def test_sem_interacoes_retorna_default(self):
        assert CalculadorIntensidade.calcular([], "test") == 0.3

    def test_intensidade_declarada_usada(self):
        interacoes = [{"conteudo": "test", "intensidade": 0.9}]
        assert CalculadorIntensidade.calcular(interacoes, "test") == 0.9

    def test_reaccoes_aumentam_intensidade(self):
        interacoes = [{"conteudo": "test", "reaccoes": 5}]
        val = CalculadorIntensidade.calcular(interacoes, "test")
        assert val > 0.3


class TestCalculadorNovidade:
    def test_sem_conteudo_retorno_medio(self):
        calc = CalculadorNovidade()
        assert calc.calcular(conteudo="") == 0.5

    def test_sem_referencias_alto(self):
        calc = CalculadorNovidade()
        assert calc.calcular(conteudo="algo completamente novo") == 0.7

    def test_conteudo_existente_baixo(self):
        calc = CalculadorNovidade()
        from lib.epistemic.memory.models import Ilha
        ilha = Ilha(nome="hello", descricao="world of testing")
        val = calc.calcular(conteudo="hello world", ilhas_existentes=[ilha])
        assert val == 0.2


class TestCalculadorRelevancia:
    def test_sem_ilhas_retorna_default(self):
        calc = CalculadorRelevancia()
        assert calc.calcular("test", []) == 0.4

    def test_conteudo_relacionado_detectado(self):
        calc = CalculadorRelevancia()
        from lib.epistemic.memory.models import Ilha
        ilha = Ilha(nome="machine learning", descricao="deep neural networks")
        val = calc.calcular("machine learning neural", [ilha])
        assert val > 0


class TestCalcularSalienciaCompleta:
    def test_calcula_com_todos_componentes(self):
        ilhas = []
        interacao = {
            "conteudo": "hello world",
            "interacoes_recentes": [{"conteudo": "hello world"}] * 5,
        }
        s = calcular_saliencia_completa(interacao, ilhas)
        assert 0 <= s.valor <= 1
        assert s.frequencia > 0
        assert s.intensidade == 0.3
