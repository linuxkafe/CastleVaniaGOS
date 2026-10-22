"""Comprehensive tests for epistemic_policy.py (T167).

Covers: all decision paths in evaluate_epistemic_policy, helper functions,
edge cases, policy configuration.
"""

import pytest

from lib.epistemic.epistemic_policy import (
    POLICY,
    _avg,
    _graph_source_ids,
    evaluate_epistemic_policy,
)


# ── _avg helper ──────────────────────────────────────────────────────────


class TestAvg:
    def test_empty_returns_none(self):
        assert _avg([], "key") is None

    def test_single_item(self):
        assert _avg([{"key": 10}], "key") == 10.0

    def test_multiple_items(self):
        assert _avg([{"key": 2}, {"key": 4}], "key") == 3.0

    def test_missing_key_returns_none(self):
        assert _avg([{"other": 1}], "key") is None

    def test_non_dict_returns_none(self):
        assert _avg(["not_a_dict"], "key") is None


# ── _graph_source_ids helper ─────────────────────────────────────────────


class TestGraphSourceIds:
    def test_empty(self):
        assert _graph_source_ids() == set()

    def test_from_consensus(self):
        consensus = [{"source_ids": ["s1", "s2"]}]
        result = _graph_source_ids(consensus=consensus)
        assert result == {"s1", "s2"}

    def test_from_fragility(self):
        fragility = [{"source_ids": ["s3"]}]
        result = _graph_source_ids(fragility=fragility)
        assert result == {"s3"}

    def test_from_both(self):
        consensus = [{"source_ids": ["s1"]}]
        fragility = [{"source_ids": ["s2"]}]
        result = _graph_source_ids(consensus=consensus, fragility=fragility)
        assert result == {"s1", "s2"}

    def test_deduplicates(self):
        consensus = [{"source_ids": ["s1", "s1"]}]
        result = _graph_source_ids(consensus=consensus)
        assert result == {"s1"}

    def test_missing_source_ids(self):
        consensus = [{"other": "data"}]
        result = _graph_source_ids(consensus=consensus)
        assert result == set()

    def test_none_source_ids(self):
        consensus = [{"source_ids": None}]
        result = _graph_source_ids(consensus=consensus)
        assert result == set()


# ── evaluate_epistemic_policy ────────────────────────────────────────────


