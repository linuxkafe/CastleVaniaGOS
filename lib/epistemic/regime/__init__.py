"""Regime lifecycle: state machine, append-only ledger, PINA, ACORDAR/VAI_DORMIR.

Ported from Grilo Falante v3 (regime package) as part of AES T036 (ADR-001
unification). Upstream: grilo_falante/backend/services/regime/.
"""

from lib.epistemic.regime.state import (
    CycleState,
    CycleContext,
    LegitimacyState,
    ValidationState,
    StateMachine,
)

from lib.epistemic.regime.ledger import (
    LedgerEntryType,
    LedgerEntry,
    Ledger,
)

from lib.epistemic.regime.acordar import (
    AcordarResult,
    Acordar,
)

from lib.epistemic.regime.pina import (
    PINADecision,
    NormativeCandidateRecord,
    PINAResult,
    PINAProtocol,
)

from lib.epistemic.regime.cli import (
    main as regime_cli_main,
)

__all__ = [
    "CycleState",
    "CycleContext",
    "LegitimacyState",
    "ValidationState",
    "StateMachine",
    "LedgerEntryType",
    "LedgerEntry",
    "Ledger",
    "AcordarResult",
    "Acordar",
    "PINADecision",
    "NormativeCandidateRecord",
    "PINAResult",
    "PINAProtocol",
    "regime_cli_main",
]
