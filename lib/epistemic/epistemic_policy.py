"""
Epistemic Policy Layer (EPL)

Encodes Grilo Falante (GF) epistemic governance principles
into executable decision rules.

This layer sits between:
    compiler -> governance

It evaluates structural epistemic quality, NOT just scores.

SOURCE: Grilo Falante v3 (https://github.com/rodolfomatos/grilo_falante)
AES T036: GF `settings` dependency replaced with inline defaults.
"""


POLICY = {
    "min_consensus": 0.3,
    "max_fragility": 0.6,
    "block_on_contradiction": True,
    "block_on_cycles": True,
    "block_on_unsupported": True,
    "require_multi_source": True,
    "min_sources": 2,
    "allow_low_evidence_if_single_claim": True,
    "evidence_threshold": 0.4,
    "m4_block_threshold": 0.7,
}


def _avg(values, key):
    if not values:
        return None
    try:
        return sum(v[key] for v in values) / len(values)
    except Exception:
        return None


def _graph_source_ids(consensus=None, fragility=None):
    source_ids = set()
    for collection in (consensus or [], fragility or []):
        for item in collection:
            if isinstance(item, dict):
                for source_id in item.get("source_ids", []) or []:
                    source_ids.add(str(source_id))
    return source_ids


def evaluate_epistemic_policy(
    claims,
    lint=None,
    fragility=None,
    contradictions=None,
    _tension_map=None,
    consensus=None,
):
    """
    Evaluate epistemic policy and return governance decision.

    Returns:
        tuple: (decision: "allow" | "block", reason: str)
    """
    if not claims:
        return "block", "no_claims"

    num_claims = len(claims)
    num_inferences = 0

    if lint:
        num_inferences = len(
            [
                n
                for n in (lint.get("weak_nodes") or [])
                if isinstance(n, str) and n.startswith("inf_")
            ]
        )

    is_factoid = num_claims <= 2 and num_inferences == 0
    has_contradictions = bool(contradictions)

    if is_factoid and not has_contradictions:
        return "allow", "factoid_mode"

    if lint:
        if POLICY["block_on_cycles"] and lint.get("cycles"):
            return "block", "circular_reasoning"

        if POLICY["block_on_unsupported"] and lint.get("unsupported_conclusions"):
            return "block", "unsupported_conclusion"

        if lint.get("hallucinated_edges"):
            return "block", "hallucinated_relations"

    if POLICY["block_on_contradiction"]:
        if contradictions and len(contradictions) > 0:
            ratio = len(contradictions) / max(len(claims), 1)
            if ratio > 0.3:
                return "block", "contradictory_evidence"

    avg_fragility = _avg(fragility, "fragility")
    if avg_fragility is not None:
        if avg_fragility > POLICY["max_fragility"]:
            return "block", "high_fragility"

    avg_consensus = _avg(consensus, "consensus")
    if avg_consensus is not None:
        if avg_consensus < POLICY["min_consensus"]:
            return "block", "low_consensus"

    if POLICY["require_multi_source"] and len(claims) > 2:
        sources = _graph_source_ids(consensus=consensus, fragility=fragility)
        if not sources:
            sources = set(str(c.get("source_id")) for c in claims if c.get("source_id") is not None)
        if len(claims) > 1 and len(sources) < POLICY["min_sources"]:
            return "block", "insufficient_source_diversity"

    if len(claims) == 1 and POLICY["allow_low_evidence_if_single_claim"]:
        return "allow", "single_claim_factoid"

    return "allow", "epistemically_valid"
