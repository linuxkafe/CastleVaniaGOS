"""Tests for InMemoryGraphStore, GMIFClassifier, GraphLinter, and EvidenceEngine."""

import pytest
from pathlib import Path
from lib.epistemic.graph_store import (
    InMemoryGraphStore,
    GraphNode,
    GraphEdge,
)
from lib.epistemic.gmif_classifier import (
    classify_claim,
    classify_by_keywords,
    classify_by_metadata,
)
from lib.epistemic.graph_linter import GraphLinter, LintIssue
from lib.epistemic.evidence_engine import EvidenceEngine, EvidenceScore
from lib.epistemic.gmif import GMIFLevel


class TestInMemoryGraphStore:
    """Tests for InMemoryGraphStore."""

    def test_add_node(self):
        store = InMemoryGraphStore()
        node = GraphNode(id="SD-001", label="Test", node_type="shadow_doc")
        store.add_node(node)
        assert store.node_count() == 1
        assert store.get_node("SD-001") is not None

    def test_add_edge(self):
        store = InMemoryGraphStore()
        edge = GraphEdge(source="A", target="B", relation="inferred")
        store.add_edge(edge)
        assert store.edge_count() == 1
        # Nodes created automatically
        assert store.node_count() == 2

    def test_get_edges_from(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))
        store.add_edge(GraphEdge(source="A", target="C", relation="r2"))
        store.add_edge(GraphEdge(source="B", target="C", relation="r3"))

        edges = store.get_edges_from("A")
        assert len(edges) == 2
        targets = {e.target for e in edges}
        assert targets == {"B", "C"}

    def test_get_edges_to(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="C", relation="r1"))
        store.add_edge(GraphEdge(source="B", target="C", relation="r2"))

        edges = store.get_edges_to("C")
        assert len(edges) == 2
        sources = {e.source for e in edges}
        assert sources == {"A", "B"}

    def test_get_neighbors(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))
        store.add_edge(GraphEdge(source="C", target="A", relation="r2"))

        neighbors = store.get_neighbors("A")
        neighbor_ids = {n.id for n in neighbors}
        assert neighbor_ids == {"B", "C"}

    def test_find_paths(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))
        store.add_edge(GraphEdge(source="B", target="C", relation="r2"))
        store.add_edge(GraphEdge(source="A", target="C", relation="r3"))

        paths = store.find_paths("A", "C")
        assert len(paths) == 2
        path_strs = {"->".join(p) for p in paths}
        assert "A->B->C" in path_strs
        assert "A->C" in path_strs

    def test_find_paths_no_path(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))
        store.add_edge(GraphEdge(source="C", target="D", relation="r2"))

        paths = store.find_paths("A", "D")
        assert len(paths) == 0

    def test_get_subgraph(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))
        store.add_edge(GraphEdge(source="B", target="C", relation="r2"))
        store.add_edge(GraphEdge(source="A", target="C", relation="r3"))

        subgraph = store.get_subgraph({"A", "B"})
        assert subgraph.node_count() == 2
        assert subgraph.edge_count() == 1  # Only A->B

    def test_load_from_dot(self, tmp_path):
        dot_content = '''
        digraph G {
            "SD-001" -> "SD-002" [label="inferred"];
            "SD-002" -> "SD-003" [label="sourced_by" weight=2.0];
        }
        '''
        dot_file = tmp_path / "test.dot"
        dot_file.write_text(dot_content)

        store = InMemoryGraphStore()
        loaded = store.load_from_dot(dot_file)
        assert loaded == 2
        assert store.edge_count() == 2

    def test_load_from_shadow_doc(self):
        frontmatter = {
            "provenance": {
                "merged_from": ["SD-OLD-001", "SD-OLD-002"],
                "merged_at": "2026-01-01T00:00:00Z",
            },
            "sources": [
                {"resource": "docs/test.md", "usage_count": 5},
            ],
            "blocked_by": ["T001"],
            "produces": ["T002"],
        }

        store = InMemoryGraphStore()
        loaded = store.load_from_shadow_doc("SD-NEW-001", frontmatter)
        assert loaded == 5  # 2 merged + 1 source + 1 blocked + 1 produces
        assert store.edge_count() == 5

    def test_get_all_nodes(self):
        store = InMemoryGraphStore()
        store.add_node(GraphNode(id="A", label="A", node_type="concept"))
        store.add_node(GraphNode(id="B", label="B", node_type="concept"))
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))

        all_nodes = store.get_all_nodes()
        assert isinstance(all_nodes, dict)
        assert len(all_nodes) == 2
        assert "A" in all_nodes
        assert "B" in all_nodes
        assert all_nodes["A"].label == "A"

    def test_get_all_nodes_includes_auto_created(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="X", target="Y", relation="r1"))

        all_nodes = store.get_all_nodes()
        assert len(all_nodes) == 2
        assert all_nodes["X"].node_type == "unknown"
        assert all_nodes["Y"].node_type == "unknown"

    def test_get_nodes_by_gmif_level(self):
        store = InMemoryGraphStore()
        store.add_node(GraphNode(id="A", label="A", node_type="concept", gmif_level="M1"))
        store.add_node(GraphNode(id="B", label="B", node_type="concept", gmif_level="M5"))
        store.add_node(GraphNode(id="C", label="C", node_type="concept", gmif_level="M5"))
        store.add_node(GraphNode(id="D", label="D", node_type="concept", gmif_level=None))

        m5_nodes = store.get_nodes_by_gmif_level("M5")
        assert len(m5_nodes) == 2
        ids = {n.id for n in m5_nodes}
        assert ids == {"B", "C"}

        m1_nodes = store.get_nodes_by_gmif_level("M1")
        assert len(m1_nodes) == 2  # A + D (None defaults to M1)
        ids = {n.id for n in m1_nodes}
        assert ids == {"A", "D"}

    def test_get_edges_filtered_out(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="contradicts"))
        store.add_edge(GraphEdge(source="A", target="C", relation="supports"))
        store.add_edge(GraphEdge(source="A", target="D", relation="contradicts"))

        result = store.get_edges_filtered("A", "out", {"contradicts"})
        assert len(result) == 2
        targets = {e.target for e in result}
        assert targets == {"B", "D"}

    def test_get_edges_filtered_in(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="X", target="A", relation="contradicts"))
        store.add_edge(GraphEdge(source="Y", target="A", relation="supports"))

        result = store.get_edges_filtered("A", "in", {"contradicts"})
        assert len(result) == 1
        assert result[0].source == "X"

    def test_get_edges_filtered_both(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="contradicts"))
        store.add_edge(GraphEdge(source="C", target="A", relation="contradicts"))

        result = store.get_edges_filtered("A", "both", {"contradicts"})
        assert len(result) == 2

    def test_count_edges_filtered(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="contradicts"))
        store.add_edge(GraphEdge(source="A", target="C", relation="supports"))
        store.add_edge(GraphEdge(source="D", target="A", relation="contradicts"))

        count = store.count_edges_filtered("A", "both", {"contradicts"})
        assert count == 2

        count = store.count_edges_filtered("A", "out", {"supports"})
        assert count == 1


