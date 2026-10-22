import pytest

from lib.epistemic.gmif import (
    GMIFLevel,
    parse_gmif,
    min_required_role,
    supports_falsification,
    supports_evidence,
    requires_source,
    validate_proposition,
    ALL_GMIF_LEVELS,
)


class TestGMIFLevel:
    def test_numeric(self):
        assert GMIFLevel.M1_ASSERTION.numeric == 1
        assert GMIFLevel.M3_INFERRED.numeric == 3
        assert GMIFLevel.M7_FORMAL.numeric == 7

    def test_label(self):
        assert GMIFLevel.M1_ASSERTION.label == "Assertion"
        assert GMIFLevel.M7_FORMAL.label == "Formal"

    def test_description(self):
        assert "evidence" in GMIFLevel.M5_EVIDENCED.description.lower()
        assert "falsification" in GMIFLevel.M7_FORMAL.description.lower()

    def test_str(self):
        assert str(GMIFLevel.M6_VALIDATED) == "M6"

    def test_all_levels_present(self):
        assert len(ALL_GMIF_LEVELS) == 7
        names = [lvl.name for lvl in ALL_GMIF_LEVELS]
        for i in range(1, 8):
            assert any(f"M{i}" in name for name in names)


class TestParseGMIF:
    def test_valid(self):
        assert parse_gmif("M1") == GMIFLevel.M1_ASSERTION
        assert parse_gmif("m6") == GMIFLevel.M6_VALIDATED
        assert parse_gmif(" M7 ") == GMIFLevel.M7_FORMAL

    def test_invalid(self):
        assert parse_gmif("M0") is None
        assert parse_gmif("M8") is None
        assert parse_gmif("foo") is None
        assert parse_gmif("") is None


class TestHelpers:
    def test_min_required_role(self):
        assert min_required_role(GMIFLevel.M1_ASSERTION) == "foundational"
        assert min_required_role(GMIFLevel.M3_INFERRED) == "derived"
        assert min_required_role(GMIFLevel.M7_FORMAL) == "derived"

    def test_supports_falsification(self):
        assert supports_falsification(GMIFLevel.M7_FORMAL)
        assert not supports_falsification(GMIFLevel.M1_ASSERTION)
        assert not supports_falsification(GMIFLevel.M6_VALIDATED)

    def test_supports_evidence(self):
        assert supports_evidence(GMIFLevel.M5_EVIDENCED)
        assert supports_evidence(GMIFLevel.M7_FORMAL)
        assert not supports_evidence(GMIFLevel.M1_ASSERTION)
        assert not supports_evidence(GMIFLevel.M4_ATTRIBUTED)

    def test_requires_source(self):
        assert requires_source(GMIFLevel.M4_ATTRIBUTED)
        assert requires_source(GMIFLevel.M7_FORMAL)
        assert not requires_source(GMIFLevel.M1_ASSERTION)
        assert not requires_source(GMIFLevel.M3_INFERRED)


class TestValidateProposition:
    def test_m1_ok(self):
        result = validate_proposition(
            GMIFLevel.M1_ASSERTION, "foundational", False, False, False, False
        )
        assert result.valid

    def test_m1_wrong_role(self):
        result = validate_proposition(
            GMIFLevel.M1_ASSERTION, "derived", False, False, False, False
        )
        assert not result.valid
        assert "role" in result.reason

    def test_m3_ok(self):
        result = validate_proposition(
            GMIFLevel.M3_INFERRED, "derived", True, False, False, False
        )
        assert result.valid

    def test_m3_missing_support(self):
        result = validate_proposition(
            GMIFLevel.M3_INFERRED, "derived", False, False, False, False
        )
        assert not result.valid
        assert "supporting claims" in result.reason

    def test_m4_requires_source(self):
        result = validate_proposition(
            GMIFLevel.M4_ATTRIBUTED, "derived", True, False, False, False
        )
        assert not result.valid
        assert "source" in result.reason

    def test_m4_ok(self):
        result = validate_proposition(
            GMIFLevel.M4_ATTRIBUTED, "derived", True, False, False, True
        )
        assert result.valid

    def test_m5_requires_evidence(self):
        result = validate_proposition(
            GMIFLevel.M5_EVIDENCED, "derived", True, False, False, True
        )
        assert not result.valid
        assert "evidence" in result.reason

    def test_m5_ok(self):
        result = validate_proposition(
            GMIFLevel.M5_EVIDENCED, "derived", True, False, True, True
        )
        assert result.valid

    def test_m6_ok(self):
        result = validate_proposition(
            GMIFLevel.M6_VALIDATED, "derived", True, False, True, True
        )
        assert result.valid

    def test_m7_requires_falsification(self):
        result = validate_proposition(
            GMIFLevel.M7_FORMAL, "derived", True, False, True, True
        )
        assert not result.valid
        assert "falsification" in result.reason

    def test_m7_ok(self):
        result = validate_proposition(
            GMIFLevel.M7_FORMAL, "derived", True, True, True, True
        )
        assert result.valid

    def test_m2_foundational_ok(self):
        result = validate_proposition(
            GMIFLevel.M2_OBSERVATION, "foundational", False, False, False, False
        )
        assert result.valid

    def test_m2_wrong_role(self):
        result = validate_proposition(
            GMIFLevel.M2_OBSERVATION, "derived", False, False, False, False
        )
        assert not result.valid

    def test_m3_wrong_role(self):
        result = validate_proposition(
            GMIFLevel.M3_INFERRED, "foundational", True, False, False, False
        )
        assert not result.valid
