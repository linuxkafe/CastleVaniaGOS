"""Bundle de Reentrada — session re-entry context for ACORDAR.

Ported from Grilo Falante v3 (app/regime/acordar.py).

Given a task query and the ILHA store, builds a context bundle:
related islands, claims, gaps, conflicts — so the resumed session
knows what was happening.
"""

from typing import Any, Dict, List, Optional

from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas
from lib.epistemic.memory.models import Ilha


def encontrar_ilhas_por_keywords(
    query: str,
    armazenamento: ArmazenamentoIlhas,
    limit: int = 5,
    threshold: float = 0.5,
) -> List[Ilha]:
    palavras_query = set(query.lower().split())
    if not palavras_query:
        return []

    ilhas = armazenamento.listar(limit=100)
    pontuadas = []
    for ilha in ilhas:
        texto_ilha = f"{ilha.nome or ''} {ilha.descricao or ''}".lower()
        palavras_ilha = set(texto_ilha.split())
        if not palavras_ilha:
            continue
        matched = len(palavras_query & palavras_ilha)
        score = matched / len(palavras_query)
        if score >= threshold:
            pontuadas.append((ilha, score))

    pontuadas.sort(key=lambda x: x[1], reverse=True)
    return [p[0] for p in pontuadas[:limit]]


def construir_bundle(
    tarefa: str,
    armazenamento: ArmazenamentoIlhas,
) -> Dict[str, Any]:
    ilhas_relacionadas = encontrar_ilhas_por_keywords(tarefa, armazenamento)

    if not ilhas_relacionadas:
        ilhas_relacionadas = [
            i for i in armazenamento.listar(limit=100)
            if i.score_ativacao > 0.3
        ][:5]

    claims = []
    lacunas = []
    conflitos = []

    for ilha in ilhas_relacionadas:
        for membro in ilha.membros:
            if membro.tipo == "claim":
                claims.append({
                    "id": membro.member_id,
                    "saliencia": membro.saliencia,
                    "ilha": ilha.nome,
                })
        lacunas.extend(ilha.lacunas_identificadas)

    lacunas = list(set(lacunas))
    conflitos = list(set(conflitos))

    return {
        "tarefa": tarefa,
        "ilhas_relacionadas": [
            {
                "id": i.id,
                "nome": i.nome,
                "descricao": i.descricao,
                "score": i.score_ativacao,
                "estado": i.estado.value,
                "membros_count": len(i.membros),
            }
            for i in ilhas_relacionadas
        ],
        "claims": claims[:10],
        "lacunas": lacunas[:5],
        "conflitos": conflitos,
        "ilhas_count": len(ilhas_relacionadas),
        "claims_count": len(claims[:10]),
        "lacunas_count": len(lacunas[:5]),
    }
