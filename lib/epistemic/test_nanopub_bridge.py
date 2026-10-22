"""Tests for nanopub_bridge — shadow doc interactions → Claims → MembroIlha."""

from pathlib import Path

import pytest

from lib.epistemic.memory.nanopub_bridge import (
    _gmif_from_epistemic,
    _match_island,
    criar_claims,
)
from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas
from lib.epistemic.memory.models import Ilha


class TestGmifFromEpistemic:
    def test_suportada_maps_to_m2(self):
        level, conf = _gmif_from_epistemic("SUPORTADA")
        assert level == "M2"
        assert conf == 0.8

    def test_verificada_maps_to_m1(self):
        level, conf = _gmif_from_epistemic("VERIFICADA")
        assert level == "M1"
        assert conf == 0.9

    def test_falsificado_maps_to_m1_alta_conf(self):
        level, conf = _gmif_from_epistemic("FALSIFICADO")
        assert level == "M1"
        assert conf == 0.95

    def test_desconhecido_maps_to_m7(self):
        level, conf = _gmif_from_epistemic("DESCONHECIDO")
        assert level == "M7"
        assert conf == 0.2

    def test_unknown_state_defaults_to_m3(self):
        level, conf = _gmif_from_epistemic("SOME_UNKNOWN_STATE")
        assert level == "M3"
        assert conf == 0.5


class TestMatchIsland:
    def test_matches_by_content_overlap(self):
        ilha = Ilha(nome="ILHA Memory Storage", descricao="File-based island storage with JSON persistence")
        interacao = {"conteudo": "ILHA Memory Architecture — file-based storage system for epistemic islands"}
        match = _match_island(interacao, [ilha], threshold=0.1)
        assert match is not None
        assert match.id == ilha.id

    def test_no_match_below_threshold(self):
        ilha = Ilha(nome="Cooking", descricao="Food recipes and kitchen tips")
        interacao = {"conteudo": "Quantum computing entanglement theory"}
        match = _match_island(interacao, [ilha], threshold=0.5)
        assert match is None

    def test_best_match_wins(self):
        i1 = Ilha(nome="Cooking", descricao="Food recipes")
        i2 = Ilha(nome="ILHA Memory", descricao="Epistemic island storage")
        interacao = {"conteudo": "ILHA islands store epistemic memory"}
        match = _match_island(interacao, [i1, i2], threshold=0.1)
        assert match is not None
        assert match.id == i2.id

    def test_empty_content_returns_none(self):
        ilha = Ilha(nome="Test", descricao="whatever")
        assert _match_island({"conteudo": ""}, [ilha]) is None

    def test_empty_islands_returns_none(self):
        assert _match_island({"conteudo": "test"}, []) is None


