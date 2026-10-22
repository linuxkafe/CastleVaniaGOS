"""Regime/ILHA integration hooks for the premise propagator.

These functions bridge the propagator into the regime lifecycle:
  - run_propagation_for_regime() — called during GFRegime.acordar()
  - propagate_into_ilha() — called during GFRegime.dormir()
"""

from typing import Any, Dict, Optional

from lib.epistemic.premises.engine import PremisesEngine


def run_propagation_for_regime(
    premises_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute premise propagation at regime wake/acordar.

    Loads the premise graph, checks falsification conditions,
    runs the propagator, and persists any loops. Returns a report.
    """
    engine = PremisesEngine()
    loaded = engine.load_premises()
    if not loaded:
        return {
            "propagation": "skipped",
            "message": "No premise graph found — nothing to propagate",
        }

    result = engine.verify_and_propagate()
    blockers = engine.get_blockers()

    return {
        "propagation": "completed" if result.get("opened_loops", 0) > 0 else "clean",
        "result": result,
        "blockers": blockers,
        "blocker_count": len(blockers),
    }


def propagate_into_ilha(
    armazenamento: Any,
    session_id: str,
    propagation_result: Dict[str, Any],
) -> int:
    """Record propagation events as claims in ILHA memory.

    Each opened loop from the propagator becomes a claim added to
    the relevant island (matched by proposition_id / island content).
    """
    from lib.epistemic.memory.nanopub_bridge import criar_claims

    affected = propagation_result.get("affected", [])
    seeds = propagation_result.get("seeds", {})
    if not affected and not seeds:
        return 0

    interacoes = []
    for pid in affected:
        interacoes.append(
            {
                "tipo": "SHADOW_DOC",
                "conteudo": f"Premise Fallen — proposition {pid} affected by propagation cascade",
                "sd_id": f"PROPAGATION-{pid}",
                "epistemic_state": "INFERIDA",
                "reaccoes": 1,
            }
        )
    for pid, reason in seeds.items():
        if pid not in affected:
            interacoes.append(
                {
                    "tipo": "SHADOW_DOC",
                    "conteudo": f"Premise Seed — proposition {pid} fallen due to {reason}",
                    "sd_id": f"PROPAGATION-SEED-{pid}",
                    "epistemic_state": "FALSIFICADO",
                    "reaccoes": 2,
                }
            )

    if not interacoes:
        return 0

    ilhas = armazenamento.listar(limit=100) if hasattr(armazenamento, "listar") else []
    if not ilhas:
        # No existing islands — propagation events are just logged
        return 0

    count = criar_claims(interacoes, armazenamento, session_id)
    return count
