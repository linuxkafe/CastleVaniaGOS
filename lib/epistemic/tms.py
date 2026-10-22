"""
Justification-based Truth Maintenance System (JTMS) — Doyle 1979.

Implements IN/OUT labeling with justifications, dependency-directed retraction,
and odd-cycle NOGOOD detection. This is the semantic core for the premise
propagator: when a premise falls (FalsificationCondition FAILED), we tell the
JTMS the node is OUT; it computes the minimal consequence cone. When a
falsification condition flips back (FAILED → UNKNOWN), we retract the
justification and the JTMS computes the minimal recovery cone.

Reference: Doyle, J. (1979). "A Truth Maintenance System." Artificial Intelligence, 12(3), 231-272.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Iterable


class NodeLabel(Enum):
    IN = "in"
    OUT = "out"


@dataclass
class Justification:
    """A justification: if all antecedents are IN, then consequent is IN."""
    id: str
    antecedents: Set[str]  # node IDs that justify the consequent
    consequent: str        # node ID being justified
    jtype: str             # "DEPENDS_ON" | "SUPPORTS"


@dataclass
class Node:
    """A node in the JTMS network."""
    id: str
    label: NodeLabel = NodeLabel.IN
    justifications: Set[str] = field(default_factory=set)  # justification IDs supporting this node
    in_nogood: bool = False


class JTMS:
    """
    Justification-based Truth Maintenance System.

    Nodes are labeled IN or OUT. A node is IN if it has at least one valid
    justification (all antecedents IN). A node is OUT if all its justifications
    are invalidated (at least one antecedent OUT) or it was explicitly told OUT.

    Supports:
    - Multiple justifications per node (multi-support)
    - Dependency-directed retraction (retract_justification)
    - Odd-cycle detection with NOGOOD creation
    """

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.justifications: Dict[str, Justification] = {}
        self.nogoods: List[Set[str]] = []
        self._justification_counter = 0

    def add_node(self, node_id: str) -> None:
        """Add a node if not present. Default label is IN."""
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(id=node_id)

    def add_justification(
        self,
        antecedents: Set[str],
        consequent: str,
        jtype: str,
    ) -> str:
        """
        Add a justification: antecedents -> consequent.
        Returns the justification ID.
        """
        for ant in antecedents:
            self.add_node(ant)
        self.add_node(consequent)

        self._justification_counter += 1
        jid = f"J{self._justification_counter}"
        just = Justification(id=jid, antecedents=set(antecedents), consequent=consequent, jtype=jtype)
        self.justifications[jid] = just
        self.nodes[consequent].justifications.add(jid)

        # If all antecedents are IN, consequent should be IN
        if all(self.nodes[ant].label == NodeLabel.IN for ant in antecedents):
            if self.nodes[consequent].label == NodeLabel.OUT:
                self._propagate_in(consequent, {jid})

        return jid

    def tell_out(self, node_id: str, reason: str = "") -> Set[str]:
        """
        Explicitly label a node OUT (e.g., premise fallen).
        Returns the set of node IDs that became OUT as a result.
        """
        self.add_node(node_id)
        if self.nodes[node_id].label == NodeLabel.IN:
            return self._propagate_out(node_id, reason)
        return set()

    def tell_in(self, node_id: str) -> Set[str]:
        """
        Explicitly label a node IN (e.g., premise restored).
        Returns the set of node IDs that became IN as a result.
        """
        self.add_node(node_id)
        if self.nodes[node_id].label == NodeLabel.OUT:
            return self._propagate_in(node_id, set())
        return set()

    def retract_justification(self, justification_id: str) -> Set[str]:
        """
        Retract a justification (e.g., falsification condition flipped back).
        Returns the set of node IDs whose label changed.
        """
        if justification_id not in self.justifications:
            return set()

        just = self.justifications[justification_id]
        consequent = just.consequent

        # Remove justification from consequent
        self.nodes[consequent].justifications.discard(justification_id)
        del self.justifications[justification_id]

        # If consequent has no valid justifications left, it becomes OUT
        if not self._has_valid_justification(consequent):
            if self.nodes[consequent].label == NodeLabel.IN:
                return self._propagate_out(consequent, f"justification_retracted:{justification_id}")
        return set()

    def get_label(self, node_id: str) -> NodeLabel:
        """Get the current label of a node (IN by default)."""
        self.add_node(node_id)
        return self.nodes[node_id].label

    def get_all_labels(self) -> Dict[str, NodeLabel]:
        """Get all node labels."""
        return {nid: node.label for nid, node in self.nodes.items()}

    def _has_valid_justification(self, node_id: str) -> bool:
        """Check if node has at least one justification with all antecedents IN."""
        node = self.nodes[node_id]
        for jid in node.justifications:
            just = self.justifications[jid]
            if all(self.nodes[ant].label == NodeLabel.IN for ant in just.antecedents):
                return True
        return False

    def _propagate_out(self, node_id: str, reason: str) -> Set[str]:
        """Propagate OUT label from a node to its dependents."""
        changed: Set[str] = set()
        queue = deque([node_id])

        while queue:
            current = queue.popleft()
            node = self.nodes[current]

            if node.label == NodeLabel.OUT:
                continue

            node.label = NodeLabel.OUT
            changed.add(current)

            # Find all justifications where current is an antecedent
            for jid, just in self.justifications.items():
                if current in just.antecedents:
                    cons = just.consequent
                    # If all antecedents of this justification are no longer IN,
                    # the justification is invalidated
                    if not all(self.nodes[ant].label == NodeLabel.IN for ant in just.antecedents):
                        # Check if consequent has any OTHER valid justification
                        if not self._has_valid_justification(cons):
                            if self.nodes[cons].label == NodeLabel.IN:
                                queue.append(cons)

        # After OUT propagation, check for odd cycles among OUT nodes
        self._detect_odd_cycles(changed)
        return changed

    def _propagate_in(self, node_id: str, _triggering_jids: Set[str]) -> Set[str]:
        """Propagate IN label from a node to its dependents."""
        changed: Set[str] = set()
        queue = deque([node_id])

        while queue:
            current = queue.popleft()
            node = self.nodes[current]

            if node.label == NodeLabel.IN:
                continue

            node.label = NodeLabel.IN
            changed.add(current)
            node.in_nogood = False  # Coming IN clears NOGOOD membership

            # Find all justifications where current is an antecedent
            for jid, just in self.justifications.items():
                if current in just.antecedents:
                    cons = just.consequent
                    # If this justification now has all antecedents IN, consequent becomes IN
                    if all(self.nodes[ant].label == NodeLabel.IN for ant in just.antecedents):
                        if self.nodes[cons].label == NodeLabel.OUT:
                            queue.append(cons)

        return changed

    def _detect_odd_cycles(self, out_nodes: Set[str]) -> None:
        """
        Detect odd cycles among OUT nodes (Doyle 1979, Section 4).
        An odd cycle in the justification graph among OUT nodes indicates
        a structural inconsistency — create a NOGOOD.
        """
        # Build justification graph among OUT nodes
        out_graph: Dict[str, Set[str]] = defaultdict(set)
        for jid, just in self.justifications.items():
            if just.consequent in out_nodes:
                for ant in just.antecedents:
                    if ant in out_nodes:
                        out_graph[ant].add(just.consequent)

        # DFS to find cycles
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in out_graph.get(node, ()):
                if neighbor not in visited:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found a cycle — extract it from path
                    idx = path.index(neighbor)
                    return path[idx:]

            rec_stack.remove(node)
            path.pop()
            return None

        for node in out_nodes:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    # Create NOGOOD from cycle nodes
                    nogood = set(cycle)
                    if nogood not in self.nogoods:
                        self.nogoods.append(nogood)
                    for n in nogood:
                        self.nodes[n].in_nogood = True