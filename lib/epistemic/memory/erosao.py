"""Erosion dynamics for the ILHA/PEDRA memory system.

Ported from Grilo Falante v3 (app/ilhas/erosao.py).
"""

import math
from typing import Dict, List, Any, Optional

from lib.epistemic.memory.estados import EstadoIlha
from lib.epistemic.memory.models import Ilha


class DinamicaErosao:
    THRESHOLD_EROSAO = 0.1
    THRESHOLD_HIBERNACAO = 0.01
    THRESHOLD_CONSOLIDACAO = 0.8
    DECAY_FACTOR_DIARIO = 0.95

    def __init__(self, ilhas: Optional[Dict[str, Ilha]] = None):
        self._ilhas: Dict[str, Ilha] = ilhas or {}

    def aplicar_decay_todas(self, dias: int = 1) -> Dict[str, int]:
        estados: Dict[str, int] = {
            "actualizadas": 0,
            "para_erosao": 0,
            "para_hibernacao": 0,
            "para_consolidacao": 0,
        }
        for ilha in self._ilhas.values():
            alterado = self._aplicar_decay_ilha(ilha, dias)
            if alterado:
                estados["actualizadas"] += 1
        return estados

    def _aplicar_decay_ilha(self, ilha: Ilha, dias: int) -> bool:
        estado_antes = ilha.estado
        score_antes = ilha.score_ativacao
        factor = self.DECAY_FACTOR_DIARIO ** dias
        ilha.score_ativacao *= factor
        self._actualizar_estado(ilha)
        return (
            ilha.estado != estado_antes
            or abs(ilha.score_ativacao - score_antes) > 0.001
        )

    def _actualizar_estado(self, ilha: Ilha) -> None:
        score = ilha.score_ativacao
        if score >= self.THRESHOLD_CONSOLIDACAO and len(ilha.membros) >= 10:
            ilha.estado = EstadoIlha.CONSOLIDADA
        elif score < self.THRESHOLD_HIBERNACAO:
            ilha.estado = EstadoIlha.DORMINTE
        elif score < self.THRESHOLD_EROSAO:
            if ilha.estado != EstadoIlha.DORMINTE:
                ilha.estado = EstadoIlha.ERODENDO
        elif score >= self.THRESHOLD_EROSAO:
            if ilha.estado in (EstadoIlha.ERODENDO, EstadoIlha.DORMINTE):
                ilha.estado = EstadoIlha.ATIVA

    def reativar_ilha(self, ilha_id: str, boost: float = 0.2) -> Optional[Ilha]:
        ilha = self._ilhas.get(ilha_id)
        if not ilha:
            return None
        ilha.score_ativacao = min(1.0, ilha.score_ativacao + boost)
        if ilha.estado in (EstadoIlha.ERODENDO, EstadoIlha.DORMINTE):
            ilha.estado = EstadoIlha.ATIVA
        return ilha

    def calcular_tempo_para_decay(self, ilha: Ilha, target_score: float = 0.1) -> Optional[int]:
        if ilha.score_ativacao <= target_score:
            return 0
        if self.DECAY_FACTOR_DIARIO >= 1.0:
            return None
        ratio = target_score / ilha.score_ativacao
        if ratio <= 0:
            return None
        dias = math.log(ratio) / math.log(self.DECAY_FACTOR_DIARIO)
        return int(math.ceil(dias))

    def get_estatisticas_decay(self) -> Dict[str, Any]:
        por_estado = {e: 0 for e in EstadoIlha}
        scores = []
        membros_total = 0
        for ilha in self._ilhas.values():
            por_estado[ilha.estado] += 1
            scores.append(ilha.score_ativacao)
            membros_total += len(ilha.membros)
        return {
            "total_ilhas": len(self._ilhas),
            "por_estado": {k.value: v for k, v in por_estado.items()},
            "score_medio": sum(scores) / len(scores) if scores else 0,
            "score_max": max(scores) if scores else 0,
            "score_min": min(scores) if scores else 0,
            "membros_total": membros_total,
            "decay_factor_diario": self.DECAY_FACTOR_DIARIO,
        }

    def registar_ilha(self, ilha: Ilha) -> None:
        self._ilhas[ilha.id] = ilha

    def listar_ilhas(self) -> List[Ilha]:
        return list(self._ilhas.values())


class GestorReativacoes:
    BOOST_REATIVACAO = 0.15
    BOOST_CONSULTA = 0.05
    BOOST_EDICAO = 0.10

    def __init__(self, erosao: DinamicaErosao):
        self.erosao = erosao

    def registar_reativacao(
        self,
        ilha_id: str,
        tipo: str = "reativacao",
        session_id: str = "",
    ) -> Optional[Ilha]:
        ilha = self.erosao.reativar_ilha(ilha_id, boost=self._get_boost_por_tipo(tipo))
        if ilha:
            ilha.adicionar_reativacao(tipo=tipo, session_id=session_id)
            if ilha.estado in (EstadoIlha.DORMINTE, EstadoIlha.ERODENDO):
                ilha.estado = EstadoIlha.ATIVA
        return ilha

    def _get_boost_por_tipo(self, tipo: str) -> float:
        boosts = {
            "reativacao": self.BOOST_REATIVACAO,
            "consulta": self.BOOST_CONSULTA,
            "edicao": self.BOOST_EDICAO,
        }
        return boosts.get(tipo, self.BOOST_REATIVACAO)