class TestGMIFClassifier:
    """Tests for GMIFClassifier."""

    def test_classify_assertion(self):
        result = classify_claim("I think this might work")
        assert result.level == GMIFLevel.M1_ASSERTION
        assert result.confidence > 0.2

    def test_classify_observation(self):
        result = classify_claim("I observed that the test fails")
        assert result.level == GMIFLevel.M2_OBSERVATION
        assert result.confidence > 0.2

    def test_classify_inferred(self):
        result = classify_claim("Therefore, we can infer that the system is broken")
        assert result.level == GMIFLevel.M3_INFERRED
        assert result.confidence > 0.2

    def test_classify_attributed(self):
        result = classify_claim("According to the documentation, this is correct")
        assert result.level == GMIFLevel.M4_ATTRIBUTED
        assert result.confidence > 0.2

    def test_classify_evidenced(self):
        result = classify_claim("Evidence shows that the benchmark confirms this")
        assert result.level == GMIFLevel.M5_EVIDENCED
        assert result.confidence > 0.2

    def test_classify_validated(self):
        result = classify_claim("Cross-validated by multiple independent sources")
        assert result.level == GMIFLevel.M6_VALIDATED
        assert result.confidence > 0.2

    def test_classify_formal(self):
        result = classify_claim("This claim is falsifiable and has formal preconditions")
        assert result.level == GMIFLevel.M7_FORMAL
        assert result.confidence > 0.2

    def test_classify_with_metadata(self):
        frontmatter = {
            "sources": [{"resource": "test.md"}],
            "verified": [{"by": "test", "at": "2026-01-01"}],
        }
        result = classify_claim("This is supported by evidence", frontmatter)
        assert result.confidence > 0.2

    def test_classify_with_claimed_level(self):
        result = classify_claim(
            "I think this might work",
            claimed_level=GMIFLevel.M3_INFERRED,
        )
        assert result.level == GMIFLevel.M3_INFERRED

    def test_classify_keywords(self):
        scores = classify_by_keywords("I think this is correct according to the docs")
        assert scores[GMIFLevel.M1_ASSERTION] > 0
        assert scores[GMIFLevel.M4_ATTRIBUTED] > 0

    def test_classify_metadata(self):
        scores = classify_by_metadata({
            "sources": [{"resource": "test.md"}],
            "verified": [{"by": "test", "at": "2026-01-01"}],
        })
        assert scores[GMIFLevel.M4_ATTRIBUTED] > 0
        assert scores[GMIFLevel.M6_VALIDATED] > 0


