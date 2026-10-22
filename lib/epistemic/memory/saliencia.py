"""Salience calculation for the ILHA/PEDRA memory system.

Ported from Grilo Falante v3 (app/ilhas/salienca.py).
"""

from typing import Dict, List, Optional, Any, Callable

from lib.epistemic.memory.models import Saliencia


class CalculadorSaliencia:
    PESOS_PADRAO = {
        "frequencia": 0.3,
        "intensidade": 0.3,
        "novidade": 0.2,
        "relevancia": 0.2,
    }

    def __init__(self, pesos: Optional[Dict[str, float]] = None):
        self.pesos = pesos or dict(self.PESOS_PADRAO)
        total = sum(self.pesos.values())
        if abs(total - 1.0) > 0.01:
            for k in self.pesos:
                self.pesos[k] /= total

    def calcular(
        self,
        frequencia: float,
        intensidade: float,
        novidade: float,
        relevancia: float,
    ) -> Saliencia:
        valor = (
            self.pesos["frequencia"] * frequencia
            + self.pesos["intensidade"] * intensidade
            + self.pesos["novidade"] * novidade
            + self.pesos["relevancia"] * relevancia
        )
        valor = min(1.0, max(0.0, valor))
        return Saliencia(
            valor=valor,
            frequencia=frequencia,
            intensidade=intensidade,
            novidade=novidade,
            relevancia=relevancia,
        )

    def calcular_de_interacao(self, interacao: Dict[str, Any]) -> Saliencia:
        frequencia = min(1.0, interacao.get("frequencia", 0.5))
        intensidade = min(1.0, interacao.get("intensidade", 0.3))
        novidade = min(1.0, interacao.get("novidade", 0.5))
        relevancia = min(1.0, interacao.get("relevancia", 0.4))
        return self.calcular(frequencia, intensidade, novidade, relevancia)


class CalculadorFrequencia:
    @staticmethod
    def calcular(interacoes: List[Dict[str, Any]], conteudo: str, janela: int = 10) -> float:
        if not interacoes:
            return 0.5
        recentes = interacoes[-janela:]
        count = sum(
            1 for i in recentes
            if conteudo.lower() in i.get("conteudo", "").lower()
        )
        return min(1.0, count / max(1, janela))


class CalculadorIntensidade:
    @staticmethod
    def calcular(interacoes: List[Dict[str, Any]], conteudo: str) -> float:
        for i in interacoes:
            if conteudo.lower() in i.get("conteudo", "").lower():
                if "intensidade" in i:
                    return min(1.0, float(i["intensidade"]))
        sinais_positivos = 0
        sinais_negativos = 0
        for i in interacoes:
            if conteudo.lower() in i.get("conteudo", "").lower():
                if i.get("reaccoes", 0) > 0:
                    sinais_positivos += 1
                if i.get("claims_geradas", 0) > 2:
                    sinais_positivos += 0.5
                if i.get("bloqueado", False):
                    sinais_negativos += 0.5
        total = sinais_positivos + sinais_negativos
        if total == 0:
            return 0.3
        ratio = sinais_positivos / total
        return min(1.0, 0.3 + ratio * 0.7)


class CalculadorNovidade:
    def __init__(self, threshold_similaridade: float = 0.8):
        self.threshold_similaridade = threshold_similaridade

    def calcular(
        self,
        conteudo: str,
        buscas_mempalace: Optional[Callable] = None,
        ilhas_existentes: Optional[List[Any]] = None,
    ) -> float:
        if not conteudo:
            return 0.5
        if not buscas_mempalace and not ilhas_existentes:
            return 0.7
        if buscas_mempalace:
            try:
                similares = buscas_mempalace(conteudo, limit=3)
                if similares:
                    melhor_score = similares[0].get("score", 0) if isinstance(similares, list) else 0
                    if melhor_score > self.threshold_similaridade:
                        return max(0.1, 1.0 - melhor_score)
            except Exception:
                pass
        if ilhas_existentes:
            for ilha in ilhas_existentes:
                desc = getattr(ilha, "descricao", getattr(ilha, "descrição", "")) or ""
                nome = getattr(ilha, "nome", "") or ""
                texto = f"{nome} {desc}".lower()
                if conteudo.lower() in texto:
                    return 0.2
                palavras_conteudo = set(conteudo.lower().split())
                palavras_ilha = set(texto.split())
                overlap = len(palavras_conteudo & palavras_ilha)
                if overlap > 3:
                    return 0.4
        return 0.7


class CalculadorRelevancia:
    def __init__(self, threshold_conexao: float = 0.6):
        self.threshold_conexao = threshold_conexao

    def calcular(
        self,
        conteudo: str,
        ilhas: List[Any],
    ) -> float:
        if not ilhas:
            return 0.4
        conexoes = 0
        total_ilhas = len(ilhas)
        for ilha in ilhas:
            texto_ilha = f"{getattr(ilha, 'nome', '') or ''} {getattr(ilha, 'descricao', getattr(ilha, 'descrição', '')) or ''}".lower()
            palavras_conteudo = set(conteudo.lower().split())
            palavras_ilha = set(texto_ilha.lower().split())
            overlap = len(palavras_conteudo & palavras_ilha)
            if overlap >= 3:
                conexoes += 1
            elif overlap >= 1:
                conexoes += 0.3
            score = getattr(ilha, "score_ativacao", 0)
            if score > 0.7:
                conexoes += 0.2
        if total_ilhas == 0:
            return 0.4
        return min(1.0, conexoes / total_ilhas)


def calcular_saliencia_completa(
    interacao: Dict[str, Any],
    ilhas: List[Any],
    buscas_mempalace: Optional[Callable] = None,
) -> Saliencia:
    freq = CalculadorFrequencia.calcular(
        interacao.get("interacoes_recentes", []),
        interacao.get("conteudo", ""),
    )
    intensidade = CalculadorIntensidade.calcular(
        interacao.get("interacoes_recentes", []),
        interacao.get("conteudo", ""),
    )
    novidade = CalculadorNovidade().calcular(
        conteudo=interacao.get("conteudo", ""),
        buscas_mempalace=buscas_mempalace,
        ilhas_existentes=ilhas,
    )
    relevancia = CalculadorRelevancia().calcular(
        conteudo=interacao.get("conteudo", ""),
        ilhas=ilhas,
    )
    return Saliencia.calcular(
        frequencia=freq,
        intensidade=intensidade,
        novidade=novidade,
        relevancia=relevancia,
    )
