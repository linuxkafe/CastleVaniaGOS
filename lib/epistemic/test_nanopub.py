"""
Tests for nanopublication export (T053).
"""

import pytest
from pathlib import Path

from lib.epistemic.nanopub_export import (
    escape_trig,
    normalize_datetime,
    uri_safe,
    detect_agent_type,
    load_frontmatter,
    export_one,
    verify_roundtrip,
)


def _sample_fm(tmp_path, overrides=None):
    import yaml
    fm = {
        "id": "SD-TEST-001",
        "title": "Test Document",
        "synthesis": "This is a test synthesis.",
        "epistemic_state": "NÃO-VERIFICÁVEL",
        "pointer": {"path": "docs/test.md", "content_hash": "abc123"},
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
    path = tmp_path / "SD-TEST-001.md"
    fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    path.write_text(f"---\n{fm_str}---\n# Test\nBody content.")
    return path, fm


def test_escape_trig():
    assert escape_trig('hello "world"') == 'hello \\"world\\"'
    assert escape_trig("line1\nline2") == "line1\\nline2"
    assert escape_trig("nochange") == "nochange"


def test_normalize_datetime():
    assert normalize_datetime("2026-07-06") == "2026-07-06T00:00:00Z"
    assert normalize_datetime("2026-07-06T10:00:00Z") == "2026-07-06T10:00:00Z"
    assert normalize_datetime("2026-07-06T10:00:00") == "2026-07-06T10:00:00Z"


def test_uri_safe():
    assert uri_safe("T041 (ingest-ambrosio.py)") == "T041__ingest-ambrosio.py_"
    assert uri_safe("hello/world:test") == "hello_world_test"
    assert uri_safe("simple") == "simple"


def test_detect_agent_type():
    assert detect_agent_type("test-script.py") == "prov:SoftwareAgent"
    assert detect_agent_type("T041 (ingest-ambrosio.py)") == "prov:SoftwareAgent"
    assert detect_agent_type("rodolfo") == "prov:Person"


def test_load_frontmatter(tmp_path):
    path, fm = _sample_fm(tmp_path)
    loaded = load_frontmatter(path)
    assert loaded is not None
    assert loaded["id"] == "SD-TEST-001"
    assert loaded["title"] == "Test Document"


def test_export_one_trig(tmp_path):
    path, fm = _sample_fm(tmp_path)
    trig = export_one(path)
    assert "@prefix np:" in trig
    assert "@prefix prov:" in trig
    assert "@prefix aes:" in trig
    assert "#assertion" in trig
    assert "#provenance" in trig
    assert "#pubinfo" in trig
    assert "SD-TEST-001" in trig
    assert "Test Document" in trig
    assert "NÃO-VERIFICÁVEL" in trig
    assert "prov:SoftwareAgent" in trig


def test_export_one_jsonld(tmp_path):
    path, fm = _sample_fm(tmp_path)
    jld = export_one(path, fmt="json-ld")
    assert '"@context"' in jld
    assert 'SD-TEST-001' in jld
    import json
    parsed = json.loads(jld)
    assert parsed["@graph"][0]["@id"].endswith("#assertion")


def test_export_archived(tmp_path):
    import yaml
    fm = {
        "id": "SD-ARCH-001",
        "title": "Archived Doc",
        "synthesis": "Old synthesis.",
        "epistemic_state": "NÃO-VERIFICÁVEL",
        "pointer": {"path": "old.md", "content_hash": "def456"},
        "provenance": {
            "generated_by": "old-script.py",
            "generated_at": "2026-07-01T00:00:00Z",
            "source_ticket": "T041",
            "source_conversation": "",
        },
        "score": {"activation": 0.0, "centrality": 0.0, "pinned": False},
        "created": "2026-07-01",
        "archive_reason": "score 0.05 below threshold 0.2",
        "archived_at": "2026-07-05T05:19:21Z",
    }
    path = tmp_path / "SD-ARCH-001.md"
    fm_str = yaml.dump(fm, default_flow_style=False)
    path.write_text(f"---\n{fm_str}---\n# Old\nBody.")
    trig = export_one(path)
    assert "aes:archiveReason" in trig
    assert "aes:archivedAt" in trig
    assert "score 0.05 below threshold" in trig


def test_export_merged(tmp_path):
    import yaml
    fm = {
        "id": "SD-MERGE-001",
        "title": "Merged Doc",
        "synthesis": "Merged synthesis.",
        "epistemic_state": "SUPORTADA",
        "pointer": {"path": "merged.md", "content_hash": ""},
        "provenance": {
            "generated_by": "merge-tool",
            "generated_at": "2026-07-06T00:00:00Z",
            "source_ticket": "T053",
            "source_conversation": "",
            "merged_from": ["SD-SOURCE-001", "SD-SOURCE-002"],
            "merged_at": "2026-07-06T12:00:00Z",
        },
        "score": {"activation": 0.0, "centrality": 0.0, "pinned": False},
        "created": "2026-07-06",
    }
    path = tmp_path / "SD-MERGE-001.md"
    fm_str = yaml.dump(fm, default_flow_style=False)
    path.write_text(f"---\n{fm_str}---\n# Merged\nBody.")
    trig = export_one(path)
    assert "prov:wasRevisionOf" in trig
    assert "SD-SOURCE-001" in trig
    assert "prov:qualifiedRevision" in trig


def test_export_human_agent(tmp_path):
    path, fm = _sample_fm(tmp_path, {"provenance": {
        "generated_by": "rodolfo",
        "generated_at": "2026-07-06T10:00:00Z",
        "source_ticket": "T053",
        "source_conversation": "",
    }})
    trig = export_one(path)
    assert "prov:Person" in trig


def test_export_no_pointer(tmp_path):
    path, fm = _sample_fm(tmp_path, {"pointer": {"path": "", "content_hash": ""}})
    trig = export_one(path)
    assert "prov:wasDerivedFrom" not in trig


def test_export_primary_source(tmp_path):
    path, fm = _sample_fm(tmp_path, {"provenance": {
        "generated_by": "test.py",
        "generated_at": "2026-07-06T10:00:00Z",
        "source_ticket": "T053",
        "source_conversation": "2026-07-06-conversation-123",
    }})
    trig = export_one(path)
    assert "prov:hadPrimarySource" in trig
    assert "conversation" in trig


def test_roundtrip_via_rdflib(tmp_path):
    pytest.importorskip("rdflib")
    import rdflib
    path, fm = _sample_fm(tmp_path)
    trig = export_one(path)
    g = rdflib.Dataset()
    g.parse(data=trig, format="trig")

    assertion = rdflib.URIRef("np:SD-TEST-001#assertion")
    provenance = rdflib.URIRef("np:SD-TEST-001#provenance")
    pubinfo = rdflib.URIRef("np:SD-TEST-001#pubinfo")
    assert len(g.get_context(assertion)) > 0
    assert len(g.get_context(provenance)) > 0
    assert len(g.get_context(pubinfo)) > 0

    shadow_uri = rdflib.URIRef("http://example.org/shadow/SD-TEST-001")
    titles = list(g.get_context(assertion).objects(subject=shadow_uri, predicate=rdflib.DCTERMS.title))
    assert len(titles) == 1
    assert str(titles[0]) == "Test Document"


def test_verify_roundtrip_on_fake_docs(tmp_path):
    pytest.importorskip("rdflib")
    """Verify roundtrip with generated docs (not real shadow docs)."""
    shadow_dir = tmp_path / "shadow"
    archive_dir = shadow_dir / "archive"
    shadow_dir.mkdir(parents=True)

    for i in range(3):
        path, fm = _sample_fm(shadow_dir, {"id": f"SD-FAKE-{i:03d}", "title": f"Fake {i}"})
        # rewrite to correct path
        correct_path = shadow_dir / f"SD-FAKE-{i:03d}.md"
        path.rename(correct_path)

    errors = verify_roundtrip(shadow_dir, archive_dir)
    assert errors == 0
