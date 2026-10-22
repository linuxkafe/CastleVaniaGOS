"""Tests for Bundle de Reentrada."""

from pathlib import Path

import pytest

from lib.epistemic.memory.bundle import construir_bundle, encontrar_ilhas_por_keywords
from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas
from lib.epistemic.memory.models import Ilha, MembroIlha


@pytest.fixture
def armazenamento(tmp_path) -> ArmazenamentoIlhas:
    return ArmazenamentoIlhas(tmp_path / "ilhas")


def test_encontrar_ilhas_vazias_quando_sem_ilhas(armazenamento):
    result = encontrar_ilhas_por_keywords("teste", armazenamento)
    assert result == []


def test_encontrar_ilhas_por_keyword(armazenamento):
    ilha = Ilha(nome="Gestao de Memoria", descricao="topicos sobre memoria insular")
    armazenamento.criar(ilha)
    result = encontrar_ilhas_por_keywords("memoria insular", armazenamento)
    assert len(result) == 1
    assert result[0].id == ilha.id


def test_encontrar_ilhas_ignora_palavras_diferentes(armazenamento):
    ilha = Ilha(nome="Arquitectura", descricao="topicos de arquitectura")
    armazenamento.criar(ilha)
    result = encontrar_ilhas_por_keywords("musica", armazenamento)
    assert result == []


def test_bundle_sem_ilhas_retorna_estrutura_vazia(armazenamento):
    bundle = construir_bundle("teste", armazenamento)
    assert bundle["tarefa"] == "teste"
    assert bundle["ilhas_relacionadas"] == []
    assert bundle["claims"] == []


def test_bundle_com_ilha_relacionada(armazenamento):
    ilha = Ilha(nome="Padroes de Design", descricao="topicos de design patterns")
    armazenamento.criar(ilha)
    bundle = construir_bundle("design patterns", armazenamento)
    assert len(bundle["ilhas_relacionadas"]) == 1
    assert bundle["ilhas_relacionadas"][0]["id"] == ilha.id


def test_bundle_inclui_claims_das_ilhas(armazenamento):
    ilha = Ilha(nome="Testes", descricao="topicos de teste")
    membro = MembroIlha(member_id="CLM-001", tipo="claim", saliencia=0.8)
    ilha.adicionar_membro(membro)
    armazenamento.criar(ilha)
    bundle = construir_bundle("teste", armazenamento)
    assert len(bundle["claims"]) == 1
    assert bundle["claims"][0]["id"] == "CLM-001"


def test_bundle_inclui_lacunas(armazenamento):
    ilha = Ilha(nome="Seguranca", descricao="topicos de seguranca")
    ilha.lacunas_identificadas.append("falta criptografia")
    armazenamento.criar(ilha)
    bundle = construir_bundle("seguranca", armazenamento)
    assert "falta criptografia" in bundle["lacunas"]


def test_bundle_fallback_para_ilhas_ativas(armazenamento):
    ilha = Ilha(nome="Outro Topico", descricao="sem relacao com a query")
    ilha.score_ativacao = 0.5
    armazenamento.criar(ilha)
    bundle = construir_bundle("query totalmente diferente", armazenamento)
    assert len(bundle["ilhas_relacionadas"]) == 1
