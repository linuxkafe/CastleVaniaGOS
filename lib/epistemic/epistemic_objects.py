"""
Epistemic Objects — Core data structures for epistemic governance.

SOURCE: Grilo Falante v3 (https://github.com/rodolfomatos/grilo_falante)
This is the UNIFIED canonical copy — AES T036 merged the divergent copies
from models/epistemic_objects.py and grilo_falante/backend/services/governance/epistemic_objects.py.

Merge rationale (T036):
  - Base: v3.0 governance copy (160 lines, docstring retained)
  - Change 1: import order from v3.0 governance (List, Optional, Dict, Any)
    over older GF (Any, Dict, List, Optional) — no semantic difference.
  - Change 2: `legitimacy` field typed as `PropositionLegitimacy` with default
    `PropositionLegitimacy.SUSPENDED` (from v3.0 models) instead of `Any = None`
    (v3.0 governance). This is a strict improvement: every proposition starts
    legitimacy-suspended, and the type checker catches misuse.
  - Verdict: 1-hunk merge (import order cosmetic, typing improvement proven).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class PropositionRole(str, Enum):
    FOUNDATIONAL = "foundational"
    ASSUMPTION = "assumption"
    DERIVED = "derived"
    CONSTRAINT = "constraint"


class PropositionLegitimacy(str, Enum):
    SUSPENDED = "LEGITIMACY_SUSPENDED"
    ASSERTED = "LEGITIMACY_ASSERTED"


class RelationType(str, Enum):
    SUPPORTS = "supports"
    DEPENDS_ON = "depends_on"
    CONTRADICTS = "contradicts"
    NARROWS = "narrows"
    EXTENDS = "extends"
    ATTACKS = "attacks"
    # T302 (MINOR-1): alinha com premise_engine.RelationType (peso 0.8).
    # O DOT canónico declara CONSTRAINS como edge type legítimo; antes isto
    # degradava silenciosamente para DEPENDS_ON, invertendo a direcção de risco.
    CONSTRAINS = "constrains"


class TensionType(str, Enum):
    CONTRADICTION = "contradiction"
    UNCERTAINTY = "uncertainty"
    INCOMPLETENESS = "incompleteness"
    COMPETING = "competing"


class TensionResolution(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    SUSPENDED = "suspended"
    ACCEPTED = "accepted"


class LoopStatus(str, Enum):
    OPEN = "OPEN"
    SCHEDULED = "SCHEDULED"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"
    PROMOTED = "PROMOTED"


class LoopCriticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClosureType(str, Enum):
    EVIDENCE_BASED = "evidence_based"
    TRUSTED_COMMITMENT = "trusted_commitment"
    SUSPENSION = "suspension"
    BLOCKED = "blocked"


class FalsificationStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ArtefactType(str, Enum):
    DOCUMENTO_SOMBRA = "DocumentoSombra"
    OBJETO_DIGITAL = "ObjetoDigital"
    CAPSULA_CONCEPTUAL = "CapsulaConceptual"


@dataclass
class FalsificationCondition:
    id: str
    proposition_id: str
    condition_text: str
    evidence_needed: str
    status: FalsificationStatus = FalsificationStatus.PENDING


@dataclass
class Proposition:
    id: str
    statement: str
    role: PropositionRole
    gmif_type: str
    legitimacy: PropositionLegitimacy = PropositionLegitimacy.SUSPENDED
    supporting_claim_ids: List[str] = field(default_factory=list)
    falsification_conditions: List[FalsificationCondition] = field(default_factory=list)
    boundary_conditions: str = ""
    confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PropositionDependency:
    from_proposition: str
    to_proposition: str
    relation_type: RelationType


@dataclass
class TensionRecord:
    id: str
    left_proposition_id: str
    right_proposition_id: str
    tension_type: TensionType
    severity: int
    resolution_status: TensionResolution = TensionResolution.UNRESOLVED


@dataclass
class OpenLoop:
    id: str
    source_type: str
    source_id: str
    status: LoopStatus = LoopStatus.OPEN
    criticality: LoopCriticality = LoopCriticality.MEDIUM
    closure_policy: str = ""
    trusted_commitment: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ClosureRecord:
    loop_id: str
    closure_type: ClosureType
    evidence: Optional[str] = None
    committed_by: Optional[str] = None
    closed_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TrustedCommitment:
    id: str
    claim_id: str
    commitment_text: str
    materialization: str
    committed_by: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Artefact:
    type: ArtefactType
    id: str
    provenance: Dict[str, Any] = field(default_factory=dict)
    content: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
