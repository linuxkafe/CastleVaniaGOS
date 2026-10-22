"""
Dung Abstract Argumentation Framework — grounded extension computation.

Implements the characteristic function and grounded extension (least fixed point)
for abstract argumentation frameworks per Dung 1995. No external dependencies.

Reference: Dung, P. M. (1995). "On the acceptability of arguments and its fundamental
role in nonmonotonic reasoning, logic programming and n-person games." 
Artificial Intelligence, 77(2), 321-357.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple, Iterable
from dataclasses import dataclass

from .epistemic_objects import Proposition, PropositionDependency, FalsificationCondition, RelationType, FalsificationStatus


@dataclass
class AbstractArgumentationFramework:
    """AAF = (Arguments, Attacks) where Attacks is a directed relation."""
    arguments: Set[str]
    attacks: Dict[str, Set[str]]  # attacker -> set of attacked

    def __post_init__(self):
        # Ensure all arguments have an entry in attacks (even if empty)
        for arg in self.arguments:
            self.attacks.setdefault(arg, set())


def build_attack_graph(
    arguments: Set[str],
    attack_edges: List[Tuple[str, str]]
) -> AbstractArgumentationFramework:
    """
    Build AAF from argument IDs and directed attack edges.
    
    Args:
        arguments: Set of all argument IDs
        attack_edges: List of (attacker, attacked) pairs
    """
    attacks: Dict[str, Set[str]] = defaultdict(set)
    for attacker, attacked in attack_edges:
        attacks[attacker].add(attacked)
    return AbstractArgumentationFramework(
        arguments=set(arguments),
        attacks=dict(attacks)
    )


def characteristic_function(
    S: Set[str],
    af: AbstractArgumentationFramework
) -> Set[str]:
    """
    Characteristic function F(S) = {a | a is defended by S}.
    
    An argument a is defended by S iff for every attacker b of a,
    there exists some c in S that attacks b.
    """
    # Build reverse attack map: attacked -> set of attackers
    attackers_of: Dict[str, Set[str]] = defaultdict(set)
    for attacker, attacked_set in af.attacks.items():
        for attacked in attacked_set:
            attackers_of[attacked].add(attacker)
    
    defended = set()
    all_args = af.arguments
    
    for a in all_args:
        # Find all attackers of a
        attackers_of_a = attackers_of.get(a, set())
        
        # a is defended if every attacker of a is attacked by some c in S
        is_defended = all(
            any(c in S for c in attackers_of.get(b, set()))
            for b in attackers_of_a
        )
        
        if is_defended:
            defended.add(a)
    
    return defended


def grounded_extension(
    af: AbstractArgumentationFramework
) -> Set[str]:
    """
    Compute the grounded extension (least fixed point of characteristic function).
    
    The grounded extension is the least fixed point of the characteristic function,
    computed by iteratively applying F starting from empty set.
    
    Returns the set of argument IDs in the grounded extension.
    """
    S: Set[str] = set()
    while True:
        new_S = characteristic_function(S, af)
        if new_S == S:
            return S
        S = new_S


def is_in_grounded(
    arg: str,
    af: AbstractArgumentationFramework
) -> bool:
    """Check if an argument is in the grounded extension."""
    return arg in grounded_extension(af)


def generate_attacks_from_epistemic(
    propositions: Iterable[Proposition],
    dependencies: Iterable[PropositionDependency],
    falsification_conditions: Iterable[FalsificationCondition]
) -> Dict[str, Set[str]]:
    """
    Generate ATTACKS edges from epistemic state.
    
    Derivation rule: A attacks B if:
    - A CONTRADICTS B (directed from the contradiction)
    - A's falsification condition is FAILED (A is false)
    - B's falsification condition is not FAILED (B is not false)
    
    This derives directed attacks from symmetric contradictions + epistemic status.
    
    Args:
        propositions: Iterable of Proposition objects
        dependencies: Iterable of PropositionDependency objects
        falsification_conditions: Iterable of FalsificationCondition objects
    
    Returns:
        Dict of attacker -> set of attacked
    """
    # Build falsification status lookup
    fc_status = {fc.proposition_id: fc.status for fc in falsification_conditions}
    
    # Build CONTRADICTS edges
    contradicts_edges = [
        (dep.from_proposition, dep.to_proposition)
        for dep in dependencies
        if dep.relation_type == RelationType.CONTRADICTS
    ]
    
    attacks: Dict[str, Set[str]] = defaultdict(set)
    for attacker, attacked in contradicts_edges:
        attacker_status = fc_status.get(attacker, "unknown")
        attacked_status = fc_status.get(attacked, "unknown")
        
        # Derive attack: attacker is false, attacked is not false
        if attacker_status == FalsificationStatus.FAILED and attacked_status != FalsificationStatus.FAILED:
            attacks[attacker].add(attacked)
    
    return dict(attacks)


def build_af_from_epistemic_state(
    propositions: Iterable[Proposition],
    dependencies: Iterable[PropositionDependency],
    falsification_conditions: Iterable[FalsificationCondition]
) -> AbstractArgumentationFramework:
    """
    Build AAF from current epistemic state.
    
    Arguments = all proposition IDs.
    Attacks = derived from CONTRADICTS + falsification status.
    """
    args = {p.id for p in propositions}
    attack_relations = generate_attacks_from_epistemic(
        propositions, dependencies, falsification_conditions
    )
    # Convert attack relations dict to edge list
    attack_edges = [(a, d) for a, attacked_set in attack_relations.items() for d in attacked_set]
    return build_attack_graph(args, attack_edges)