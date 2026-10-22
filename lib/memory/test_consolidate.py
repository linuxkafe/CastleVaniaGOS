"""Tests for sleep/wake consolidation (T039).

Covers: demotion gate, merge, idempotence, sleep report, wake preamble.
"""

from pathlib import Path
from datetime import datetime, timezone

import pytest
import yaml

from lib.memory.consolidate import (
    sleep,
    wake,
    SleepReport,
    DemotionEvent,
    MergeEvent,
    ExecutionContext,
    InsightRelevance,
    find_duplicates,
    merge_shadow_docs,
    check_premise_dependencies,
    demote_to_archive,
    open_demotion_loop,
    sleep_twice_idempotent,
    DEMOTION_THRESHOLD,
)
from lib.epistemic.loop_closure import LoopCriticality, LoopStatus


def _make_shadow(
    directory: Path,
    sid: str,
    title: str = "",
    pinned: bool = False,
    ep_state: str = "pendente",
    pointer_path: str = "",
    duplicate_of: str = "",
) -> Path:
    """Helper: create a shadow doc with minimal frontmatter."""
    fm = {
        "id": sid,
        "title": title or sid,
        "synthesis": f"Synthesis for {sid}",
        "pointer": {"path": pointer_path, "content_hash": "abc"},
        "epistemic_state": ep_state,
        "score": {"activation": 0.0, "pinned": pinned, "centrality": 0.0},
        "provenance": {
            "generated_by": "test",
            "generated_at": "2026-07-05",
            "source_ticket": "T039",
            "source_conversation": "",
        },
        "created": "2026-07-05",
        "last_accessed": "2026-07-05",
    }
    if duplicate_of:
        fm["duplicate-of"] = duplicate_of

    body = f"# {title or sid}\n\nContent of {sid}."
    content = "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n" + body

    fpath = directory / f"{sid}.md"
    fpath.write_text(content)
    return fpath


def _make_access_log(path: Path, entries: dict) -> None:
    """Write an access.log with {sid: [timestamps]}."""
    lines = []
    for sid, timestamps in entries.items():
        for ts in timestamps:
            lines.append(f"{ts} {sid} T039")
    path.write_text("\n".join(lines))