class TestEvaluateEpistemicPolicy:
    def test_no_claims_blocks(self):
        decision, reason = evaluate_epistemic_policy([])
        assert decision == "block"
        assert reason == "no_claims"

    def test_single_claim_factoid_allows(self):
        claims = [{"text": "hello"}]
        decision, reason = evaluate_epistemic_policy(claims)
        assert decision == "allow"
        assert reason == "factoid_mode"

    def test_two_claims_no_inferences_factoid(self):
        claims = [{"text": "a"}, {"text": "b"}]
        decision, reason = evaluate_epistemic_policy(claims)
        assert decision == "allow"
        assert reason == "factoid_mode"

    def test_two_claims_with_inferences_not_factoid(self):
        claims = [{"text": "a"}, {"text": "b"}]
        lint = {"weak_nodes": ["inf_001"]}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert decision != "factoid_mode"

    def test_contradictions_block(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        contradictions = [{"text": "x"}, {"text": "y"}]
        decision, reason = evaluate_epistemic_policy(
            claims, contradictions=contradictions
        )
        assert decision == "block"
        assert reason == "contradictory_evidence"

    def test_contradictions_below_threshold_allows(self):
        claims = [
            {"text": "a", "source_id": "s1"},
            {"text": "b", "source_id": "s2"},
            {"text": "c", "source_id": "s3"},
            {"text": "d", "source_id": "s4"},
            {"text": "e", "source_id": "s5"},
        ]
        contradictions = [{"text": "x"}]  # 1/5 = 0.2 < 0.3
        decision, reason = evaluate_epistemic_policy(
            claims, contradictions=contradictions
        )
        assert decision == "allow"

    def test_cycles_block(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        lint = {"cycles": [["a", "b"]]}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert decision == "block"
        assert reason == "circular_reasoning"

    def test_unsupported_conclusions_block(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        lint = {"unsupported_conclusions": ["inf_001"]}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert decision == "block"
        assert reason == "unsupported_conclusion"

    def test_hallucinated_edges_block(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        lint = {"hallucinated_edges": ["e1"]}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert decision == "block"
        assert reason == "hallucinated_relations"

    def test_high_fragility_blocks(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        fragility = [{"fragility": 0.8}]
        decision, reason = evaluate_epistemic_policy(claims, fragility=fragility)
        assert decision == "block"
        assert reason == "high_fragility"

    def test_low_fragility_allows(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        fragility = [{"fragility": 0.3, "source_ids": ["s1", "s2"]}]
        decision, reason = evaluate_epistemic_policy(claims, fragility=fragility)
        assert decision == "allow"

    def test_low_consensus_blocks(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        consensus = [{"consensus": 0.1}]
        decision, reason = evaluate_epistemic_policy(claims, consensus=consensus)
        assert decision == "block"
        assert reason == "low_consensus"

    def test_high_consensus_allows(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        consensus = [{"consensus": 0.8, "source_ids": ["s1", "s2"]}]
        decision, reason = evaluate_epistemic_policy(claims, consensus=consensus)
        assert decision == "allow"

    def test_insufficient_source_diversity_blocks(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        fragility = [{"source_ids": ["s1"]}]
        decision, reason = evaluate_epistemic_policy(claims, fragility=fragility)
        assert decision == "block"
        assert reason == "insufficient_source_diversity"

    def test_sufficient_source_diversity_allows(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        fragility = [{"source_ids": ["s1", "s2"]}]
        decision, reason = evaluate_epistemic_policy(claims, fragility=fragility)
        assert decision == "allow"

    def test_source_diversity_from_claim_source_ids(self):
        claims = [
            {"text": "a", "source_id": "s1"},
            {"text": "b", "source_id": "s2"},
            {"text": "c", "source_id": "s3"},
        ]
        decision, reason = evaluate_epistemic_policy(claims)
        assert decision == "allow"
        assert reason == "epistemically_valid"

    def test_epistemically_valid_path(self):
        claims = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
        fragility = [{"fragility": 0.3, "source_ids": ["s1", "s2"]}]
        consensus = [{"consensus": 0.8}]
        decision, reason = evaluate_epistemic_policy(
            claims, fragility=fragility, consensus=consensus
        )
        assert decision == "allow"
        assert reason == "epistemically_valid"

    def test_factoid_with_contradictions_not_factoid_mode(self):
        claims = [{"text": "a"}, {"text": "b"}]
        contradictions = [{"text": "x"}]
        decision, reason = evaluate_epistemic_policy(
            claims, contradictions=contradictions
        )
        # 2 claims, 0 inferences → is_factoid=True, but has_contradictions=True
        # So factoid path is skipped, falls through to contradiction check
        # 1/2 = 0.5 > 0.3 → block
        assert decision == "block"
        assert reason == "contradictory_evidence"

    def test_lint_without_cycles_allows(self):
        claims = [
            {"text": "a", "source_id": "s1"},
            {"text": "b", "source_id": "s2"},
            {"text": "c", "source_id": "s3"},
        ]
        lint = {"weak_nodes": [], "cycles": [], "unsupported_conclusions": [], "hallucinated_edges": []}
        decision, reason = evaluate_epistemic_policy(claims, lint=lint)
        assert decision == "allow"


# ── POLICY defaults ──────────────────────────────────────────────────────


class TestPolicyDefaults:
    def test_min_consensus(self):
        assert POLICY["min_consensus"] == 0.3

    def test_max_fragility(self):
        assert POLICY["max_fragility"] == 0.6

    def test_block_on_contradiction(self):
        assert POLICY["block_on_contradiction"] is True

    def test_block_on_cycles(self):
        assert POLICY["block_on_cycles"] is True

    def test_block_on_unsupported(self):
        assert POLICY["block_on_unsupported"] is True

    def test_require_multi_source(self):
        assert POLICY["require_multi_source"] is True

    def test_min_sources(self):
        assert POLICY["min_sources"] == 2

    def test_allow_low_evidence_if_single_claim(self):
        assert POLICY["allow_low_evidence_if_single_claim"] is True
