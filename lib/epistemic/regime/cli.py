"""CLI entry points for the regime rituals.

Usage (via `python -m lib.epistemic.regime.cli ...`):
    acordar --anchor 2026-06-11 --intention "..."
    vai-dormir | resume | status
    pina-propose --source X --statement Y --location Z
    pina-decide --nca-id N --decision ACCEPT --reason "..."

State persists across invocations in AES_REGIME_STATE (default .aes/regime-state.json);
the ledger in AES_REGIME_LEDGER (default .aes/regime-ledger.jsonl). PINA candidates are
rebuilt from the ledger -- the ledger is the source of truth, the state file
only carries the cycle context.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from lib.epistemic.regime.acordar import Acordar
from lib.epistemic.regime.ledger import Ledger, LedgerEntryType
from lib.epistemic.regime.pina import PINAProtocol
from lib.epistemic.regime.state import CycleContext, CycleState, StateMachine


def _paths() -> tuple[Path, Path, Path]:
    state = Path(os.environ.get("AES_REGIME_STATE", ".aes/regime-state.json"))
    ledger = Path(os.environ.get("AES_REGIME_LEDGER", ".aes/regime-ledger.jsonl"))
    ilhas = Path(os.environ.get("AES_ILHAS_DIR", ".aes/ilhas"))
    state.parent.mkdir(parents=True, exist_ok=True)
    ilhas.mkdir(parents=True, exist_ok=True)
    return state, ledger, ilhas


def _load_machine(state_path: Path) -> StateMachine:
    machine = StateMachine()
    if state_path.exists():
        data = json.loads(state_path.read_text())
        ctx = CycleContext(cycle_id=data["cycle_id"])
        ctx.state = CycleState(data["state"])
        ctx.started_at = datetime.fromisoformat(data["started_at"])
        ctx.claims_count = data.get("claims_count", 0)
        ctx.nca_pending = data.get("nca_pending", 0)
        ctx.is_exploratory = data.get("is_exploratory", True)
        ctx.legitimacy_declared = data.get("legitimacy_declared", False)
        ctx.temporal_anchor = data.get("temporal_anchor")
        ctx.intention = data.get("intention")
        machine.current_cycle = ctx
    return machine


def _save_machine(machine: StateMachine, state_path: Path):
    if machine.current_cycle:
        state_path.write_text(json.dumps(machine.current_cycle.to_dict(), indent=2))


def _rebuild_pina(machine: StateMachine, ledger: Ledger) -> PINAProtocol:
    """Rebuild PINA from the ledger: candidates minus already-decided ones."""
    pina = PINAProtocol(state_machine=machine, ledger=ledger)
    decided = {e.gf_id for e in ledger._by_type(LedgerEntryType.PINA_DECISION)}
    for entry in ledger.get_nca():
        from lib.epistemic.regime.pina import NormativeCandidateRecord

        record = NormativeCandidateRecord(
            nca_id=entry.gf_id,
            source_document=entry.metadata.get("source", ""),
            faithful_statement=entry.content,
            location=entry.metadata.get("location", ""),
            graph_scope=entry.metadata.get("graph_scope"),
            created_at=datetime.fromisoformat(entry.timestamp),
            cycle_id=entry.cycle_id,
        )
        pina._candidates[entry.gf_id] = record
        if entry.gf_id in decided:
            record.decided_at = record.created_at
            for d in ledger._by_type(LedgerEntryType.PINA_DECISION):
                if d.gf_id == entry.gf_id and d.metadata.get("decision") == "A":
                    pina._active_invariants.append(entry.gf_id)
    return pina


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aes-regime", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_acordar = sub.add_parser("acordar", help="Wake-up ritual")
    p_acordar.add_argument("--anchor", required=True)
    p_acordar.add_argument("--intention", required=True)
    p_acordar.add_argument(
        "--mode", default="exploratory", choices=["exploratory", "committed"]
    )

    p_dormir = sub.add_parser("vai-dormir", help="Kill switch: consolidate and hibernate")
    p_dormir.add_argument("--interacao", action="append", help="Interaction dict as JSON (can repeat)")

    p_resume = sub.add_parser("resume", help="Resume from hibernation")
    p_resume.add_argument("--tarefa", help="Task description for re-entry bundle")
    sub.add_parser("status", help="Show regime status")

    mem_list = sub.add_parser("memory-list", help="List memory islands")
    mem_list.add_argument("--active-only", action="store_true")
    mem_list.add_argument("--threshold", type=float, default=0.5)

    mem_show = sub.add_parser("memory-show", help="Show island details")
    mem_show.add_argument("id", help="Island ID")

    sub.add_parser("memory-sleep", help="Force ILHA sleep cycle with stored interactions")

    p_prop = sub.add_parser("pina-propose", help="Propose a Normative Candidate")
    p_prop.add_argument("--source", required=True)
    p_prop.add_argument("--statement", required=True)
    p_prop.add_argument("--location", required=True)
    p_prop.add_argument("--graph-scope")

    p_dec = sub.add_parser("pina-decide", help="Record human PINA decision")
    p_dec.add_argument("--nca-id", required=True)
    p_dec.add_argument("--decision", required=True)
    p_dec.add_argument("--reason")

    args = parser.parse_args(argv)
    state_path, ledger_path, ilhas_path = _paths()
    machine = _load_machine(state_path)
    ledger = Ledger(ledger_path=ledger_path)

    from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas
    armazenamento = ArmazenamentoIlhas(ilhas_path)
    ritual = Acordar(
        state_machine=machine,
        ledger=ledger,
        armazenamento=armazenamento,
    )

    if args.command == "acordar":
        if machine.current_cycle is None:
            machine.start_cycle()
        result = ritual.execute(args.anchor, args.intention, mode=args.mode)
        print(result.message)
        if result.success:
            print(f"State: {machine.current_cycle.state.value}")
        _save_machine(machine, state_path)
        return 0 if result.success else 1

    if args.command == "vai-dormir":
        interacoes = None
        if args.interacao:
            interacoes = [json.loads(i) for i in args.interacao]
        report = ritual.vai_dormir(interacoes=interacoes)
        print(report["message"])
        if report["success"]:
            print(f"State: {machine.current_cycle.state.value}")
            print(f"Islands: {len(armazenamento.listar())}")
        _save_machine(machine, state_path)
        return 0 if report["success"] else 1

    if args.command == "resume":
        tarefa = getattr(args, "tarefa", None)
        report = ritual.resume(tarefa=tarefa)
        print(report["message"])
        if tarefa and report.get("bundle"):
            b = report["bundle"]
            print(f"Bundle: {b['ilhas_count']} islands, {b['claims_count']} claims, {b['lacunas_count']} gaps")
        _save_machine(machine, state_path)
        return 0 if report["success"] else 1

    if args.command == "status":
        status = machine.get_status()
        print(json.dumps(status, indent=2))
        print(f"State: {status.get('state', 'NO_CYCLE')}")
        return 0

    pina = _rebuild_pina(machine, ledger)

    if args.command == "pina-propose":
        result = pina.propose_candidate(
            args.source, args.statement, args.location, graph_scope=args.graph_scope
        )
        print(result.message)
        print(f"{result.nca_id} pending")
        _save_machine(machine, state_path)
        return 0 if result.success else 1

    if args.command == "pina-decide":
        result = pina.decide(args.nca_id, args.decision, reason=args.reason)
        print(result.message)
        _save_machine(machine, state_path)
        return 0 if result.success else 1

    if args.command == "memory-list":
        if args.active_only:
            ilhas = [i for i in armazenamento.listar() if i.e_ativa(threshold=args.threshold)]
        else:
            ilhas = armazenamento.listar()
        dados = [
            {
                "id": i.id,
                "nome": i.nome,
                "estado": i.estado.value,
                "score": round(i.score_ativacao, 3),
                "membros": len(i.membros),
            }
            for i in ilhas
        ]
        print(json.dumps(dados, indent=2, ensure_ascii=False))
        print(f"\nTotal: {len(dados)} islands")
        return 0

    if args.command == "memory-show":
        ilha = armazenamento.obter(args.id)
        if ilha is None:
            print(f"Island not found: {args.id}")
            return 1
        print(json.dumps(ilha.para_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "memory-sleep":
        if not machine.current_cycle:
            print("No active cycle. Start regime first.")
            return 1
        session_id = machine.current_cycle.cycle_id
        from lib.epistemic.memory.dormir import ir_dormir
        from lib.epistemic.memory.shadow_loader import carregar_shadow_docs
        shadow_dir = Path(
            os.environ.get(
                "AES_SHADOW_DIR",
                Path(__file__).parent.parent.parent.parent / "aes" / "shadow",
            )
        )
        interacoes = carregar_shadow_docs(shadow_dir) if shadow_dir.exists() else []
        report = ir_dormir(armazenamento, session_id, interacoes)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
