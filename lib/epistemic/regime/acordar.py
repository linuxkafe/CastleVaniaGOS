"""ACORDAR / VAI_DORMIR -- regime entry and exit rituals (FR-4).

Ported from v3.0 with the broken paths removed: the source's
vai_dormir_async referenced an undefined logger, imported a nonexistent
batch module, and collected interactions from a TODO stub returning [] --
the "vai_dormir() doesn't sleep" finding from its own hostile analysis.

Here VAI_DORMIR does what especificacao_vai_dormir.md requires at the
regime level: ilha_sleep (memory-layer batch consolidation) -> consolidate
(cycle statistics -> CONSOLIDATION ledger entry) -> record the regime event
-> hibernate. The ILHA processing plugs into vai_dormir via the optional
armazenamento parameter.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from lib.epistemic.regime.ledger import Ledger, LedgerEntryType
from lib.epistemic.regime.state import CycleState, StateMachine

if TYPE_CHECKING:
    from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas


@dataclass
class AcordarResult:
    success: bool
    message: str
    temporal_anchor: Optional[str] = None
    intention_declared: Optional[str] = None


class Acordar:
    """Wake-up ritual: regime is active only after temporal anchor AND intention."""

    def __init__(
        self,
        state_machine: StateMachine,
        ledger: Optional[Ledger] = None,
        armazenamento: Optional["ArmazenamentoIlhas"] = None,
    ):
        self.state_machine = state_machine
        self.ledger = ledger
        self.armazenamento = armazenamento

    def execute(
        self, temporal_anchor: str, intention: str, mode: str = "exploratory"
    ) -> AcordarResult:
        """Run ACORDAR: anchor + intention -> ACTIVE -> GOVERNING."""
        cycle = self.state_machine.current_cycle
        if cycle is None:
            return AcordarResult(
                success=False, message="No active cycle. Load the regime first."
            )

        if not temporal_anchor or not temporal_anchor.strip():
            return AcordarResult(success=False, message="Temporal anchor is required")
        if not intention or not intention.strip():
            return AcordarResult(
                success=False, message="Intention declaration is required"
            )

        self.state_machine.set_temporal_anchor(temporal_anchor)
        self.state_machine.set_intention(intention)
        self.state_machine.set_exploratory(mode == "exploratory")

        if not self.state_machine.activate():
            return AcordarResult(
                success=False,
                message=f"Cannot transition from {cycle.state.value} to ACTIVE",
            )
        if not self.state_machine.govern():
            return AcordarResult(
                success=False, message="Failed to transition to GOVERNING"
            )

        if self.ledger:
            self.ledger.add_entry(
                entry_type=LedgerEntryType.REGIME_EVENT,
                content=(
                    f"ACORDAR executed: anchor={temporal_anchor}, "
                    f"intention={intention}, mode={mode}"
                ),
                metadata={
                    "temporal_anchor": temporal_anchor,
                    "intention": intention,
                    "mode": mode,
                },
                cycle_id=cycle.cycle_id,
            )

        return AcordarResult(
            success=True,
            message="ACORDAR completed. Regime is now GOVERNING.",
            temporal_anchor=temporal_anchor,
            intention_declared=intention,
        )

    def consolidate(self) -> dict:
        """Consolidate the cycle into a ledger record before hibernation."""
        cycle = self.state_machine.current_cycle
        summary = {
            "claims_count": cycle.claims_count,
            "nca_pending": cycle.nca_pending,
            "temporal_anchor": cycle.temporal_anchor,
            "intention": cycle.intention,
            "started_at": cycle.started_at.isoformat(),
        }
        if self.ledger:
            self.ledger.add_entry(
                entry_type=LedgerEntryType.CONSOLIDATION,
                content="VAI_DORMIR consolidation: cycle summary",
                metadata=summary,
                cycle_id=cycle.cycle_id,
            )
        return summary

    def vai_dormir(
        self, interacoes: Optional[List[Dict[str, Any]]] = None
    ) -> dict:
        """Kill switch: ilha_sleep -> consolidate -> hibernate (CRITICO-001).

        Args:
            interacoes: Session interactions to process into ILHA memory.
                        Only used if armazenamento was provided at init.
        """
        cycle = self.state_machine.current_cycle
        if cycle is None:
            return {"success": False, "message": "No active cycle"}
        if cycle.state != CycleState.GOVERNING:
            return {
                "success": False,
                "message": f"Cannot hibernate from {cycle.state.value}; "
                "VAI_DORMIR requires GOVERNING",
            }

        # Memory-layer batch sleep (ILHA/PEDRA processing)
        ilha_report = None
        if self.armazenamento and interacoes:
            from lib.epistemic.memory.dormir import ir_dormir
            ilha_report = ir_dormir(self.armazenamento, cycle.cycle_id, interacoes)
            if self.ledger and ilha_report:
                self.ledger.add_entry(
                    entry_type=LedgerEntryType.ILHA_SLEEP,
                    content="ILHA batch sleep: pedra/ilha consolidation",
                    metadata=ilha_report,
                    cycle_id=cycle.cycle_id,
                )

        summary = self.consolidate()
        if ilha_report:
            summary["ilha"] = ilha_report

        if not self.state_machine.hibernate():
            return {"success": False, "message": "Hibernation transition refused"}

        if self.ledger:
            self.ledger.add_entry(
                entry_type=LedgerEntryType.REGIME_EVENT,
                content="VAI_DORMIR: regime hibernated",
                metadata={"consolidation": summary},
                cycle_id=cycle.cycle_id,
            )

        return {
            "success": True,
            "message": "Regime hibernated. Use resume() to continue.",
            "cycle_id": cycle.cycle_id,
            "consolidation": summary,
        }

    def resume(self, tarefa: Optional[str] = None) -> dict:
        """Resume from hibernation back to GOVERNING.

        Args:
            tarefa: Optional task description to build a re-entry bundle.
        """
        if not self.state_machine.resume():
            return {"success": False, "message": "Cannot resume from current state"}

        cycle = self.state_machine.current_cycle
        if self.ledger:
            self.ledger.add_entry(
                entry_type=LedgerEntryType.REGIME_EVENT,
                content="ACORDAR (resume): regime resumed",
                metadata={"tarefa": tarefa} if tarefa else None,
                cycle_id=cycle.cycle_id,
            )

        result: Dict[str, Any] = {
            "success": True,
            "message": "Regime resumed and GOVERNING.",
        }

        if tarefa and self.armazenamento:
            from lib.epistemic.memory.bundle import construir_bundle
            result["bundle"] = construir_bundle(tarefa, self.armazenamento)

        if self.armazenamento:
            result["active_islands"] = self.get_active_islands()

        return result

    def get_active_islands(self, threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Get active ILHAs for re-entry context (used during ACORDAR).

        Args:
            threshold: Minimum score_ativacao to consider active.

        Returns:
            List of active island summaries, or empty list if no storage.
        """
        if not self.armazenamento:
            return []
        ilhas = self.armazenamento.listar_ativas(threshold=threshold)
        return [
            {
                "id": i.id,
                "nome": i.nome,
                "score": i.score_ativacao,
                "estado": i.estado.value,
                "membros": len(i.membros),
                "lacunas": i.lacunas_identificadas,
            }
            for i in ilhas
        ]

    def get_status(self) -> dict:
        cycle = self.state_machine.current_cycle
        status = {
            "temporal_anchor_declared": bool(cycle and cycle.temporal_anchor),
            "temporal_anchor": cycle.temporal_anchor if cycle else None,
            "intention_declared": bool(cycle and cycle.intention),
            "intention": cycle.intention if cycle else None,
            "is_exploratory": cycle.is_exploratory if cycle else None,
        }
        if self.armazenamento:
            status["active_islands"] = len(self.get_active_islands())
        return status
