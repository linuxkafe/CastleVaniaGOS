"""Bridge: shadow doc interactions → Claim objects → MembroIlha in islands.

Each shadow doc processed through the sleep cycle creates a Pedra that may
become an island or be aggregated. This bridge adds explicit Claim objects
as members (tipo="claim") to the matching island, so that:

1. Claims carry epistemic_state provenance (SUPORTADA, FALSIFICADO, etc.)
2. Islands have machine-readable claims instead of opaque SHADOW_DOC members
3. Future reasoning (contradiction, gap analysis) can operate over claims

Usage:
    from lib.epistemic.memory.nanopub_bridge import criar_claims
    claims_added = criar_claims(interacoes, armazenamento, session_id)
"""

from typing import Any, Dict, List

from lib.epistemic.memory.estados import EstadoClaim
from lib.epistemic.memory.models import Claim, MembroIlha
from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas

_EPISTEMIC_TO_GMIF = {
    "SUPORTADA": ("M2", 0.8),
    "VERIFICADA": ("M1", 0.9),
    "VERIFICADO": ("M1", 0.9),
    "NAO-VERIFICAVEL": ("M5", 0.3),
    "NÃO-VERIFICÁVEL": ("M5", 0.3),
    "FALSIFICADO": ("M1", 0.95),
    "FALSIFICADA": ("M1", 0.95),
    "ABERTO": ("M4", 0.4),
    "INFERIDA": ("M5", 0.35),
    "ASSUMED": ("M3", 0.5),
    "DESCONHECIDO": ("M7", 0.2),
}


def _gmif_from_epistemic(epistemic_state: str) -> tuple:
    level, conf = _EPISTEMIC_TO_GMIF.get(epistemic_state, ("M3", 0.5))
    return level, conf


def _match_island(
    interacao: Dict[str, Any],
    ilhas: List,
    threshold: float = 0.25,
) -> Any:
    palavras = set(interacao.get("conteudo", "").lower().split())
    if not palavras:
        return None
    melhor = None
    melhor_score = threshold
    for ilha in ilhas:
        texto = f"{ilha.nome} {ilha.descricao}".lower()
        palavras_ilha = set(texto.split())
        overlap = len(palavras & palavras_ilha)
        uniao = len(palavras | palavras_ilha)
        score = overlap / uniao if uniao > 0 else 0
        if score >= melhor_score:
            melhor_score = score
            melhor = ilha
    return melhor


def criar_claims(
    interacoes: List[Dict[str, Any]],
    armazenamento: ArmazenamentoIlhas,
    session_id: str,
    threshold: float = 0.2,
) -> int:
    ilhas = armazenamento.listar(limit=100)
    if not ilhas:
        return 0

    claims_adicionados = 0
    for interacao in interacoes:
        if interacao.get("tipo") != "SHADOW_DOC":
            continue

        sd_id = interacao.get("sd_id", "")
        if not sd_id:
            continue

        epistemic_state = interacao.get("epistemic_state", "DESCONHECIDO")
        gmif_level, gmif_conf = _gmif_from_epistemic(epistemic_state)

        claim = Claim(
            texto=interacao.get("conteudo", "")[:500],
            gmif_level=gmif_level,
            gmif_confidence=gmif_conf,
            estado=EstadoClaim.ESTRUTURAL,
            session_id=session_id,
            sources=[sd_id],
        )

        ilha = _match_island(interacao, ilhas, threshold)
        if ilha is None:
            continue

        if ilha.tem_membro(sd_id):
            continue

        membro = MembroIlha(
            member_id=sd_id,
            tipo="claim",
            saliencia=0.5,
            inserido_por="nanopub_bridge",
        )
        ilha.adicionar_membro(membro)
        armazenamento.atualizar(ilha)
        claims_adicionados += 1

    return claims_adicionados