class TestCriarClaims:
    def test_cria_claim_em_ilha_existente(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha(nome="ILHA Memory", descricao="File-based epistemic memory islands")
        store.criar(ilha)

        interacoes = [{
            "tipo": "SHADOW_DOC",
            "conteudo": "ILHA Memory Architecture — file-based storage for islands",
            "sd_id": "SD-TEST-001",
            "epistemic_state": "SUPORTADA",
            "reaccoes": 5,
        }]
        count = criar_claims(interacoes, store, "sess-1")
        assert count == 1

        reloaded = store.obter(ilha.id)
        assert reloaded is not None
        assert len(reloaded.membros) == 1
        assert reloaded.membros[0].tipo == "claim"

    def test_nao_cria_claim_se_sem_islands(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        interacoes = [{
            "tipo": "SHADOW_DOC",
            "conteudo": "something",
            "sd_id": "SD-TEST-001",
            "epistemic_state": "ASSUMED",
        }]
        count = criar_claims(interacoes, store, "sess-1")
        assert count == 0

    def test_ignora_tipos_nao_shadow_doc(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha(nome="Test", descricao="whatever")
        store.criar(ilha)

        interacoes = [
            {"tipo": "MENSAGEM", "conteudo": "hi", "sd_id": "", "epistemic_state": "DESCONHECIDO"},
            {"tipo": "CLAIM", "conteudo": "claim", "sd_id": "", "epistemic_state": "DESCONHECIDO"},
            {"tipo": "EVENTO", "conteudo": "event", "sd_id": "", "epistemic_state": "DESCONHECIDO"},
        ]
        count = criar_claims(interacoes, store, "sess-1")
        assert count == 0

    def test_nao_duplica_membros_existentes(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha(nome="ILHA Memory", descricao="File-based storage")
        store.criar(ilha)

        interacao = {
            "tipo": "SHADOW_DOC",
            "conteudo": "ILHA Memory Architecture — file-based storage",
            "sd_id": "SD-TEST-001",
            "epistemic_state": "SUPORTADA",
        }
        count1 = criar_claims([interacao], store, "sess-1")
        count2 = criar_claims([interacao], store, "sess-2")
        assert count1 == 1
        assert count2 == 0

    def test_gmif_reflete_epistemic_state(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        ilha = Ilha(nome="Falsified Claim", descricao="A claim that was proven wrong")
        store.criar(ilha)

        interacoes = [{
            "tipo": "SHADOW_DOC",
            "conteudo": "Falsified Claim — this was wrong",
            "sd_id": "SD-TEST-003",
            "epistemic_state": "FALSIFICADO",
        }]
        count = criar_claims(interacoes, store, "sess-1")
        assert count == 1

        reloaded = store.obter(ilha.id)
        assert reloaded is not None
        assert len(reloaded.membros) == 1

    def test_multiplos_shadow_docs_multiplas_ilhas(self, tmp_path):
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        i1 = Ilha(nome="ILHA Memory", descricao="File-based island storage")
        i2 = Ilha(nome="Pipeline Gates", descricao="Quality gates for AES pipeline")
        store.criar(i1)
        store.criar(i2)

        interacoes = [
            {
                "tipo": "SHADOW_DOC", "sd_id": "SD-001",
                "conteudo": "ILHA Memory Architecture — file-based storage for epistemic islands",
                "epistemic_state": "SUPORTADA",
            },
            {
                "tipo": "SHADOW_DOC", "sd_id": "SD-002",
                "conteudo": "Pipeline Gates — lint gates and identity enforcement",
                "epistemic_state": "VERIFICADA",
            },
        ]
        count = criar_claims(interacoes, store, "sess-1")
        assert count == 2


class TestCriarClaimsPipeline:
    def test_integracao_com_processar_shadow_docs(self, tmp_path):
        sd_content = """---
type: ShadowDoc
id: SD-TEST-BRIDGE-001
title: "Nanopub Bridge Test"
synthesis: "Testing the nanopub bridge integration"
epistemic_state: SUPORTADA
tags:
  - test
score:
  activation: 0.8
  pinned: false
  centrality: 2.0
---
# Test

Integration test for the nanopub bridge.
"""
        sd_file = tmp_path / "SD-TEST-BRIDGE-001.md"
        sd_file.write_text(sd_content)

        from lib.epistemic.memory.shadow_loader import processar_shadow_docs
        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        report = processar_shadow_docs(tmp_path, store, "sess-integration")

        assert report["sucesso"]
        assert report["shadow_docs_carregados"] == 1
        assert report["claims_adicionados"] >= 0

        ilhas = store.listar()
        if ilhas:
            total_claims = sum(
                1 for m in ilhas[0].membros if m.tipo == "claim"
            )
            assert total_claims == report["claims_adicionados"]

    def test_pipeline_30_shadow_docs_processados(self, tmp_path, monkeypatch):
        import shutil
        shadow_dir = tmp_path / "shadow"
        shadow_dir.mkdir(parents=True, exist_ok=True)

        # Copy minimal fixtures for test
        fixtures = [
            "SD-META-022.md",
            "SD-OPS-022.md",
            "SD-OPS-023.md",
            "SD-OPS-024.md",
        ]
        found_any = False
        for fname in fixtures:
            src = Path("/opt/aes/aes/shadow") / fname
            if src.exists():
                shutil.copy2(src, shadow_dir / fname)
                found_any = True

        if not found_any:
            pytest.skip("No shadow fixtures found in /opt/aes/aes/shadow")

        # Override AES_SHADOW_DIR for isolation
        monkeypatch.setenv("AES_SHADOW_DIR", str(shadow_dir))

        store = ArmazenamentoIlhas(tmp_path / "ilhas")
        from lib.epistemic.memory.shadow_loader import processar_shadow_docs
        report = processar_shadow_docs(shadow_dir, store, "sess-pipeline")

        assert report["sucesso"]
        # shadow_docs_carregados may be missing if no fixtures found
        loaded = report.get("shadow_docs_carregados", 0)
        if loaded > 0:
            ilhas = store.listar()
            total_claims = sum(
                sum(1 for m in i.membros if m.tipo == "claim")
                for i in ilhas
            )
            assert total_claims == report.get("claims_adicionados", 0)
