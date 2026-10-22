"""Unit tests for scoring module (T038).

Covers: activation monotonicity, pinned floor, centrality contribution,
access log parsing, composite score.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from lib.memory.scoring import (
    CONFIG,
    compute_activation,
    compute_centrality,
    composite_score,
    parse_access_log,
    compute_scores,
)


class TestActivation:
    def test_no_accesses_returns_default(self):
        assert compute_activation([]) == CONFIG["default_activation"]

    def test_single_recent_access_positive(self):
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        act = compute_activation([ts], current_time=now)
        assert act > 0

    def test_monotone_in_frequency(self):
        now = datetime.now(timezone.utc)
        one = compute_activation([now.isoformat()], current_time=now)
        many = compute_activation([now.isoformat()] * 5, current_time=now)
        assert many > one

    def test_monotone_in_recency(self):
        now = datetime.now(timezone.utc)
        old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        recent_ts = now.isoformat()
        old = compute_activation([old_ts], current_time=now)
        recent = compute_activation([recent_ts], current_time=now)
        assert recent > old

    def test_future_timestamp_clamped(self):
        now = datetime.now(timezone.utc)
        future = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()
        act = compute_activation([future], current_time=now)
        assert act > 0

    def test_mixed_accesses(self):
        now = datetime.now(timezone.utc)
        ts_list = [
            datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
            datetime(2025, 6, 1, tzinfo=timezone.utc).isoformat(),
            now.isoformat(),
        ]
        act = compute_activation(ts_list, current_time=now)
        assert act > 0

    def test_invalid_timestamp_skipped(self):
        act = compute_activation(["not-a-date", "also-bad"], current_time=datetime.now(timezone.utc))
        assert act == CONFIG["default_activation"]


class TestCentrality:
    def test_no_deps_returns_zero(self):
        assert compute_centrality("SD-001") == 0.0

    def test_deps_contribute(self):
        deps = {"SD-001": ["P1", "P2", "P3"]}
        assert compute_centrality("SD-001", deps) == 3.0

    def test_other_docs_unaffected(self):
        deps = {"SD-001": ["P1"], "SD-002": ["P2", "P3"]}
        assert compute_centrality("SD-003", deps) == 0.0


class TestCompositeScore:
    def test_default_weights_pinned(self):
        score = composite_score(0.5, True, 0.3)
        expected = 0.5 * 0.5 + 0.3 * 1.0 + 0.2 * 0.3
        assert score == pytest.approx(expected)

    def test_default_weights_unpinned(self):
        score = composite_score(0.5, False, 0.3)
        expected = 0.5 * 0.5 + 0.2 * 0.3
        assert score == pytest.approx(expected)

    def test_higher_activation_wins(self):
        low = composite_score(0.1, False, 0.0)
        high = composite_score(1.0, False, 0.0)
        assert high > low

    def test_pinned_never_demotes(self):
        unpinned = composite_score(0.0, False, 0.0)
        pinned = composite_score(0.0, True, 0.0)
        assert pinned >= unpinned

    def test_centrality_contributes(self):
        low = composite_score(0.0, False, 0.0)
        high = composite_score(0.0, False, 5.0)
        assert high >= low


class TestAccessLog:
    def test_missing_log(self, tmp_path):
        log = tmp_path / "nonexistent.log"
        assert parse_access_log(log) == {}

    def test_empty_log(self, tmp_path):
        log = tmp_path / "access.log"
        log.write_text("")
        assert parse_access_log(log) == {}

    def test_parses_lines(self, tmp_path):
        log = tmp_path / "access.log"
        log.write_text("2026-07-05T10:00:00 SD-001 T038\n2026-07-05T11:00:00 SD-002 T039\n")
        parsed = parse_access_log(log)
        assert len(parsed["SD-001"]) == 1
        assert len(parsed["SD-002"]) == 1

    def test_skips_comments(self, tmp_path):
        log = tmp_path / "access.log"
        log.write_text("# comment\n2026-07-05T10:00:00 SD-001\n")
        parsed = parse_access_log(log)
        assert "SD-001" in parsed

    def test_multiple_accesses_same_doc(self, tmp_path):
        log = tmp_path / "access.log"
        log.write_text("2026-07-05T10:00:00 SD-001\n2026-07-06T10:00:00 SD-001\n")
        parsed = parse_access_log(log)
        assert len(parsed["SD-001"]) == 2

    def test_skip_short_lines(self, tmp_path):
        log = tmp_path / "access.log"
        log.write_text("SD-001\n")
        parsed = parse_access_log(log)
        assert not parsed


class TestComputeScores:
    def test_no_shadow_dir_returns_empty(self, tmp_path):
        scores = compute_scores(tmp_path / "empty", tmp_path / "access.log")
        assert scores == {}

    def test_computes_from_real_files(self, tmp_path, monkeypatch):
        shadow_dir = tmp_path / "shadow"
        shadow_dir.mkdir()
        sd = shadow_dir / "SD-001-test.md"
        sd.write_text(
            "---\n"
            'id: SD-001\n'
            'title: "Test"\n'
            'synthesis: "test"\n'
            "pointer:\n"
            '  path: /dev/null\n'
            '  content_hash: "abc"\n'
            'epistemic_state: SUPORTADA\n'
            "score:\n"
            "  activation: 0.0\n"
            "  pinned: true\n"
            "  centrality: 0.0\n"
            "provenance:\n"
            '  generated_by: "test"\n'
            '  generated_at: "2026-07-05"\n'
            '  source_ticket: T038\n'
            '  source_conversation: ""\n'
            'created: "2026-07-05"\n'
            'last_accessed: "2026-07-05"\n'
            "---\n"
            "# Test\n"
        )
        log = tmp_path / "access.log"
        log.write_text("2026-07-05T10:00:00 SD-001 T038\n")

        scores = compute_scores(shadow_dir, log)
        assert "SD-001" in scores
        assert scores["SD-001"] > 0
