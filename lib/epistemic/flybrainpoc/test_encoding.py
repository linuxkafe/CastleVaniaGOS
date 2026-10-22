"""test_encoding.py — unit tests for the T-3 encoder (ablation A vs B)."""

import numpy as np
import pytest

from lib.epistemic.flybrainpoc.encoder import Encoder, parse_logical_form, synapse_weights


def _island(nodes, edges=None):
    return {"artifact": "unit", "version": 1, "notes": "", "nodes": nodes, "edges": edges or []}


def _node(cid, conf, logical="G(C-X)", state="INFERRED", vtype="logical", connectors=None):
    return {
        "id": cid,
        "kind": "claim",
        "category": "2-conditioned",
        "state": state,
        "validation_type": vtype,
        "validation_confidence": conf,
        "extraction_confidence": 0.9,
        "extractor": "test",
        "logical_form": logical,
        "connectors": connectors or [],
        "source_chunks": ["raw/unit"],
        "last_verified": "",
        "verification_method": "",
        "anchor": "unit::t269",
        "sources": [],
        "note": "",
    }


class TestParseLogicalForm:
    def test_bare_claim(self):
        assert parse_logical_form("C-001") == ("DEFAULT", 1.0)

    def test_global(self):
        assert parse_logical_form("G(C-001)") == ("G", 1.0)

    def test_finally(self):
        assert parse_logical_form("F(C-002)") == ("F", 1.0)

    def test_probabilistic(self):
        op, prob = parse_logical_form("P>=0.9(C-003)")
        assert op == "P"
        assert abs(prob - 0.9) < 1e-6

    def test_empty(self):
        assert parse_logical_form("") == ("DEFAULT", 0.0)


class TestRateEncoding:
    def test_rate_encoding_matches_confidence(self):
        """Rate derives from confidence * base_rate."""
        enc = Encoder(base_rate=80.0, mode="rate_only")
        high = _node("C-H", 0.9)
        st = enc.encode_island(_island([high]))
        (neuron, spikes), = st.spike_trains.items()
        # With duration 400ms and rate 72Hz, expected ~28 spikes
        assert len(spikes) > 5
        assert st.meta[neuron]["confidence"] == pytest.approx(0.9)

    def test_rate_only_ignores_timing(self):
        """In rate_only, spikes should be spread over the full horizon for
        both G and F claims — no temporal modulation."""
        np.random.seed(7)
        enc = Encoder(base_rate=80.0, mode="rate_only")
        a = _node("C-G", 0.9, logical="G(C-G)")
        b = _node("C-F", 0.9, logical="F(C-F)")
        st = enc.encode_island(_island([a, b]))
        for spike_times in st.spike_trains.values():
            assert spike_times.max() >= 380.0

    def test_timing_encoding_depends_on_operator(self):
        """Gen G claims are front-loaded (0-200ms); F claims span 0-400ms."""
        np.random.seed(11)
        enc = Encoder(base_rate=80.0, mode="rate+timing")
        g = _node("C-G2", 0.9, logical="G(C-G2)")
        f = _node("C-F2", 0.9, logical="F(C-F2)")
        st = enc.encode_island(_island([g, f]))
        for n, times in st.spike_trains.items():
            if st.meta[n]["operator"] == "G":
                assert times.max() <= 202.0
            elif st.meta[n]["operator"] == "F":
                assert times.max() >= 380.0

    def test_contradicts_creates_two_populations(self):
        """A contradicts edge yields two distinct claim populations."""
        enc = Encoder(mode="rate+timing")
        a = _node("C-A", 0.8, logical="C-A")
        b = _node("C-B", 0.8, logical="C-B")
        st = enc.encode_island(_island([a, b], [{"from": "C-A", "to": "C-B", "type": "contradicts", "strength": "strong"}]))
        assert len(st.spike_trains) == 2
        meta_by_claim = {m["claim"]: (n, m) for n, m in st.meta.items()}
        assert meta_by_claim["C-A"][1]["is_contradiction"] is True
        assert meta_by_claim["C-B"][1]["is_contradiction"] is True


class TestSynapseWeights:
    def test_contradicts_is_inhibitory(self):
        island = _island(
            [_node("C-A", 0.8), _node("C-B", 0.8)],
            [{"from": "C-A", "to": "C-B", "type": "contradicts", "strength": "strong"}],
        )
        w = synapse_weights(island)
        # Positional layout: C-A sits at slot 0, C-B at slot 1.
        assert w[(0, 1)] < 0.0

    def test_implies_is_excitatory(self):
        island = _island(
            [_node("C-A", 0.8), _node("C-B", 0.8)],
            [{"from": "C-A", "to": "C-B", "type": "implies", "strength": "strong"}],
        )
        w = synapse_weights(island)
        assert w[(0, 1)] > 0.0

    def test_unknown_edge_ignored(self):
        island = _island(
            [_node("C-A", 0.8), _node("C-B", 0.8)],
            [{"from": "C-A", "to": "C-B", "type": "mystery", "strength": "strong"}],
        )
        assert synapse_weights(island) == {}