"""
GMIF (Graded Model of Information Fidelity) M1–M7 classification.

SOURCE: Ported from gepeto-s-notebook (GMIF M1–M7 epistemic classification).

M1: ASSERTION — claim stated without evidence or support
M2: OBSERVATION — claim based on direct observation
M3: INFERRED — claim derived from other claims via reasoning
M4: ATTRIBUTED — claim attributed to a named source
M5: EVIDENCED — claim with supporting evidence (references, data)
M6: VALIDATED — cross-validated claim (multiple independent sources)
M7: FORMAL — claim with formal falsification conditions
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class GMIFLevel(str, Enum):
    M1_ASSERTION = "M1"
    M2_OBSERVATION = "M2"
    M3_INFERRED = "M3"
    M4_ATTRIBUTED = "M4"
    M5_EVIDENCED = "M5"
    M6_VALIDATED = "M6"
    M7_FORMAL = "M7"

    def __str__(self) -> str:
        return self.value

    @property
    def numeric(self) -> int:
        return int(self.value[1])

    @property
    def label(self) -> str:
        return {
            "M1": "Assertion",
            "M2": "Observation",
            "M3": "Inferred",
            "M4": "Attributed",
            "M5": "Evidenced",
            "M6": "Validated",
            "M7": "Formal",
        }[self.value]

    @property
    def description(self) -> str:
        return {
            "M1": "Claim stated without evidence or support",
            "M2": "Claim based on direct observation",
            "M3": "Claim derived from other claims via reasoning",
            "M4": "Claim attributed to a named source",
            "M5": "Claim with supporting evidence (references, data)",
            "M6": "Cross-validated claim (multiple independent sources)",
            "M7": "Claim with formal falsification conditions",
        }[self.value]


ALL_GMIF_LEVELS: List[GMIFLevel] = list(GMIFLevel)


def parse_gmif(value: str) -> Optional[GMIFLevel]:
    normalized = value.strip().upper()
    for level in GMIFLevel:
        if level.value == normalized:
            return level
    return None


def min_required_role(gmif: GMIFLevel) -> str:
    role_map = {
        GMIFLevel.M1_ASSERTION: "foundational",
        GMIFLevel.M2_OBSERVATION: "foundational",
        GMIFLevel.M3_INFERRED: "derived",
        GMIFLevel.M4_ATTRIBUTED: "derived",
        GMIFLevel.M5_EVIDENCED: "derived",
        GMIFLevel.M6_VALIDATED: "derived",
        GMIFLevel.M7_FORMAL: "derived",
    }
    return role_map[gmif]


def supports_falsification(gmif: GMIFLevel) -> bool:
    return gmif == GMIFLevel.M7_FORMAL


def supports_evidence(gmif: GMIFLevel) -> bool:
    return gmif.numeric >= 5


def requires_source(gmif: GMIFLevel) -> bool:
    return gmif.numeric >= 4


@dataclass
class GMIFValidation:
    level: GMIFLevel
    valid: bool
    reason: Optional[str] = None

    @staticmethod
    def ok(level: GMIFLevel) -> "GMIFValidation":
        return GMIFValidation(level=level, valid=True)

    @staticmethod
    def fail(level: GMIFLevel, reason: str) -> "GMIFValidation":
        return GMIFValidation(level=level, valid=False, reason=reason)


def validate_proposition(
    gmif: GMIFLevel,
    role: str,
    has_supporting_claims: bool,
    has_falsification: bool,
    has_evidence: bool,
    has_source: bool,
) -> GMIFValidation:
    errors: List[str] = []

    if gmif == GMIFLevel.M1_ASSERTION:
        if role not in ("foundational", "assumption"):
            errors.append(f"M1 requires role foundational/assumption, got {role}")

    elif gmif == GMIFLevel.M2_OBSERVATION:
        if role not in ("foundational", "assumption"):
            errors.append(f"M2 requires role foundational/assumption, got {role}")

    elif gmif == GMIFLevel.M3_INFERRED:
        if role != "derived":
            errors.append("M3 requires role derived")
        if not has_supporting_claims:
            errors.append("M3 requires supporting claims")

    elif gmif == GMIFLevel.M4_ATTRIBUTED:
        if role != "derived":
            errors.append("M4 requires role derived")
        if not has_source:
            errors.append("M4 requires a named source")
        if not has_supporting_claims:
            errors.append("M4 requires supporting claims")

    elif gmif == GMIFLevel.M5_EVIDENCED:
        if role != "derived":
            errors.append("M5 requires role derived")
        if not has_supporting_claims:
            errors.append("M5 requires supporting claims")
        if not has_source:
            errors.append("M5 requires a named source")
        if not has_evidence:
            errors.append("M5 requires supporting evidence")

    elif gmif == GMIFLevel.M6_VALIDATED:
        if role != "derived":
            errors.append("M6 requires role derived")
        if not has_supporting_claims:
            errors.append("M6 requires supporting claims")
        if not has_source:
            errors.append("M6 requires a named source")
        if not has_evidence:
            errors.append("M6 requires supporting evidence")

    elif gmif == GMIFLevel.M7_FORMAL:
        if role != "derived":
            errors.append("M7 requires role derived")
        if not has_supporting_claims:
            errors.append("M7 requires supporting claims")
        if not has_source:
            errors.append("M7 requires a named source")
        if not has_evidence:
            errors.append("M7 requires supporting evidence")
        if not has_falsification:
            errors.append("M7 requires falsification conditions")

    if errors:
        return GMIFValidation.fail(gmif, "; ".join(errors))
    return GMIFValidation.ok(gmif)