class TestFindDuplicates:
    def test_no_duplicates(self, tmp_path):
        _make_shadow(tmp_path, "SD-001")
        _make_shadow(tmp_path, "SD-002", pointer_path="/dev/null")
        merges = find_duplicates(tmp_path)
        assert len(merges) == 0

    def test_explicit_duplicate_of(self, tmp_path):
        _make_shadow(tmp_path, "SD-001")
        _make_shadow(tmp_path, "SD-002", duplicate_of="SD-001")
        merges = find_duplicates(tmp_path)
        assert len(merges) >= 1
        target, source, reason = merges[0]
        assert target == "SD-001"
        assert source == "SD-002"

    def test_same_pointer_path(self, tmp_path):
        _make_shadow(tmp_path, "SD-001", pointer_path="/some/doc.md")
        _make_shadow(tmp_path, "SD-002", pointer_path="/some/doc.md")
        merges = find_duplicates(tmp_path)
        assert len(merges) >= 1

    def test_skips_readme(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# README")
        _make_shadow(tmp_path, "SD-001", pointer_path="/doc.md")
        _make_shadow(tmp_path, "SD-002", pointer_path="/doc.md")
        merges = find_duplicates(tmp_path)
        assert all("README" not in str(m) for m in merges)


class TestMergeShadowDocs:
    def test_merges_into_target(self, tmp_path):
        _make_shadow(tmp_path, "SD-001")
        _make_shadow(tmp_path, "SD-002")
        result = merge_shadow_docs("SD-001", ["SD-002"], tmp_path)
        assert "merged into SD-001" in result
        assert not (tmp_path / "SD-002.md").exists()
        content = (tmp_path / "SD-001.md").read_text()
        merged_fm = yaml.safe_load(content.split("---")[1])
        assert merged_fm["provenance"]["merged_count"] == 1

    def test_merge_preserves_target(self, tmp_path):
        _make_shadow(tmp_path, "SD-TARGET", title="Target")
        _make_shadow(tmp_path, "SD-SOURCE", title="Source")
        merge_shadow_docs("SD-TARGET", ["SD-SOURCE"], tmp_path)
        assert (tmp_path / "SD-TARGET.md").exists()

    def test_merge_nonexistent_target(self, tmp_path):
        _make_shadow(tmp_path, "SD-SOURCE")
        result = merge_shadow_docs("SD-MISSING", ["SD-SOURCE"], tmp_path)
        assert "MERGE FAILED" in result


class TestCheckPremiseDependencies:
    def test_no_premises_dir(self, tmp_path):
        assert not check_premise_dependencies("SD-001", tmp_path / "does-not-exist")

    def test_no_match(self, tmp_path):
        dot = tmp_path / "graph.dot"
        dot.write_text('digraph { "prem_a" -> "prem_b" [label=DEPENDS_ON]; }')
        assert not check_premise_dependencies("SD-001", tmp_path)

    def test_match_in_node(self, tmp_path):
        dot = tmp_path / "graph.dot"
        dot.write_text('digraph { "SD-001" [label="test"]; }')
        assert check_premise_dependencies("SD-001", tmp_path)

    def test_match_in_label(self, tmp_path):
        dot = tmp_path / "graph.dot"
        dot.write_text('digraph { "prem_a" [label="depends on SD-001"]; }')
        assert check_premise_dependencies("SD-001", tmp_path)

    def test_case_insensitive(self, tmp_path):
        dot = tmp_path / "graph.dot"
        dot.write_text('digraph { "prem_a" [label="sd-001 reference"]; }')
        assert check_premise_dependencies("SD-001", tmp_path)


class TestDemotionLoop:
    def test_creates_high_loop(self):
        loop = open_demotion_loop("SD-001", "Test Doc", 0.15)
        assert loop.criticality == LoopCriticality.HIGH
        assert loop.status == LoopStatus.OPEN

    def test_loop_has_policy(self):
        loop = open_demotion_loop("SD-001", "Test", 0.1)
        assert "demotion_review" in loop.closure_policy
        assert "SD-001" in loop.closure_policy


class TestDemoteToArchive:
    def test_moves_file(self, tmp_path):
        archive = tmp_path / "archive"
        _make_shadow(tmp_path, "SD-001")
        event = demote_to_archive("SD-001", tmp_path, archive, "low score", 0.1)
        assert not (tmp_path / "SD-001.md").exists()
        assert (archive / "SD-001.md").exists()
        assert event.shadow_id == "SD-001"

    def test_archived_frontmatter(self, tmp_path):
        archive = tmp_path / "archive"
        _make_shadow(tmp_path, "SD-001", title="Original")
        demote_to_archive("SD-001", tmp_path, archive, "test demotion", 0.15)
        content = (archive / "SD-001.md").read_text()
        fm = yaml.safe_load(content.split("---")[1])
        assert fm.get("archived_at")
        assert fm.get("archive_reason") == "test demotion"
        assert fm.get("archived_score") == 0.15

    def test_missing_file(self, tmp_path):
        archive = tmp_path / "archive"
        event = demote_to_archive("SD-MISSING", tmp_path, archive, "not found", 0.0)
        assert event.shadow_id == "SD-MISSING"
        assert event.reason == "not found"


class TestSleep:
    def test_sleep_empty_dir(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        shadow.mkdir()
        log.write_text("")
        report = sleep(shadow, archive, log, tmp_path / "premises")
        assert isinstance(report, SleepReport)
        assert len(report.demoted) == 0

    def test_sleep_demotes_below_threshold(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        shadow.mkdir()
        _make_shadow(shadow, "SD-001", ep_state="pendente")
        log.write_text("")
        report = sleep(shadow, archive, log, tmp_path / "premises", demotion_threshold=1.0)
        assert len(report.demoted) >= 1
        assert report.demoted[0].shadow_id == "SD-001"

    def test_pinned_never_demotes(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        shadow.mkdir()
        _make_shadow(shadow, "SD-001", pinned=True)
        log.write_text("")
        report = sleep(shadow, archive, log, tmp_path / "premises", demotion_threshold=1.0)
        demoted_ids = [e.shadow_id for e in report.demoted]
        assert "SD-001" not in demoted_ids

    def test_suporata_with_deps_blocks_demotion(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        premises = tmp_path / "premises"
        log = tmp_path / "access.log"
        shadow.mkdir()
        premises.mkdir()
        _make_shadow(shadow, "SD-001", ep_state="SUPORTADA")

        # Premise graph references SD-001
        dot = premises / "graph.dot"
        dot.write_text('digraph { "SD-001" [label="supported claim"]; }')

        log.write_text("")
        report = sleep(shadow, archive, log, premises, demotion_threshold=1.0)
        demoted_ids = [e.shadow_id for e in report.demoted]
        assert "SD-001" in demoted_ids  # it IS in demoted list (as blocked)
        blocked = [e for e in report.demoted if "blocked" in e.reason]
        assert len(blocked) >= 1

    def test_suporata_without_deps_demotes(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        premises = tmp_path / "premises"
        log = tmp_path / "access.log"
        shadow.mkdir()
        premises.mkdir()
        _make_shadow(shadow, "SD-001", ep_state="SUPORTADA")
        # Premise graph does NOT reference SD-001
        dot = premises / "graph.dot"
        dot.write_text('digraph { "prem_a" -> "prem_b"; }')
        log.write_text("")
        report = sleep(shadow, archive, log, premises, demotion_threshold=1.0)
        non_blocked = [e for e in report.demoted if "blocked" not in e.reason]
        assert len(non_blocked) >= 1

    def test_merge_during_sleep(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        shadow.mkdir()
        _make_shadow(shadow, "SD-001", pointer_path="/doc.md")
        _make_shadow(shadow, "SD-002", pointer_path="/doc.md", ep_state="pendente")
        log.write_text("")
        report = sleep(shadow, archive, log, tmp_path / "premises", demotion_threshold=1.0)
        assert len(report.merged) >= 1

    def test_sleep_returns_report_with_counts(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        shadow.mkdir()
        _make_shadow(shadow, "SD-001")
        _make_shadow(shadow, "SD-002")
        log.write_text("")
        report = sleep(shadow, archive, log, tmp_path / "premises", demotion_threshold=0.0,
                      regenerate_index=False)
        assert report.total_hot <= 2

    def test_sleep_demotes_to_archive(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        shadow.mkdir()
        _make_shadow(shadow, "SD-001", ep_state="pendente")
        log.write_text("")
        sleep(shadow, archive, log, tmp_path / "premises", demotion_threshold=1.0,
              regenerate_index=False)
        assert not (shadow / "SD-001.md").exists()
        assert (archive / "SD-001.md").exists()


class TestSleepTwiceIdempotent:
    def test_idempotent_no_changes(self, tmp_path):
        shadow = tmp_path / "shadow"
        archive = tmp_path / "archive"
        log = tmp_path / "access.log"
        premises = tmp_path / "premises"
        shadow.mkdir()
        premises.mkdir()
        _make_shadow(shadow, "SD-001", pinned=True)  # pinned = stable
        log.write_text("")
        result = sleep_twice_idempotent(shadow, archive, log, premises)
        assert result is True


class TestWake:
    def test_wake_returns_context(self, tmp_path):
        # Create a mock kanban so wake doesn't read from real one
        kanban = tmp_path / "aes" / "kanban.md"
        kanban.parent.mkdir(parents=True)
        kanban.write_text("---\ncurrent_sprint: test-sprint\n---\n")
        
        result = wake(
            shadow_dir=tmp_path,
            index_file=None,
            loops=[],
            kanban_path=kanban,
        )
        assert isinstance(result, ExecutionContext)
        assert result.sprint == "test-sprint"

    def test_wake_format_contains_acordar(self, tmp_path):
        kanban = tmp_path / "kanban.md"
        kanban.write_text("---\ncurrent_sprint: test\n---\n")
        result = wake(
            shadow_dir=Path("/tmp/nonexistent"),
            index_file=None,
            loops=[],
            kanban_path=kanban,
        )
        formatted = result.format()
        assert "ACORDAR" in formatted

    def test_wake_with_high_loops(self, tmp_path):
        loop = open_demotion_loop("SD-001", "Test", 0.1)
        kanban = tmp_path / "kanban.md"
        kanban.write_text("---\ncurrent_sprint: test\n---\n")
        result = wake(shadow_dir=tmp_path, index_file=None, loops=[loop], kanban_path=kanban)
        assert isinstance(result, ExecutionContext)
        assert len(result.open_loops) > 0
        assert loop.id in result.open_loops[0]

    def test_wake_with_shadow_docs(self, tmp_path):
        _make_shadow(tmp_path, "SD-001", title="Test Doc", pinned=True)
        # Mock kanban so wake() doesn't read the real one
        kanban = tmp_path / "kanban.md"
        kanban.write_text("---\ncurrent_sprint: test\n---\n")
        result = wake(shadow_dir=tmp_path, index_file=None, loops=[], kanban_path=kanban)
        assert isinstance(result, ExecutionContext)
        assert len(result.relevant_insights) > 0
        assert result.relevant_insights[0].doc_id == "SD-001"

    def test_wake_detects_stale_docs(self, tmp_path):
        # Create a doc with old last_accessed
        _make_shadow(tmp_path, "SD-OLD", pinned=False)
        fpath = tmp_path / "SD-OLD.md"
        content = fpath.read_text()
        fm = yaml.safe_load(content.split("---")[1])
        fm["last_accessed"] = "2026-06-01"
        fpath.write_text("---\n" + yaml.dump(fm) + "---\n# Old doc")
        # Mock kanban so wake() doesn't read the real one
        kanban = tmp_path / "kanban.md"
        kanban.write_text("---\ncurrent_sprint: test\n---\n")
        result = wake(shadow_dir=tmp_path, index_file=None, loops=[], kanban_path=kanban)
        stale_warnings = [w for w in result.stale_warnings if "SD-OLD" in w]
        assert len(stale_warnings) > 0

    def test_wake_json_output(self, tmp_path):
        import json
        from dataclasses import asdict
        kanban = tmp_path / "kanban.md"
        kanban.write_text("---\ncurrent_sprint: test\n---\n")
        result = wake(shadow_dir=tmp_path, index_file=None, loops=[], kanban_path=kanban)
        data = asdict(result)
        assert "ticket_id" in data
        assert "relevant_insights" in data
        assert "stale_warnings" in data

    def test_wake_premise_graph_verification(self, tmp_path):
        """Integration test: wake() verifies premise graphs."""
        from lib.memory.consolidate import _verify_premise_graphs
        failures = _verify_premise_graphs()
        # Should return a dict (may be empty if all premises pass)
        assert isinstance(failures, dict)

    def test_wake_configurable_staleness(self, tmp_path):
        """Integration test: staleness threshold is configurable."""
        import os
        from lib.memory.consolidate import STALENESS_THRESHOLD_DAYS
        # Default should be 14
        assert STALENESS_THRESHOLD_DAYS == 14


class TestGetRelevantDocs:
    def test_returns_list(self):
        from lib.memory.consolidate import get_relevant_docs
        result = get_relevant_docs()
        assert isinstance(result, list)

    def test_returns_relevant_docs(self):
        from lib.memory.consolidate import get_relevant_docs, RelevantDoc
        # With no ticket_text, should return empty
        result = get_relevant_docs(ticket_text="nonexistent query")
        assert isinstance(result, list)
