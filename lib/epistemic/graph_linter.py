"""
Graph Linter — Epistemic integrity checks (L1-L8)

Performs structural integrity checks on epistemic graphs:

L1: Orphan nodes (no incoming edges, not M1/M2)
L2: Self-referential edges
L3: Contradictory edges (supports + contradicts)
L4: Circular dependencies
L5: Unsupported conclusions (M4 source for M1 target)
L6: Missing M1 prerequisites
L7: Confidence mismatches
L8: Falsification gap (M7 claims without falsification conditions)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .graph_store import KnowledgeGraphStore, GraphNode, GraphEdge


@dataclass
class LintIssue:
    """A single lint issue found in the graph."""
    code: str
    severity: str  # error, warning, info
    description: str
    affected_nodes: List[str]
    details: Dict[str, Any] = field(default_factory=dict)


class GraphLinter:
    """Performs epistemic integrity checks on claim graphs."""

    L1_ORPHAN = "L1"
    L2_SELF_REF = "L2"
    L3_CONTRADICTION = "L3"
    L4_CYCLE = "L4"
    L5_UNSUPPORTED = "L5"
    L6_MISSING_M1 = "L6"
    L7_CONFIDENCE_MISMATCH = "L7"
    L8_FALSIFICATION_GAP = "L8"

    def __init__(self, store: Optional[KnowledgeGraphStore] = None):
        self.store = store

    def run_all_checks(self, store: Optional[KnowledgeGraphStore] = None) -> Dict[str, List[LintIssue]]:
        """Run all lint checks and return issues grouped by code."""
        active_store = store or self.store
        if not active_store:
            return {code: [] for code in [
                self.L1_ORPHAN, self.L2_SELF_REF, self.L3_CONTRADICTION,
                self.L4_CYCLE, self.L5_UNSUPPORTED, self.L6_MISSING_M1,
                self.L7_CONFIDENCE_MISMATCH, self.L8_FALSIFICATION_GAP,
            ]}

        graph_data = self._get_graph_data(active_store)

        issues: Dict[str, List[LintIssue]] = {}
        issues[self.L1_ORPHAN] = self._detect_orphans(graph_data)
        issues[self.L2_SELF_REF] = self._detect_self_references(graph_data)
        issues[self.L3_CONTRADICTION] = self._detect_contradictions(graph_data)
        issues[self.L4_CYCLE] = self._detect_cycles(graph_data)
        issues[self.L5_UNSUPPORTED] = self._detect_unsupported_conclusions(graph_data)
        issues[self.L6_MISSING_M1] = self._detect_missing_m1_prerequisites(graph_data)
        issues[self.L7_CONFIDENCE_MISMATCH] = self._detect_confidence_mismatches(graph_data)
        issues[self.L8_FALSIFICATION_GAP] = self._detect_falsification_gaps(graph_data)

        return issues

    def _get_graph_data(self, store: KnowledgeGraphStore) -> Dict[str, Dict]:
        """Extract graph data as dict of node_id -> node info."""
        graph: Dict[str, Dict] = {}

        for node_id, node in store.get_all_nodes().items():
            in_edges = store.get_edges_to(node_id)
            out_edges = store.get_edges_from(node_id)
            graph[node_id] = {
                "id": node_id,
                "label": node.label,
                "node_type": node.node_type,
                "gmif_level": node.gmif_level or "M1",
                "confidence": node.metadata.get("confidence", 0.5),
                "in_edges": [{"source": e.source, "target": e.target, "relation": e.relation} for e in in_edges],
                "out_edges": [{"source": e.source, "target": e.target, "relation": e.relation} for e in out_edges],
            }

        return graph

    def _detect_orphans(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L1: Nodes with no incoming edges (except M1/M2 primary claims)."""
        issues = []

        for node_id, node in graph.items():
            in_edges = node.get("in_edges", [])
            gmif_level = node.get("gmif_level", "M1")

            if not in_edges and gmif_level not in ("M1", "M2"):
                issues.append(LintIssue(
                    code=self.L1_ORPHAN,
                    severity="warning",
                    description="Orphan node without supporting claims",
                    affected_nodes=[node.get("label", node_id)],
                    details={"gmif_level": gmif_level},
                ))

        return issues

    def _detect_self_references(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L2: Self-referential edges."""
        issues = []

        for node_id, node in graph.items():
            for edge in node.get("out_edges", []):
                if edge.get("target") == node_id:
                    issues.append(LintIssue(
                        code=self.L2_SELF_REF,
                        severity="error",
                        description="Self-referential edge detected",
                        affected_nodes=[node.get("label", node_id)],
                        details={"relation": edge.get("relation")},
                    ))

        return issues

    def _detect_contradictions(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L3: Nodes with both supporting and contradicting edges."""
        issues = []

        for node_id, node in graph.items():
            has_support = False
            has_contradict = False

            for edge in node.get("in_edges", []):
                if edge.get("relation") == "supports":
                    has_support = True
                elif edge.get("relation") == "contradicts":
                    has_contradict = True

            if has_support and has_contradict:
                issues.append(LintIssue(
                    code=self.L3_CONTRADICTION,
                    severity="error",
                    description="Node has both supporting and contradicting edges",
                    affected_nodes=[node.get("label", node_id)],
                    details={"has_support": has_support, "has_contradict": has_contradict},
                ))

        return issues

    def _detect_cycles(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L4: Circular dependencies in the graph."""
        issues = []
        visited: set = set()
        rec_stack: set = set()

        def dfs(node_id: str, path: List[str]) -> Optional[List[str]]:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            node = graph.get(node_id, {})
            for edge in node.get("out_edges", []):
                target = edge.get("target")
                if target and target in graph:
                    if target not in visited:
                        cycle = dfs(target, path.copy())
                        if cycle:
                            return cycle
                    elif target in rec_stack:
                        # Found a cycle - return the cycle path
                        try:
                            cycle_start = path.index(target)
                            return path[cycle_start:] + [target]
                        except ValueError:
                            # Target not in path (shouldn't happen with rec_stack)
                            return [node_id, target]

            rec_stack.discard(node_id)
            return None

        for node_id in graph:
            if node_id not in visited:
                cycle = dfs(node_id, [])
                if cycle:
                    node_labels = [
                        graph.get(cid, {}).get("label", cid)
                        for cid in cycle
                        if cid in graph
                    ]
                    issues.append(LintIssue(
                        code=self.L4_CYCLE,
                        severity="error",
                        description="Circular dependency detected",
                        affected_nodes=node_labels,
                        details={"cycle_length": len(cycle)},
                    ))

        return issues

    def _detect_unsupported_conclusions(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L5: Conclusions (M1 targets) sourced from M4 (doubtful) claims."""
        issues = []

        for node_id, node in graph.items():
            if node.get("gmif_level") != "M1":
                continue

            m4_sources = []
            for edge in node.get("in_edges", []):
                source_id = edge.get("source")
                if source_id and source_id in graph:
                    if graph[source_id].get("gmif_level") == "M4":
                        m4_sources.append(graph[source_id].get("label", source_id))

            if m4_sources:
                issues.append(LintIssue(
                    code=self.L5_UNSUPPORTED,
                    severity="error",
                    description="M1 conclusion sourced from M4 (doubtful) claims",
                    affected_nodes=[node.get("label", node_id)],
                    details={"m4_sources": m4_sources},
                ))

        return issues

    def _detect_missing_m1_prerequisites(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L6: Claims without M1/M2 prerequisite claims in evidence chain."""
        issues = []

        for node_id, node in graph.items():
            gmif_level = node.get("gmif_level", "M1")
            if gmif_level in ("M1", "M2"):
                continue

            ancestors = self._get_ancestors(node_id, graph, max_depth=10)
            has_m1_m2_ancestor = False

            for ancestor_id in ancestors:
                ancestor_level = graph.get(ancestor_id, {}).get("gmif_level", "M1")
                if ancestor_level in ("M1", "M2"):
                    has_m1_m2_ancestor = True
                    break

            if not has_m1_m2_ancestor and ancestors:
                issues.append(LintIssue(
                    code=self.L6_MISSING_M1,
                    severity="warning",
                    description="Claim chain missing M1/M2 primary evidence",
                    affected_nodes=[node.get("label", node_id)],
                    details={"ancestor_count": len(ancestors)},
                ))

        return issues

    def _detect_confidence_mismatches(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L7: Claims where confidence doesn't match GMIF level expectations."""
        issues = []

        level_expected = {
            "M1": (0.0, 0.3),   # Assertion → low confidence (no evidence)
            "M2": (0.1, 0.4),   # Observation → moderate-low
            "M3": (0.2, 0.5),   # Inferred → moderate
            "M4": (0.3, 0.6),   # Attributed → moderate (sourced)
            "M5": (0.5, 0.8),   # Evidenced → moderate-high
            "M6": (0.6, 0.9),   # Validated → high
            "M7": (0.7, 1.0),   # Formal → very high (testable)
        }

        for node_id, node in graph.items():
            gmif_level = node.get("gmif_level", "M1")
            confidence = node.get("confidence", 0.5)

            if gmif_level in level_expected:
                min_exp, max_exp = level_expected[gmif_level]
                if confidence < min_exp - 0.2 or confidence > max_exp + 0.2:
                    issues.append(LintIssue(
                        code=self.L7_CONFIDENCE_MISMATCH,
                        severity="warning",
                        description=f"Confidence {confidence} mismatches {gmif_level} expected range",
                        affected_nodes=[node.get("label", node_id)],
                        details={
                            "gmif_level": gmif_level,
                            "confidence": confidence,
                            "expected_range": (min_exp, max_exp),
                        },
                    ))

        return issues

    def _detect_falsification_gaps(self, graph: Dict[str, Dict]) -> List[LintIssue]:
        """L8: M7 claims without falsification conditions."""
        issues = []

        for node_id, node in graph.items():
            if node.get("gmif_level") != "M7":
                continue

            has_falsification = node.get("metadata", {}).get("falsification_conditions")
            if not has_falsification:
                issues.append(LintIssue(
                    code=self.L8_FALSIFICATION_GAP,
                    severity="error",
                    description="M7 claim lacks falsification conditions",
                    affected_nodes=[node.get("label", node_id)],
                    details={"gmif_level": "M7"},
                ))

        return issues

    def _get_ancestors(
        self,
        node_id: str,
        graph: Dict[str, Dict],
        max_depth: int = 5,
    ) -> List[str]:
        """Get ancestor node IDs up to max_depth."""
        ancestors: List[str] = []
        visited: set = set()
        queue = [(node_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue

            visited.add(current_id)
            node = graph.get(current_id, {})

            for edge in node.get("in_edges", []):
                source_id = edge.get("source")
                if source_id and source_id not in visited:
                    ancestors.append(source_id)
                    queue.append((source_id, depth + 1))

        return ancestors
