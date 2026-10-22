"""
GMIF Classifier with keyword heuristics and confidence scoring.

Classifies claims into GMIF levels (M1-M7) based on:
- Keyword presence in claim text
- Metadata signals (sources, evidence, verification)
- Confidence scoring based on signal strength
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .gmif import GMIFLevel


@dataclass
class ClassificationResult:
    """Result of GMIF classification."""
    level: GMIFLevel
    confidence: float  # 0.0 to 1.0
    signals: List[str]  # What contributed to the classification
    alternative_levels: List[Tuple[GMIFLevel, float]]  # Other possible levels with scores


# Keywords that suggest each GMIF level
LEVEL_KEYWORDS: Dict[GMIFLevel, List[str]] = {
    GMIFLevel.M1_ASSERTION: [
        "i think", "i believe", "maybe", "probably", "might be",
        "it seems", "likely", "possibly", "could be", "should be",
        "in my opinion", "i assume", "presumably", "apparently",
    ],
    GMIFLevel.M2_OBSERVATION: [
        "i see", "i noticed", "observed", "measured", "recorded",
        "found that", "data shows", "results indicate", "the log shows",
        "we saw", "appears", "looks like", "seems to be",
    ],
    GMIFLevel.M3_INFERRED: [
        "therefore", "thus", "hence", "implies", "suggests",
        "we can infer", "it follows", "reasoning suggests", "logically",
        "consequently", "as a result", "this means", "indicates that",
    ],
    GMIFLevel.M4_ATTRIBUTED: [
        "according to", "cited by", "as stated in", "per the documentation",
        "the paper says", "author states", "source reports", "reference",
        "documentation says", "specification requires", "standard defines",
    ],
    GMIFLevel.M5_EVIDENCED: [
        "evidence shows", "supported by", "backed by", "data confirms",
        "test results", "validated by", "measurements show", "benchmarks",
        "test shows", "tests show", "coverage", "benchmarked", "profiling",
        "experiment", "empirical", "demonstrated", "proven",
    ],
    GMIFLevel.M6_VALIDATED: [
        "cross-validated", "independently confirmed", "multiple sources",
        "replicated", "consensus", "peer-reviewed", "independent verification",
        "audited", "certified", "validated independently",
    ],
    GMIFLevel.M7_FORMAL: [
        "falsifiable", "falsification condition", "testable prediction",
        "can be disproven", "formal specification", "mathematical proof",
        "invariant", "postcondition", "precondition",
        "formal proof", "formally verified", "theorem", "lemma",
        "axiom", "specification", "contract",
    ],
}


def classify_by_keywords(text: str) -> Dict[GMIFLevel, float]:
    """Score text against keyword patterns for each GMIF level.
    
    Uses token overlap and regex word-boundary matching for robustness
    against phrase variations (e.g., "test shows coverage" matches "test results").
    """
    import re
    text_lower = text.lower()
    # Tokenize for overlap matching
    tokens = set(re.findall(r'\b\w+\b', text_lower))
    
    scores: Dict[GMIFLevel, float] = {}
    
    for level, keywords in LEVEL_KEYWORDS.items():
        match_score = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            # Try exact phrase match first
            if kw_lower in text_lower:
                match_score += 1.0
            else:
                # Try token overlap: split keyword into tokens, check overlap
                kw_tokens = set(re.findall(r'\b\w+\b', kw_lower))
                if kw_tokens:
                    overlap = len(tokens & kw_tokens) / len(kw_tokens)
                    if overlap > 0.5:  # At least half the keyword tokens present
                        match_score += overlap * 0.5  # Partial credit
        
        # Normalize by number of keywords
        scores[level] = match_score / len(keywords) if keywords else 0.0
    
    return scores


def classify_by_metadata(frontmatter: Dict) -> Dict[GMIFLevel, float]:
    """Score metadata signals for GMIF level."""
    scores: Dict[GMIFLevel, float] = {level: 0.0 for level in GMIFLevel}

    # Check for sources - number of sources matters
    sources = frontmatter.get("sources", [])
    if sources:
        src_count = len(sources)
        # More sources = higher confidence, but cap at 0.6
        scores[GMIFLevel.M4_ATTRIBUTED] += min(0.6, src_count * 0.2)
        scores[GMIFLevel.M5_EVIDENCED] += min(0.4, src_count * 0.1)

    # Check for verification
    verified = frontmatter.get("verified", [])
    if verified:
        ver_count = len(verified)
        scores[GMIFLevel.M5_EVIDENCED] += min(0.5, ver_count * 0.2)
        scores[GMIFLevel.M6_VALIDATED] += min(0.6, ver_count * 0.2)

    # Check for falsification conditions
    if "falsification" in str(frontmatter).lower():
        scores[GMIFLevel.M7_FORMAL] += 0.5

    # Check for evidence keywords in frontmatter
    if "evidence" in str(frontmatter).lower():
        scores[GMIFLevel.M5_EVIDENCED] += 0.2

    # Check for gmif field (explicit claim)
    gmif_field = frontmatter.get("gmif", "")
    if gmif_field:
        try:
            from .gmif import parse_gmif
            claimed = parse_gmif(gmif_field)
            if claimed:
                scores[claimed] += 0.5  # Strong signal for claimed level
        except Exception:
            pass

    # Don't normalize to max - keep absolute scores for meaningful combination
    # Cap all scores at 1.0
    for level in scores:
        scores[level] = min(1.0, scores[level])

    return scores


def classify_claim(
    text: str,
    frontmatter: Optional[Dict] = None,
    claimed_level: Optional[GMIFLevel] = None,
) -> ClassificationResult:
    """Classify a claim into GMIF level with confidence scoring.

    Args:
        text: The claim text to classify
        frontmatter: Optional metadata from the source document
        claimed_level: Optional pre-claimed GMIF level to validate

    Returns:
        ClassificationResult with level, confidence, and signals
    """
    signals: List[str] = []

    # Keyword-based scoring
    keyword_scores = classify_by_keywords(text)
    signals.append(f"keyword_scores: {keyword_scores}")

    # Metadata-based scoring
    metadata_scores = classify_by_metadata(frontmatter or {})
    signals.append(f"metadata_scores: {metadata_scores}")

    # Combined scoring (60% keywords, 40% metadata)
    combined_scores: Dict[GMIFLevel, float] = {}
    for level in GMIFLevel:
        kw = keyword_scores.get(level, 0.0)
        md = metadata_scores.get(level, 0.0)
        # Boost keyword scores - a single strong keyword match is significant
        kw_boosted = min(1.0, kw * 5.0)  # 5x boost for keyword matches (was 3x)
        combined_scores[level] = 0.6 * kw_boosted + 0.4 * md

    # Find the best level
    best_level = max(combined_scores, key=lambda l: combined_scores[l])
    best_score = combined_scores[best_level]

    # If claimed level is provided, boost it
    if claimed_level:
        boost = 0.3
        combined_scores[claimed_level] = min(1.0, combined_scores[claimed_level] + boost)
        if combined_scores[claimed_level] > best_score:
            best_level = claimed_level
            best_score = combined_scores[claimed_level]
            signals.append(f"claimed_level_boost: {claimed_level}")

    # Calculate confidence
    # Confidence is based on the gap between best and second-best
    sorted_scores = sorted(combined_scores.values(), reverse=True)
    if len(sorted_scores) >= 2:
        gap = sorted_scores[0] - sorted_scores[1]
        confidence = min(1.0, best_score + gap * 0.5)
    else:
        confidence = best_score

    # Build alternative levels
    alternatives = [
        (level, score)
        for level, score in sorted(combined_scores.items(), key=lambda x: -x[1])
        if level != best_level and score > 0.1
    ]

    return ClassificationResult(
        level=best_level,
        confidence=round(confidence, 3),
        signals=signals,
        alternative_levels=alternatives[:3],  # Top 3 alternatives
    )
