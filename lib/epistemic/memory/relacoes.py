"""Relations between islands for the ILHA/PEDRA memory system.

Ported from Grilo Falante v3 (app/ilhas/relacoes.py).
"""

from pathlib import Path
from typing import Dict, List, Optional, Any

from lib.epistemic.memory.estados import TipoRelacao
from lib.epistemic.memory.models import Ilha, RelacaoIlha
from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas, GestorIlhas


class CalculadorSimilaridade:
    PESOS_SIMILARIDADE = {
        "conteudo": 0.4,
        "membros": 0.3,
        "topicos": 0.3,
    }

    def calcular(self, ilha1: Ilha, ilha2: Ilha) -> float:
        scores = []
        sim_conteudo = self._similaridade_conteudo(ilha1, ilha2)
        scores.append(("conteudo", sim_conteudo, self.PESOS_SIMILARIDADE["conteudo"]))
        sim_membros = self._similaridade_membros(ilha1, ilha2)
        scores.append(("membros", sim_membros, self.PESOS_SIMILARIDADE["membros"]))
        sim_topicos = self._similaridade_topicos(ilha1, ilha2)
        scores.append(("topicos", sim_topicos, self.PESOS_SIMILARIDADE["topicos"]))
        total_peso = sum(s[2] for s in scores)
        if total_peso == 0:
            return 0.0
        return sum(s[1] * s[2] for s in scores) / total_peso

    def _similaridade_conteudo(self, ilha1: Ilha, ilha2: Ilha) -> float:
        texto1 = f"{ilha1.nome or ''} {ilha1.descricao or ''}".lower()
        texto2 = f"{ilha2.nome or ''} {ilha2.descricao or ''}".lower()
        if not texto1 or not texto2:
            return 0.0
        palavras1 = set(texto1.split())
        palavras2 = set(texto2.split())
        if not palavras1 or not palavras2:
            return 0.0
        intersecao = len(palavras1 & palavras2)
        uniao = len(palavras1 | palavras2)
        return intersecao / uniao if uniao > 0 else 0.0

    def _similaridade_membros(self, ilha1: Ilha, ilha2: Ilha) -> float:
        membros1 = {m.member_id for m in ilha1.membros}
        membros2 = {m.member_id for m in ilha2.membros}
        if not membros1 or not membros2:
            return 0.0
        intersecao = len(membros1 & membros2)
        uniao = len(membros1 | membros2)
        return intersecao / uniao if uniao > 0 else 0.0

    def _similaridade_topicos(self, ilha1: Ilha, ilha2: Ilha) -> float:
        topicos1 = set(ilha1.lacunas_identificadas)
        topicos2 = set(ilha2.lacunas_identificadas)
        if not topicos1 or not topicos2:
            return 0.0
        intersecao = len(topicos1 & topicos2)
        uniao = len(topicos1 | topicos2)
        return intersecao / uniao if uniao > 0 else 0.0


class GestorRelacoes:
    def __init__(
        self,
        armazenamento: ArmazenamentoIlhas,
        gestor_ilhas: GestorIlhas,
        calculador: Optional[CalculadorSimilaridade] = None,
    ):
        self.armazenamento = armazenamento
        self.gestor_ilhas = gestor_ilhas
        self.calculador = calculador or CalculadorSimilaridade()

    def criar_relacao(
        self,
        ilha1_id: str,
        ilha2_id: str,
        tipo: TipoRelacao,
        forca: float = 0.5,
    ) -> bool:
        ilha1 = self.armazenamento.obter(ilha1_id)
        if not ilha1:
            return False
        if ilha1.tem_relacao(ilha2_id):
            return True
        relacao = RelacaoIlha(ilha_id=ilha2_id, tipo=tipo, forca=forca)
        ilha1.adicionar_relacao(relacao)
        self.armazenamento.atualizar(ilha1)
        return True

    def remover_relacao(self, ilha1_id: str, ilha2_id: str) -> bool:
        ilha1 = self.armazenamento.obter(ilha1_id)
        if not ilha1:
            return False
        ilha1.relacoes = [r for r in ilha1.relacoes if r.ilha_id != ilha2_id]
        self.armazenamento.atualizar(ilha1)
        return True

    def encontrar_similares(
        self,
        ilha_id: str,
        limit: int = 5,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        ilha = self.armazenamento.obter(ilha_id)
        if not ilha:
            return []
        todas = self.armazenamento.listar(limit=100)
        similares = []
        for outra in todas:
            if outra.id == ilha_id:
                continue
            score = self.calculador.calcular(ilha, outra)
            if score >= threshold:
                similares.append({
                    "ilha_id": outra.id,
                    "nome": outra.nome,
                    "score": score,
                    "estado": outra.estado.value,
                })
        similares.sort(key=lambda x: x["score"], reverse=True)
        return similares[:limit]

    def sugerir_agregacao(self, threshold_similaridade: float = 0.3) -> List[Dict[str, Any]]:
        ilhas = self.armazenamento.listar(limit=100)
        sugeridos = []
        for i, ilha1 in enumerate(ilhas):
            for ilha2 in ilhas[i + 1:]:
                score = self.calculador.calcular(ilha1, ilha2)
                if score >= threshold_similaridade:
                    sugeridos.append({
                        "ilha1_id": ilha1.id,
                        "ilha1_nome": ilha1.nome,
                        "ilha2_id": ilha2.id,
                        "ilha2_nome": ilha2.nome,
                        "similaridade": score,
                    })
        sugeridos.sort(key=lambda x: x["similaridade"], reverse=True)
        return sugeridos

    def obter_relacoes_ilha(self, ilha_id: str) -> List[Dict[str, Any]]:
        ilha = self.armazenamento.obter(ilha_id)
        if not ilha:
            return []
        relacoes = []
        for relacao in ilha.relacoes:
            ilha_relacionada = self.armazenamento.obter(relacao.ilha_id)
            relacoes.append({
                "ilha_id": relacao.ilha_id,
                "nome": ilha_relacionada.nome if ilha_relacionada else "Desconhecida",
                "tipo": relacao.tipo.value,
                "forca": relacao.forca,
            })
        return relacoes


def sugerir_agregacoes_batch(threshold: float = 0.7, armazenamento: Optional[ArmazenamentoIlhas] = None) -> List[Dict[str, Any]]:
    if armazenamento is None:
        import tempfile
        armazenamento = ArmazenamentoIlhas(Path(tempfile.mkdtemp()))
    gestor = GestorRelacoes(armazenamento, GestorIlhas(armazenamento))
    return gestor.sugerir_agregacao(threshold)
