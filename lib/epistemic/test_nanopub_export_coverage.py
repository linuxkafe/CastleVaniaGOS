"""Tests for export_for_ticket, export_all, verify_roundtrip, and uncovered paths (T175)."""

import json
import yaml
import pytest
from pathlib import Path

from lib.epistemic.nanopub_export import (
    export_for_ticket,
    export_all,
    export_one,
    verify_roundtrip,
    load_frontmatter,
    _format_annotation_block,
    _format_primary_source_block,
    _format_merge_block,
)


def _write_shadow(tmp_path, name, overrides=None):
    fm = {
        "id": name,
        "title": f"Title {name}",
        "synthesis": f"Synthesis for {name}",
        "epistemic_state": "VERIFICÁVEL",
        "pointer": {"path": f"docs/{name}.md", "content_hash": "abc"},
        "provenance": {
            "generated_by": "test-script.py",
            "generated_at": "2026-07-06T10:00:00Z",
            "source_ticket": "T053",
            "source_conversation": "",
        },
        "score": {"activation": 0.5, "centrality": 1.0, "pinned": False},
        "created": "2026-07-06",
    }
    if overrides:
        fm.update(overrides)
    path = tmp_path / f"{name}.md"
    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    path.write_text(f"---\n{fm_str}---\n# {name}\nBody.")
    return path


class TestExportForTicket:
    def test_finds_matching_docs(self, tmp_path):
        _write_shadow(tmp_path, "SD-001")
        _write_shadow(tmp_path, "SD-002", {"provenance": {"source_ticket": "T999"}})
        results = export_for_ticket("T053", tmp_path, tmp_path / "empty")
        assert "SD-001" in results
        assert "SD-002" not in results

    def test_empty_when_no_match(self, tmp_path):
        _write_shadow(tmp_path, "SD-001")
        results = export_for_ticket("T999", tmp_path, tmp_path / "empty")
        assert len(results) == 0

    def test_nonexistent_dir_ok(self, tmp_path):
        results = export_for_ticket("T053", tmp_path / "nope", tmp_path / "nope2")
        assert results == {}

    def test_skips_readme(self, tmp_path):
        (tmp_path / "README.md").write_text("not a shadow doc")
        results = export_for_ticket("T053", tmp_path, tmp_path / "empty")
        assert "README" not in results

    def test_includes_archive_dir(self, tmp_path):
        arch = tmp_path / "archive"
        arch.mkdir()
        _write_shadow(arch, "SD-ARCH", {"provenance": {"source_ticket": "T053"}})
        results = export_for_ticket("T053", tmp_path, arch)
        assert "SD-ARCH" in results


class TestExportAll:
    def test_exports_all_docs(self, tmp_path):
        _write_shadow(tmp_path, "SD-001")
        _write_shadow(tmp_path, "SD-002")
        results = export_all(tmp_path, tmp_path / "empty")
        assert len(results) == 2

    def test_empty_dirs(self, tmp_path):
        results = export_all(tmp_path / "nope", tmp_path / "nope2")
        assert results == {}

    def test_skips_readme(self, tmp_path):
        (tmp_path / "README.md").write_text("skip me")
        _write_shadow(tmp_path, "SD-001")
        results = export_all(tmp_path, tmp_path / "empty")
        assert len(results) == 1
        assert "SD-001" in results


class TestVerifyRoundtrip:
    def test_passes_with_valid_docs(self, tmp_path):
        _write_shadow(tmp_path, "SD-001")
        _write_shadow(tmp_path, "SD-002")
        _write_shadow(tmp_path, "SD-003")
        errors = verify_roundtrip(tmp_path, tmp_path / "empty")
        assert errors == 0

    def test_empty_dirs_returns_0(self, tmp_path):
        errors = verify_roundtrip(tmp_path / "nope", tmp_path / "nope2")
        assert errors == 0

    def test_invalid_frontmatter_counts_error(self, tmp_path):
        (tmp_path / "bad.md").write_text("no frontmatter here")
        _write_shadow(tmp_path, "SD-001")
        _write_shadow(tmp_path, "SD-002")
        errors = verify_roundtrip(tmp_path, tmp_path / "empty")
        # bad.md has no frontmatter → counts as error
        assert errors >= 1


class TestLoadFrontmatterEdgeCases:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("")
        assert load_frontmatter(p) is None

    def test_no_frontmatter(self, tmp_path):
        p = tmp_path / "nope.md"
        p.write_text("just body text, no frontmatter")
        assert load_frontmatter(p) is None

    def test_invalid_yaml(self, tmp_path):
        p = tmp_path / "bad.md"
        p.write_text("---\n[[[\n---\nbody")
        assert load_frontmatter(p) is None


class TestFormatAnnotationBlock:
    def test_full_score(self):
        fm = {"score": {"activation": 0.5, "centrality": 1.0, "pinned": True}}
        block = _format_annotation_block(fm)
        assert "activation" in block
        assert "centrality" in block
        assert "pinned" in block

    def test_with_archive_reason(self):
        fm = {"score": {}, "archive_reason": "stale", "archived_at": "2026-07-20"}
        block = _format_annotation_block(fm)
        assert "archiveReason" in block
        assert "archivedAt" in block

    def test_empty_score_returns_empty(self):
        fm = {"score": {}}
        block = _format_annotation_block(fm)
        assert block == ""


class TestFormatPrimarySourceBlock:
    def test_with_conversation(self):
        fm = {"id": "SD-001", "provenance": {"source_conversation": "conv-123"}}
        block = _format_primary_source_block(fm)
        assert "hadPrimarySource" in block
        assert "conv-123" in block

    def test_with_ambrosio_path(self):
        fm = {"id": "SD-001", "provenance": {"ambrosio_path": "session/abc"}}
        block = _format_primary_source_block(fm)
        assert "hadPrimarySource" in block
        assert "abc" in block

    def test_empty_returns_empty(self):
        fm = {"id": "SD-001", "provenance": {}}
        block = _format_primary_source_block(fm)
        assert block == ""


class TestFormatMergeBlock:
    def test_with_merged_from(self):
        fm = {"id": "SD-001", "provenance": {"merged_from": ["SD-OLD"], "merged_at": "2026-07-20"}}
        block = _format_merge_block(fm)
        assert "wasRevisionOf" in block
        assert "qualifiedRevision" in block

    def test_empty_returns_empty(self):
        fm = {"id": "SD-001", "provenance": {}}
        block = _format_merge_block(fm)
        assert block == ""


class TestExportOneJsonLd:
    def test_jsonld_format(self, tmp_path):
        path = _write_shadow(tmp_path, "SD-JSONLD")
        result = export_one(path, fmt="json-ld")
        parsed = json.loads(result)
        assert "@graph" in parsed
        assert len(parsed["@graph"]) == 3
