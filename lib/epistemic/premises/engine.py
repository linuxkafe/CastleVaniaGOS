"""PremisesEngine — wraps propagator + loop store + premise loader.

Wires the AES-native premise propagator into the filesystem loop store
that the promotion gate reads. Provides the integration layer:

1. load_premises() — read propositions/dependencies from aes/premises/
2. verify_and_propagate() — run propagator + persist loops
3. get_blockers() — check if propagation blocks promotion
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from lib.epistemic.propagator import (
    propagate,
    retract,
    propagate as core_propagate,
)
from lib.epistemic.epistemic_objects import (
    FalsificationCondition,
    FalsificationStatus,
    LoopCriticality,
    LoopStatus,
    OpenLoop,
    Proposition,
    PropositionDependency,
    PropositionRole,
)
from lib.epistemic.premises.dot_common import (
    join_dot_lines,
    pick_canonical_dot,
    proposition_role,
    relation_type,
)

AES_ROOT = Path(__file__).resolve().parents[3]

LOOPS_DIR = AES_ROOT / "aes" / "loops"
STORE_PATH = LOOPS_DIR / "active.json"
PREMISES_DIR = AES_ROOT / "aes" / "premises"


def _dot_path(premises_dir: Optional[Path] = None) -> Optional[Path]:
    return pick_canonical_dot(premises_dir or PREMISES_DIR)


def _extract_edge_label(line: str) -> str:
    """Extract the relation type from an edge line, e.g. ``[label=CONSTRAINS]``.

    T302 (MINOR-1): the old parser matched substrings (``if 'SUPPORTS' in
    line``), which silently missed CONSTRAINS. Extract the real label value
    and let ``dot_common.relation_type()`` resolve it (supports quoted or
    unquoted labels; edge lines only — never node lines).
    """
    m = re.search(r'label\s*=\s*"?([A-Za-z_]+)"?', line)
    return m.group(1) if m else "DEPENDS_ON"


def _fc_dir(premises_dir: Optional[Path] = None) -> Path:
    base = premises_dir or PREMISES_DIR
    return base / "fc"


def _parse_dot(dot_file: Path):
    content = dot_file.read_text()
    propositions = []
    dependencies = []
    seen_ids: Set[str] = set()

    for line in join_dot_lines(content):
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        if "->" in line and "[" in line and "]" in line:
            parts = line.split("->")
            from_id = parts[0].strip().strip('"')
            to_part = parts[1].split("[")[0].strip().strip('"')
            rel = _extract_edge_label(line)
            dependencies.append(
                PropositionDependency(
                    from_proposition=from_id,
                    to_proposition=to_part,
                    relation_type=relation_type(rel),
                )
            )
            seen_ids.add(from_id)
            seen_ids.add(to_part)

        elif "[" in line and "]" in line and "->" not in line:
            head = line.split("[", 1)[0].strip()
            if not (head.startswith('"') and head.endswith('"')):
                continue
            parts = line.split("[")
            node_id = parts[0].strip().strip('"')
            attrs = parts[1].split("]")[0]
            props = {}
            for attr in attrs.split(","):
                attr = attr.strip()
                if "=" in attr:
                    k, v = attr.split("=", 1)
                    props[k.strip()] = v.strip().strip('"')
            role_str = props.get("type", "DERIVED")
            role = proposition_role(role_str)
            statement = props.get("label", f"Proposition {node_id}")
            propositions.append(
                Proposition(
                    id=node_id,
                    statement=statement,
                    role=role,
                    gmif_type="M6",
                )
            )
            seen_ids.add(node_id)

    for p in propositions:
        if p.id in seen_ids and p.role is None:
            p.role = "DERIVED"

    return propositions, dependencies


def _load_falsification_conditions(premises_dir: Optional[Path] = None) -> List[FalsificationCondition]:
    fc_path = _fc_dir(premises_dir)
    if not fc_path.exists():
        return []
    conditions = []
    for f in sorted(fc_path.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            conditions.append(
                FalsificationCondition(
                    id=data.get("id", f.stem),
                    proposition_id=data.get("proposition_id", ""),
                    condition_text=data.get("condition_text", ""),
                    status=FalsificationStatus(data.get("status", "pending").lower()),
                    evidence_needed=data.get("evidence_needed", ""),
                )
            )
        except Exception:
            pass
    return conditions


class PremisesEngine:
    """Verifies premises and propagates failures through the dependency graph."""

    def __init__(
        self,
        premises_dir: Optional[Path] = None,
        loop_store_path: Optional[Path] = None,
    ):
        self.premises_dir = premises_dir or PREMISES_DIR
        self.loop_store_path = loop_store_path or STORE_PATH
        self._propositions: List[Proposition] = []
        self._dependencies: List[PropositionDependency] = []
        self._fc_conditions: List[FalsificationCondition] = []

    def load_premises(self) -> bool:
        dot = _dot_path(self.premises_dir)
        if dot is None:
            return False
        self._propositions, self._dependencies = _parse_dot(dot)
        self._fc_conditions = _load_falsification_conditions(self.premises_dir)
        return len(self._propositions) > 0

    def get_failed_conditions(self) -> List[FalsificationCondition]:
        return [fc for fc in self._fc_conditions if fc.status == FalsificationStatus.FAILED]

    def has_premises(self) -> bool:
        return len(self._propositions) > 0

    def verify_and_propagate(self) -> Dict[str, Any]:
        dot = _dot_path(self.premises_dir)
        if dot is None:
            return {"message": "No premise graph found", "opened_loops": 0}

        self._propositions, self._dependencies = _parse_dot(dot)
        self._fc_conditions = _load_falsification_conditions(self.premises_dir)

        if not self._propositions:
            return {"message": "No propositions parsed", "opened_loops": 0}

        contested = set()
        for fc in self._fc_conditions:
            if fc.status == FalsificationStatus.FAILED:
                contested.add(fc.proposition_id)

        result = core_propagate(
            propositions=self._propositions,
            dependencies=self._dependencies,
            falsification_conditions=self._fc_conditions,
            contested_ids=contested if contested else None,
        )

        if not result.opened_loops:
            return {"message": "No fallen premises", "opened_loops": 0}

        count = self._persist_loops(result.opened_loops)
        return {
            "message": f"Opened {count} loops for fallen premises",
            "opened_loops": count,
            "opened_loop_ids": [l.id for l in result.opened_loops],
            "seeds": dict(result.seeds),
            "affected": list(result.affected_proposition_ids),
            "reopen_records": [
                {
                    "affected": r.affected_proposition_id,
                    "fallen": r.fallen_proposition_id,
                    "trigger": r.trigger,
                    "path": r.path,
                }
                for r in result.reopen_records
            ],
        }

    def _persist_loops(self, loops: List[OpenLoop]) -> int:
        self.loops_dir.mkdir(parents=True, exist_ok=True)

        existing = {"loops": []}
        if self.loop_store_path.exists():
            try:
                existing = json.loads(self.loop_store_path.read_text())
            except Exception:
                pass

        existing_keys = {(l.get("source_type"), l.get("source_id")) for l in existing.get("loops", [])}
        added = 0
        for loop in loops:
            key = (loop.source_type, loop.source_id)
            if key in existing_keys:
                continue
            existing.setdefault("loops", []).append(
                {
                    "id": loop.id,
                    "source_type": loop.source_type,
                    "source_id": loop.source_id,
                    "status": loop.status.value,
                    "criticality": loop.criticality.value,
                    "closure_policy": loop.closure_policy,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
            added += 1

        if added > 0:
            existing["metadata"] = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
            }
            self.loop_store_path.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n"
            )

        return added

    @property
    def loops_dir(self) -> Path:
        return self.loop_store_path.parent

    def count_blocking_loops(self) -> int:
        if not self.loop_store_path.exists():
            return 0
        try:
            data = json.loads(self.loop_store_path.read_text())
            count = 0
            for loop in data.get("loops", []):
                if loop.get("status") == "OPEN" and loop.get("criticality") == "HIGH":
                    count += 1
            return count
        except Exception:
            return 0

    def get_blockers(self) -> List[str]:
        if not self.loop_store_path.exists():
            return []
        blockers = []
        try:
            data = json.loads(self.loop_store_path.read_text())
            for loop in data.get("loops", []):
                if loop.get("status") == "OPEN" and loop.get("criticality") == "HIGH":
                    sid = loop.get("source_id", "?")
                    desc = loop.get("closure_policy", "premise_fallen")
                    blockers.append(f"{sid} ({desc})")
        except Exception:
            pass
        return blockers
