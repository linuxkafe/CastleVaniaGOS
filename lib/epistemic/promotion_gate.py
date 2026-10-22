"""
Promotion gate — executable gate for the pre-review hook contract.

Contract (defined by .aes/hooks/pre-review.sh):
  python3 -m lib.epistemic.promotion_gate
  exit 0 = promotable, non-zero = blocked by HIGH-criticality open loops.

The loop store is a JSON file (GRILO_LOOPS, default .grilo/loops.json) written
by the cascade propagator. An absent store means no loops have ever been
opened: promotable, with a notice. The exit-code contract is the stable
surface; the storage behind it can change freely.

SOURCE: Grilo Falante v3 (promotion_gate.py)
AES T036: imports updated from relative to lib.epistemic package.
"""

import json
import os
import sys
from pathlib import Path

from lib.epistemic.epistemic_objects import LoopCriticality, LoopStatus, OpenLoop
from lib.epistemic.loop_closure import can_promote


def load_loops(path: Path) -> list:
    """Load OpenLoops from the JSON store; unknown keys are ignored."""
    raw = json.loads(path.read_text())
    loops = []
    for item in raw:
        loops.append(
            OpenLoop(
                id=item["id"],
                source_type=item.get("source_type", "proposition"),
                source_id=item.get("source_id", ""),
                status=LoopStatus(item.get("status", "OPEN")),
                criticality=LoopCriticality(item.get("criticality", "medium")),
                closure_policy=item.get("closure_policy", ""),
            )
        )
    return loops


def main() -> int:
    store = Path(os.environ.get("GRILO_LOOPS", ".grilo/loops.json"))
    if not store.exists():
        print(f"promotion_gate: no loop store at {store} - nothing blocks promotion.")
        return 0

    try:
        loops = load_loops(store)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"promotion_gate: loop store unreadable ({exc}) - BLOCKING.")
        return 2

    promotable, reasons = can_promote(loops)
    if not promotable:
        print("promotion_gate: BLOCKED -")
        for reason in reasons:
            print(f"  {reason}")
        return 1

    print(f"promotion_gate: {len(loops)} loop(s) checked - promotable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
