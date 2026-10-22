"""Premises — premise propagation for epistemic governance.

This package re-exports the canonical AES-native propagator
(lib.epistemic.propagator) and adds integration layers:

  Propagator — core algorithm (propagate, retract, propose_contestations)
  PremisesEngine — wires propagator + loop store + regime lifecycle
  wiring — hooks for regime/ILHA integration

Usage:
    from lib.epistemic.premises import propagate, PremisesEngine
    engine = PremisesEngine()
    result = engine.verify_and_propagate()
"""

from lib.epistemic.propagator import (
    ReopenRecord,
    PropagationResult,
    build_risk_graph,
    seed_fallen,
    _cascade_nodes,
    _build_jtms,
    propagate,
    retract,
    propose_claim_contestations,
    CLOSURE_POLICY_PREMISE_FALLEN,
)

from lib.epistemic.premises.engine import PremisesEngine
from lib.epistemic.premises.wiring import (
    run_propagation_for_regime,
    propagate_into_ilha,
)

__all__ = [
    "ReopenRecord",
    "PropagationResult",
    "build_risk_graph",
    "seed_fallen",
    "propagate",
    "retract",
    "propose_claim_contestations",
    "CLOSURE_POLICY_PREMISE_FALLEN",
    "PremisesEngine",
    "run_propagation_for_regime",
    "propagate_into_ilha",
]