class TestGraphLinter:
    """Tests for GraphLinter."""

    def test_l1_orphan_detection(self):
        store = InMemoryGraphStore()
        store.add_node(GraphNode(id="A", label="A", node_type="claim", gmif_level="M4"))
        store.add_node(GraphNode(id="B", label="B", node_type="claim", gmif_level="M1"))
        # A is orphan (M4 without incoming edges), B is not (M1 is ok)

        linter = GraphLinter(store)
        issues = linter.run_all_checks(store)
        assert len(issues["L1"]) == 1
        assert issues["L1"][0].affected_nodes == ["A"]

    def test_l2_self_reference(self):
        store = InMemoryGraphStore()
        store.add_node(GraphNode(id="A", label="A", node_type="claim"))
        store.add_edge(GraphEdge(source="A", target="A", relation="self"))

        linter = GraphLinter(store)
        issues = linter.run_all_checks(store)
        assert len(issues["L2"]) == 1

    def test_l3_contradiction(self):
        store = InMemoryGraphStore()
        store.add_node(GraphNode(id="A", label="A", node_type="claim"))
        store.add_edge(GraphEdge(source="B", target="A", relation="supports"))
        store.add_edge(GraphEdge(source="C", target="A", relation="contradicts"))

        linter = GraphLinter(store)
        issues = linter.run_all_checks(store)
        assert len(issues["L3"]) == 1

    def test_l4_cycle(self):
        store = InMemoryGraphStore()
        store.add_edge(GraphEdge(source="A", target="B", relation="r1"))
        store.add_edge(GraphEdge(source="B", target="C", relation="r2"))
        store.add_edge(GraphEdge(source="C", target="A", relation="r3"))

        linter = GraphLinter(store)
        issues = linter.run_all_checks(store)
        assert len(issues["L4"]) == 1

    def test_l8_falsification_gap(self):
        store = InMemoryGraphStore()
        store.add_node(GraphNode(
            id="M7-1", label="M7 Claim", node_type="claim",
            gmif_level="M7", metadata={}
        ))

        linter = GraphLinter(store)
        issues = linter.run_all_checks(store)
        assert len(issues["L8"]) == 1


class TestEvidenceEngine:
    """Tests for EvidenceEngine."""

    def test_compute_score(self):
        engine = EvidenceEngine()
        score = engine.compute("test-node", {"sources": [{"resource": "test.md"}]})
        assert 0.0 <= score.score <= 1.0
        assert isinstance(score.level, GMIFLevel)

    def test_score_to_level(self):
        engine = EvidenceEngine()
        assert engine.score_to_level(0.9) == GMIFLevel.M7_FORMAL
        assert engine.score_to_level(0.7) == GMIFLevel.M6_VALIDATED
        assert engine.score_to_level(0.5) == GMIFLevel.M5_EVIDENCED
        assert engine.score_to_level(0.1) == GMIFLevel.M1_ASSERTION

    def test_temporal_decay(self):
        from datetime import datetime, timezone, timedelta
        engine = EvidenceEngine()

        # Fresh source
        fresh = engine.compute("test", {}, datetime.now(timezone.utc))
        assert fresh.factors["temporal"] == 1.0

        # Old source
        old = engine.compute("test", {}, datetime.now(timezone.utc) - timedelta(days=400))
        assert old.factors["temporal"] < 1.0


class TestGovernanceOrchestrator:
    """Tests for GovernanceOrchestrator."""

    def test_govern_claim_basic(self):
        from lib.epistemic.orchestrator import GovernanceOrchestrator
        orchestrator = GovernanceOrchestrator()
        result = orchestrator.govern_claim(
            "This is a test claim",
            claim_id="test-1",
        )
        assert result.overall_decision in ("allow", "warn", "block")
        assert result.gmif_result.level in list(GMIFLevel)

    def test_govern_claim_with_metadata(self):
        from lib.epistemic.orchestrator import GovernanceOrchestrator
        orchestrator = GovernanceOrchestrator()
        result = orchestrator.govern_claim(
            "Evidence shows this is correct",
            claim_id="test-2",
            frontmatter={"sources": [{"resource": "test.md"}]},
        )
        assert result.overall_decision in ("allow", "warn", "block")

    def test_run_graph_lint(self):
        from lib.epistemic.orchestrator import GovernanceOrchestrator
        store = InMemoryGraphStore()
        store.add_node(GraphNode(id="A", label="A", node_type="claim", gmif_level="M4"))
        orchestrator = GovernanceOrchestrator(store)
        issues = orchestrator.run_graph_lint()
        assert "L1" in issues  # Should detect orphan
