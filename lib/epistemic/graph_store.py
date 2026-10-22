"""
In-memory graph store for epistemic knowledge graphs.

Implements the KnowledgeGraphStore interface without database dependencies.
Reads from DOT edges + markdown links + merged_from metadata.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from pathlib import Path
import re


@dataclass
class GraphEdge:
    """Directed edge in the knowledge graph."""
    source: str
    target: str
    relation: str
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class GraphNode:
    """Node in the knowledge graph."""
    id: str
    label: str
    node_type: str  # shadow_doc, ticket, concept, claim
    gmif_level: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class KnowledgeGraphStore(ABC):
    """Abstract interface for knowledge graph storage."""

    @abstractmethod
    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""

    @abstractmethod
    def add_edge(self, edge: GraphEdge) -> None:
        """Add a directed edge to the graph."""

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node by ID."""

    @abstractmethod
    def get_edges_from(self, node_id: str) -> List[GraphEdge]:
        """Get all outgoing edges from a node."""

    @abstractmethod
    def get_edges_to(self, node_id: str) -> List[GraphEdge]:
        """Get all incoming edges to a node."""

    @abstractmethod
    def get_neighbors(self, node_id: str) -> List[GraphNode]:
        """Get all neighboring nodes (both directions)."""

    @abstractmethod
    def find_paths(self, source: str, target: str, max_depth: int = 5) -> List[List[str]]:
        """Find all paths between source and target up to max_depth."""

    @abstractmethod
    def get_subgraph(self, node_ids: Set[str]) -> "KnowledgeGraphStore":
        """Extract a subgraph containing only the specified nodes."""

    @abstractmethod
    def node_count(self) -> int:
        """Return the number of nodes."""

    @abstractmethod
    def edge_count(self) -> int:
        """Return the number of edges."""

    @abstractmethod
    def get_all_nodes(self) -> Dict[str, "GraphNode"]:
        """Return all nodes as a dict. Replaces direct _nodes access."""

    @abstractmethod
    def get_nodes_by_gmif_level(self, level: str) -> List["GraphNode"]:
        """Return nodes filtered by GMIF level (M1-M7)."""

    @abstractmethod
    def get_edges_filtered(
        self, node_id: str, direction: str, relations: Set[str]
    ) -> List["GraphEdge"]:
        """Return edges filtered by direction and relation types.

        Args:
            node_id: The node to query edges for.
            direction: 'in' for incoming, 'out' for outgoing, 'both' for all.
            relations: Set of relation types to include (e.g. {'contradicts', 'refutes'}).
        """

    @abstractmethod
    def count_edges_filtered(
        self, node_id: str, direction: str, relations: Set[str]
    ) -> int:
        """Count edges matching direction and relation filter."""


