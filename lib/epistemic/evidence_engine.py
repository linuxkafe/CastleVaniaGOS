"""
Evidence Engine — computes epistemic quality dimensions.

Produces an evidence_score [0.0, 1.0] that incorporates:
1. Contradiction severity (weighted by source credibility ratio)
2. Temporal validity (configurable decay)
3. Source freshness factor
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .graph_store import KnowledgeGraphStore
from .gmif import GMIFLevel


@dataclass
class EvidenceScore:
    """Result of evidence scoring."""
    score: float  # 0.0 to 1.0
    level: GMIFLevel
    confidence: float
    factors: Dict[str, float]  # Individual scoring factors


class EvidenceEngine:
    """Computes epistemic evidence scores from graph data."""

    SCORE_THRESHOLDS = [
        (0.8, GMIFLevel.M7_FORMAL),
        (0.6, GMIFLevel.M6_VALIDATED),
        (0.5, GMIFLevel.M5_EVIDENCED),
        (0.4, GMIFLevel.M4_ATTRIBUTED),
        (0.3, GMIFLevel.M3_INFERRED),
        (0.2, GMIFLevel.M2_OBSERVATION),
    ]
    DEFAULT_LEVEL = GMIFLevel.M1_ASSERTION

    # Temporal decay settings
    TEMPORAL_THRESHOLD_DAYS = 365
    TEMPORAL_PENALTY = 0.3

    def __init__(self, store: Optional[KnowledgeGraphStore] = None):
        self.store = store

    def score_to_level(self, evidence_score: float) -> GMIFLevel:
        """Map a continuous evidence score to GMIFLevel."""
        for threshold, level in self.SCORE_THRESHOLDS:
            if evidence_score >= threshold:
                return level
        return self.DEFAULT_LEVEL

    def score_to_confidence(self, evidence_score: float, level: GMIFLevel) -> float:
        """Derive confidence from how close the score is to the level's range."""
        # Simple confidence based on distance from threshold
        for threshold, l in self.SCORE_THRESHOLDS:
            if l == level:
                distance = abs(evidence_score - threshold)
                return max(0.0, 1.0 - distance)
        return 0.5

    def compute(
        self,
        node_id: str,
        frontmatter: Optional[Dict] = None,
        source_timestamp: Optional[datetime] = None,
    ) -> EvidenceScore:
        """Compute evidence score for a node."""
        factors: Dict[str, float] = {}

        # Base score from metadata
        base_score = self._base_score(frontmatter or {})
        factors["base"] = base_score

        # Contradiction penalty
        contradiction_penalty = self._contradiction_severity(node_id)
        factors["contradiction"] = -contradiction_penalty

        # Temporal factor
        temporal_factor = self._temporal_factor(source_timestamp)
        factors["temporal"] = temporal_factor

        # Source credibility
        source_credibility = self._source_credibility(frontmatter or {})
        factors["source_credibility"] = source_credibility

        # Combine factors
        score = base_score - contradiction_penalty
        score *= temporal_factor
        score *= source_credibility
        score = max(0.0, min(1.0, score))

        level = self.score_to_level(score)
        confidence = self.score_to_confidence(score, level)

        return EvidenceScore(
            score=round(score, 4),
            level=level,
            confidence=round(confidence, 4),
            factors=factors,
        )

    def _base_score(self, frontmatter: Dict) -> float:
        """Compute base score from frontmatter metadata."""
        score = 0.3  # Default base

        # Boost for sources
        sources = frontmatter.get("sources", [])
        if sources:
            score += 0.2 * min(len(sources) / 3, 1.0)

        # Boost for verification
        verified = frontmatter.get("verified", [])
        if verified:
            score += 0.3

        # Boost for evidence keywords
        text = str(frontmatter).lower()
        if "evidence" in text or "data" in text:
            score += 0.1
        if "validated" in text or "confirmed" in text:
            score += 0.1

        return min(1.0, score)

    def _contradiction_severity(self, node_id: str) -> float:
        """Compute contradiction penalty from incoming contradict edges.

        Returns 0.0 if no contradictions, otherwise a penalty in [0.0, 0.5]
        proportional to the number of contradicting edges.
        """
        if not self.store:
            return 0.0

        in_edges = self.store.get_edges_to(node_id)
        contradict_count = sum(
            1 for e in in_edges
            if e.relation in ("contradicts", "refutes", "disproves")
        )

        if contradict_count == 0:
            return 0.0

        # Each contradiction adds 0.15 penalty, capped at 0.5
        return min(0.5, contradict_count * 0.15)

    def _temporal_factor(self, source_timestamp: Optional[datetime]) -> float:
        """Apply temporal decay based on source age."""
        if source_timestamp is None:
            return 1.0

        age_days = (datetime.now(timezone.utc) - source_timestamp).days

        if age_days <= self.TEMPORAL_THRESHOLD_DAYS:
            return 1.0

        excess = age_days - self.TEMPORAL_THRESHOLD_DAYS
        decay_window = self.TEMPORAL_THRESHOLD_DAYS
        factor = 1.0 - self.TEMPORAL_PENALTY * min(excess / max(decay_window, 1), 1.0)
        return max(factor, 1.0 - self.TEMPORAL_PENALTY)

    def _source_credibility(self, frontmatter: Dict) -> float:
        """Compute source credibility from metadata."""
        credibility = 0.5  # Default

        # Check for trusted sources
        sources = frontmatter.get("sources", [])
        for source in sources:
            resource = source.get("resource", "")
            if "docs/" in resource or "reference" in resource:
                credibility += 0.2
            if source.get("usage_count", 0) > 5:
                credibility += 0.1

        # Check for verification
        verified = frontmatter.get("verified", [])
        if verified:
            credibility += 0.2

        return min(1.0, credibility)
