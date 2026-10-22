"""Tests for shadow doc → ILHA interaction conversion."""

from pathlib import Path

import pytest

from lib.epistemic.memory.shadow_loader import (
    _compute_salience,
    _extract_conteudo,
    _parse_frontmatter,
    carregar_shadow_docs,
    shadow_doc_to_interacao,
)
from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas


SAMPLE_SUPORTADA = """---
type: ShadowDoc
id: SD-TEST-001
title: "Test Shadow Doc"
synthesis: "A test shadow doc for unit testing"
epistemic_state: SUPORTADA
tags:
  - meta
  - test
score:
  activation: 0.8
  pinned: true
  centrality: 3.0
---
# Test

This is the body of a test shadow doc.
It has multiple lines of content.
"""

SAMPLE_NAO_VERIFICAVEL = """---
type: ShadowDoc
id: SD-TEST-002
title: "Unverified Insight"
synthesis: "Something we cannot verify"
epistemic_state: NÃO-VERIFICÁVEL
tags:
  - hostile
  - insight
score:
  activation: 0.3
  pinned: false
  centrality: 2.0
---
# Unverified

This insight cannot be verified yet.
"""

SAMPLE_SEM_FRONTMATTER = """# Just a doc

No frontmatter here.
"""

SAMPLE_FALSIFICADO = """---
type: ShadowDoc
id: SD-TEST-003
title: "Falsified Claim"
synthesis: "This was wrong"
epistemic_state: FALSIFICADO
tags:
  - finding
score:
  activation: 0.1
  pinned: false
  centrality: 1.0
---
# Falsified

This claim was falsified by evidence.
"""


class TestParseFrontmatter:
    def test_extrai_frontmatter(self):
        meta, body = _parse_frontmatter(SAMPLE_SUPORTADA)
        assert meta["id"] == "SD-TEST-001"
        assert meta["epistemic_state"] == "SUPORTADA"
        assert "Test" in body

    def test_sem_frontmatter_retorna_vazio(self):
        meta, body = _parse_frontmatter(SAMPLE_SEM_FRONTMATTER)
        assert meta == {}
        assert "Just a doc" in body

    def test_string_vazia(self):
        meta, body = _parse_frontmatter("")
        assert meta == {}

    def test_frontmatter_malformed_nao_quebra(self):
        meta, body = _parse_frontmatter("---\n: invalid yaml\n---\nbody")
        assert meta == {}


class TestComputeSalience:
    def test_suportada_pinned_alta_saliencia(self):
        sal = _compute_salience({"epistemic_state": "SUPORTADA", "score": {"centrality": 3.0, "activation": 0.8, "pinned": True}, "tags": ["meta"]}, "body")
        assert sal["frequencia"] == 0.9
        assert sal["intensidade"] == 1.0
        assert sal["relevancia"] > 0.5

    def test_falsificado_baixa_intensidade(self):
        sal = _compute_salience({"epistemic_state": "FALSIFICADO", "score": {"centrality": 1.0, "activation": 0.1, "pinned": False}, "tags": ["finding"]}, "body")
        assert sal["intensidade"] == 0.2
        assert sal["frequencia"] == 0.5

    def test_hostile_insight_alta_novidade(self):
        sal = _compute_salience({"epistemic_state": "NÃO-VERIFICÁVEL", "score": {"centrality": 2.0, "activation": 0.3, "pinned": False}, "tags": ["hostile", "insight"]}, "body")
        assert sal["novidade"] == 0.9

    def test_finding_novidade_media_alta(self):
        sal = _compute_salience({"epistemic_state": "SUPORTADA", "score": {"centrality": 2.0, "activation": 0.5, "pinned": False}, "tags": ["finding"]}, "body")
        assert sal["novidade"] == 0.8

    def test_reaccoes_proporcional_ao_tamanho(self):
        sal_curto = _compute_salience({"epistemic_state": "SUPORTADA", "score": {"centrality": 1.0, "activation": 0.5, "pinned": False}, "tags": []}, "short")
        sal_longo = _compute_salience({"epistemic_state": "SUPORTADA", "score": {"centrality": 1.0, "activation": 0.5, "pinned": False}, "tags": []}, " ".join(["word"] * 500))
        assert sal_curto["reaccoes"] < sal_longo["reaccoes"]

    def test_default_state_meio_termo(self):
        sal = _compute_salience({"epistemic_state": "UNKNOWN_STATE", "score": {"centrality": 1.0, "activation": 0.5, "pinned": False}, "tags": []}, "body")
        assert sal["intensidade"] == 0.5


class TestShadowDocToInteracao:
    def test_converte_suportada(self, tmp_path):
        p = tmp_path / "SD-TEST-001.md"
        p.write_text(SAMPLE_SUPORTADA)
        interacao = shadow_doc_to_interacao(p)
        assert interacao is not None
        assert interacao["tipo"] == "SHADOW_DOC"
        assert interacao["sd_id"] == "SD-TEST-001"
        assert interacao["epistemic_state"] == "SUPORTADA"
        assert interacao["frequencia"] == 0.9
        assert interacao["reaccoes"] >= 1

    def test_converte_falsificado(self, tmp_path):
        p = tmp_path / "SD-TEST-003.md"
        p.write_text(SAMPLE_FALSIFICADO)
        interacao = shadow_doc_to_interacao(p)
        assert interacao is not None
        assert interacao["intensidade"] == 0.2

    def test_sem_frontmatter_usa_defaults(self, tmp_path):
        p = tmp_path / "SD-NOFRONT.md"
        p.write_text(SAMPLE_SEM_FRONTMATTER)
        interacao = shadow_doc_to_interacao(p)
        assert interacao is not None
        assert interacao["intensidade"] == 0.5

    def test_conteudo_inclui_title_synthesis_body(self, tmp_path):
        p = tmp_path / "SD-TEST-001.md"
        p.write_text(SAMPLE_SUPORTADA)
        interacao = shadow_doc_to_interacao(p)
        assert "Test Shadow Doc" in interacao["conteudo"]
        assert "test shadow doc" in interacao["conteudo"]


class TestCarregarShadowDocs:
    def test_carrega_multiplos_docs(self, tmp_path):
        (tmp_path / "SD-001.md").write_text(SAMPLE_SUPORTADA)
        (tmp_path / "SD-002.md").write_text(SAMPLE_NAO_VERIFICAVEL)
        docs = carregar_shadow_docs(tmp_path)
        assert len(docs) == 2

    def test_ignora_readme(self, tmp_path):
        (tmp_path / "README.md").write_text("readme")
        (tmp_path / "SD-001.md").write_text(SAMPLE_SUPORTADA)
        docs = carregar_shadow_docs(tmp_path)
        assert len(docs) == 1

    def test_vazio_se_sem_sd(self, tmp_path):
        (tmp_path / "not-sd.md").write_text("nothing")
        docs = carregar_shadow_docs(tmp_path)
        assert docs == []

    def test_processar_shadow_docs_integra_com_ilha(self, tmp_path):
        (tmp_path / "SD-001.md").write_text(SAMPLE_SUPORTADA)
        memory = ArmazenamentoIlhas(tmp_path / "ilhas")
        from lib.epistemic.memory.shadow_loader import processar_shadow_docs
        report = processar_shadow_docs(tmp_path, memory, "session-001")
        assert report["sucesso"]
        assert report["shadow_docs_carregados"] == 1