class InMemoryGraphStore(KnowledgeGraphStore):
    """In-memory implementation of KnowledgeGraphStore.

    Reads graph data from:
    - DOT files (*.dot) in aes/premises/
    - Markdown links in shadow docs
    - merged_from metadata in shadow docs
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._adjacency: Dict[str, List[int]] = {}  # node_id -> list of edge indices
        self._reverse_adjacency: Dict[str, List[int]] = {}

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self._nodes[node.id] = node
        if node.id not in self._adjacency:
            self._adjacency[node.id] = []
        if node.id not in self._reverse_adjacency:
            self._reverse_adjacency[node.id] = []

    def add_edge(self, edge: GraphEdge) -> None:
        """Add a directed edge to the graph."""
        idx = len(self._edges)
        self._edges.append(edge)

        # Ensure nodes exist
        if edge.source not in self._nodes:
            self.add_node(GraphNode(id=edge.source, label=edge.source, node_type="unknown"))
        if edge.target not in self._nodes:
            self.add_node(GraphNode(id=edge.target, label=edge.target, node_type="unknown"))

        self._adjacency.setdefault(edge.source, []).append(idx)
        self._reverse_adjacency.setdefault(edge.target, []).append(idx)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Retrieve a node by ID."""
        return self._nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> List[GraphEdge]:
        """Get all outgoing edges from a node."""
        indices = self._adjacency.get(node_id, [])
        return [self._edges[i] for i in indices]

    def get_edges_to(self, node_id: str) -> List[GraphEdge]:
        """Get all incoming edges to a node."""
        indices = self._reverse_adjacency.get(node_id, [])
        return [self._edges[i] for i in indices]

    def get_neighbors(self, node_id: str) -> List[GraphNode]:
        """Get all neighboring nodes (both directions)."""
        neighbor_ids: Set[str] = set()
        for edge in self.get_edges_from(node_id):
            neighbor_ids.add(edge.target)
        for edge in self.get_edges_to(node_id):
            neighbor_ids.add(edge.source)
        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def find_paths(self, source: str, target: str, max_depth: int = 5) -> List[List[str]]:
        """Find all paths between source and target using BFS."""
        if source not in self._nodes or target not in self._nodes:
            return []

        paths: List[List[str]] = []
        queue: List[List[str]] = [[source]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if len(path) > max_depth:
                continue

            if current == target and len(path) > 1:
                paths.append(path)
                continue

            for edge in self.get_edges_from(current):
                if edge.target not in path:  # Avoid cycles
                    queue.append(path + [edge.target])

        return paths

    def get_subgraph(self, node_ids: Set[str]) -> "InMemoryGraphStore":
        """Extract a subgraph containing only the specified nodes."""
        subgraph = InMemoryGraphStore()

        for node_id in node_ids:
            if node_id in self._nodes:
                subgraph.add_node(self._nodes[node_id])

        for edge in self._edges:
            if edge.source in node_ids and edge.target in node_ids:
                subgraph.add_edge(edge)

        return subgraph

    def node_count(self) -> int:
        """Return the number of nodes."""
        return len(self._nodes)

    def edge_count(self) -> int:
        """Return the number of edges."""
        return len(self._edges)

    def get_all_nodes(self) -> Dict[str, GraphNode]:
        """Return all nodes as a dict."""
        return dict(self._nodes)

    def get_nodes_by_gmif_level(self, level: str) -> List[GraphNode]:
        """Return nodes filtered by GMIF level (M1-M7)."""
        return [
            n for n in self._nodes.values()
            if (n.gmif_level or "M1") == level
        ]

    def get_edges_filtered(
        self, node_id: str, direction: str, relations: Set[str]
    ) -> List[GraphEdge]:
        """Return edges filtered by direction and relation types."""
        result: List[GraphEdge] = []
        if direction in ("out", "both"):
            for edge in self.get_edges_from(node_id):
                if edge.relation in relations:
                    result.append(edge)
        if direction in ("in", "both"):
            for edge in self.get_edges_to(node_id):
                if edge.relation in relations:
                    result.append(edge)
        return result

    def count_edges_filtered(
        self, node_id: str, direction: str, relations: Set[str]
    ) -> int:
        """Count edges matching direction and relation filter."""
        return len(self.get_edges_filtered(node_id, direction, relations))

    def load_from_dot(self, dot_path: Path) -> int:
        """Load graph edges from a DOT file. Returns number of edges loaded."""
        if not dot_path.exists():
            return 0

        content = dot_path.read_text(encoding="utf-8")
        edge_count = 0

        # Parse DOT edges: "source" -> "target" [label="relation"]
        for match in re.finditer(
            r'"([^"]+)"\s*->\s*"([^"]+)"(?:\s*\[([^\]]*)\])?',
            content,
        ):
            source, target, attrs = match.group(1), match.group(2), match.group(3) or ""
            relation = "inferred"
            weight = 1.0

            label_match = re.search(r'label="([^"]+)"', attrs)
            if label_match:
                relation = label_match.group(1)

            weight_match = re.search(r'weight=([0-9.]+)', attrs)
            if weight_match:
                weight = float(weight_match.group(1))

            self.add_edge(GraphEdge(
                source=source,
                target=target,
                relation=relation,
                weight=weight,
                metadata={"source_file": str(dot_path)},
            ))
            edge_count += 1

        return edge_count

    def load_from_shadow_doc(self, doc_id: str, frontmatter: Dict) -> int:
        """Load edges from shadow doc metadata. Returns number of edges loaded."""
        edge_count = 0

        # Edges from merged_from
        provenance = frontmatter.get("provenance", {})
        for merged_id in provenance.get("merged_from", []):
            self.add_edge(GraphEdge(
                source=merged_id,
                target=doc_id,
                relation="merged_into",
                metadata={"merged_at": provenance.get("merged_at", "")},
            ))
            edge_count += 1

        # Edges from sources
        for source in frontmatter.get("sources", []):
            source_resource = source.get("resource", "")
            if source_resource:
                self.add_edge(GraphEdge(
                    source=source_resource,
                    target=doc_id,
                    relation="sourced_by",
                    metadata={"usage_count": source.get("usage_count", 0)},
                ))
                edge_count += 1

        # Edges from blocked_by (may be string or list)
        blocked_by = frontmatter.get("blocked_by", [])
        if isinstance(blocked_by, str):
            blocked_by = [blocked_by] if blocked_by else []
        for blocked in blocked_by:
            self.add_edge(GraphEdge(
                source=doc_id,
                target=blocked,
                relation="blocked_by",
            ))
            edge_count += 1

        # Edges from produces
        for produced in frontmatter.get("produces", []):
            self.add_edge(GraphEdge(
                source=doc_id,
                target=produced,
                relation="produces",
            ))
            edge_count += 1

        return edge_count
