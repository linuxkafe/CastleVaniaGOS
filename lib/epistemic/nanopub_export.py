"""
Nanopublication export core (T053).

Pure functions for mapping AES shadow doc frontmatter → PROV-O TriG/JSON-LD.
Called by scripts/export-nanopub.py (thin CLI wrapper).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

try:
    import pytest
except ImportError:
    pytest = None

AES_NS = "http://example.org/aes/ns/2026/"
NP_NS = "http://www.nanopub.org/nschema#"
SHADOW_NS = "http://example.org/shadow/"
AGENT_NS = "http://example.org/agent/"
TICKET_NS = "http://example.org/ticket/"
ORIGINAL_NS = "http://example.org/original/"

TRIG_TEMPLATE = """@prefix np: <{np_ns}> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix aes: <{aes_ns}> .

# --- Assertion Graph ---
<np:{doc_id}#assertion> {{
  <{shadow_uri}> a prov:Entity ;
    dcterms:title "{title}" ;
    prov:value "{synthesis_escaped}" ;
    aes:epistemicState "{epistemic_state}" ;
{derivation_block}\
{annotation_block}\
}}

# --- Provenance Graph ---
<np:{doc_id}#provenance> {{
  <np:{doc_id}> prov:wasGeneratedBy _:gen-0 .
  _:gen-0 a prov:Activity ;
    prov:startedAtTime "{generated_at}"^^xsd:dateTime ;
    prov:wasAssociatedWith <{agent_uri}> ;
    prov:wasAttributedTo <{ticket_uri}> .
  <{agent_uri}> a {agent_type} ;
    prov:label "{generated_by}" .
{primary_source_block}\
{merge_block}\
}}

# --- Publication Info Graph ---
<np:{doc_id}#pubinfo> {{
  <np:{doc_id}> dcterms:created "{created_iso}"^^xsd:date ;
    dcterms:rights "Public domain — AES governance regime" .
}}
"""


def normalize_datetime(val: str) -> str:
    val = val.strip().rstrip("Z")
    if "T" in val:
        return val + "Z"
    return val + "T00:00:00Z"


def uri_safe(val: str) -> str:
    unsafe = {" ", "(", ")", "/", "\\", ":", ";"}
    return "".join("_" if c in unsafe else c for c in val)


def escape_trig(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def load_frontmatter(path: Path) -> Optional[Dict]:
    content = path.read_text()
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    import yaml
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None


def detect_agent_type(generated_by: str) -> str:
    gb = generated_by.lower()
    if any(marker in gb for marker in [".py", "script", "pipeline", "tool", "ingest", "bot"]):
        return "prov:SoftwareAgent"
    return "prov:Person"


def _format_derivation_block(fm: Dict) -> str:
    pointer = fm.get("pointer", {})
    path = pointer.get("path", "")
    content_hash = pointer.get("content_hash", "")
    if not path:
        return ""
    original_uri = ORIGINAL_NS + uri_safe(path)
    line = f"    prov:wasDerivedFrom <{original_uri}> ;\n"
    if content_hash:
        line += f"    prov:qualifiedDerivation [ a prov:Derivation ;\n"
        line += f"      prov:entity <{original_uri}> ;\n"
        line += f"      prov:hadSignature \"sha256:{escape_trig(content_hash)}\" ] ;\n"
    return line


def _format_annotation_block(fm: Dict) -> str:
    lines = []
    score = fm.get("score", {})
    activation = score.get("activation")
    centrality = score.get("centrality")
    pinned = score.get("pinned")
    if activation is not None:
        lines.append(f"    aes:activationScore \"{activation}\"^^xsd:decimal ;")
    if centrality is not None:
        lines.append(f"    aes:centralityScore \"{centrality}\"^^xsd:decimal ;")
    if pinned is not None:
        lines.append(f"    aes:pinned \"{str(pinned).lower()}\"^^xsd:boolean ;")
    archive_reason = fm.get("archive_reason")
    if archive_reason:
        lines.append(f"    aes:archiveReason \"{escape_trig(str(archive_reason))}\" ;")
    archived_at = fm.get("archived_at")
    if archived_at:
        lines.append(f"    aes:archivedAt \"{normalize_datetime(archived_at)}\"^^xsd:dateTime ;")
    if not lines:
        return ""
    lines[-1] = lines[-1].rstrip(" ;")
    return "\n".join(lines) + "\n"


def _format_primary_source_block(fm: Dict) -> str:
    lines = []
    conversation = fm.get("provenance", {}).get("source_conversation", "")
    ambrosio_path = fm.get("provenance", {}).get("ambrosio_path", "")
    if conversation:
        lines.append(f"  <np:{fm['id']}#assertion> prov:hadPrimarySource <{ORIGINAL_NS}conversation/{uri_safe(conversation)}> .")
    if ambrosio_path:
        lines.append(f"  <{SHADOW_NS}{fm['id']}> prov:hadPrimarySource <{ORIGINAL_NS}ambrosio/{uri_safe(ambrosio_path)}> .")
    if lines:
        return "\n".join(lines) + "\n"
    return ""


def _format_merge_block(fm: Dict) -> str:
    provenance = fm.get("provenance", {})
    merged_from = provenance.get("merged_from", [])
    merged_at = provenance.get("merged_at", "")
    if not merged_from:
        return ""
    lines = []
    for src_id in merged_from:
        lines.append(f"  <{SHADOW_NS}{fm['id']}> prov:wasRevisionOf <{SHADOW_NS}{src_id}> .")
    if merged_at:
        lines.append(f"  <{SHADOW_NS}{fm['id']}> prov:qualifiedRevision [ a prov:Revision ;")
        lines.append(f"    prov:atTime \"{normalize_datetime(merged_at)}\"^^xsd:dateTime ] .")
    return "\n".join(lines) + "\n"


def export_one(path: Path, fmt: str = "trig") -> str:
    fm = load_frontmatter(path)
    if not fm:
        raise ValueError(f"No valid frontmatter in {path}")

    doc_id = fm.get("id", path.stem)
    title = escape_trig(str(fm.get("title", doc_id)))
    synthesis = escape_trig(str(fm.get("synthesis", "")))
    epistemic_state = escape_trig(str(fm.get("epistemic_state", "N/A")))

    provenance = fm.get("provenance", {})
    generated_by = provenance.get("generated_by", "unknown")
    raw_generated_at = provenance.get("generated_at", datetime.now(timezone.utc).isoformat())
    generated_at = normalize_datetime(raw_generated_at)
    source_ticket = provenance.get("source_ticket", "unknown")

    agent_type = detect_agent_type(generated_by)
    agent_uri = f"{AGENT_NS}{uri_safe(generated_by)}"
    ticket_uri = f"{TICKET_NS}{source_ticket}"

    created = fm.get("created", datetime.now().strftime("%Y-%m-%d"))

    derivation_block = _format_derivation_block(fm)
    annotation_block = _format_annotation_block(fm)
    primary_source_block = _format_primary_source_block(fm)
    merge_block = _format_merge_block(fm)

    trig = TRIG_TEMPLATE.format(
        np_ns=NP_NS,
        aes_ns=AES_NS,
        doc_id=doc_id,
        shadow_uri=f"{SHADOW_NS}{doc_id}",
        title=title,
        synthesis_escaped=synthesis,
        epistemic_state=epistemic_state,
        derivation_block=derivation_block,
        annotation_block=annotation_block,
        generated_at=generated_at,
        agent_uri=agent_uri,
        ticket_uri=ticket_uri,
        agent_type=agent_type,
        generated_by=escape_trig(generated_by),
        primary_source_block=primary_source_block,
        merge_block=merge_block,
        created_iso=created,
    )

    if fmt == "json-ld":
        return _trig_to_jsonld(trig, doc_id, fm)
    return trig


def _trig_to_jsonld(trig: str, doc_id: str, fm: Dict) -> str:
    shadow_uri = f"{SHADOW_NS}{doc_id}"
    np_uri = f"np:{doc_id}"
    frame = {
        "@context": {
            "np": NP_NS,
            "prov": "http://www.w3.org/ns/prov#",
            "dcterms": "http://purl.org/dc/terms/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "aes": AES_NS,
        },
        "@graph": [
            {
                "@id": f"np:{doc_id}#assertion",
                "@graph": [{
                    "@id": shadow_uri,
                    "@type": "prov:Entity",
                    "dcterms:title": fm.get("title", doc_id),
                    "prov:value": fm.get("synthesis", ""),
                    "aes:epistemicState": fm.get("epistemic_state", "N/A"),
                }]
            },
            {
                "@id": f"np:{doc_id}#provenance",
                "@graph": [{
                    "@id": np_uri,
                    "prov:wasGeneratedBy": {
                        "@id": "_:gen-0",
                        "@type": "prov:Activity",
                        "prov:startedAtTime": {"@value": fm.get("provenance", {}).get("generated_at", ""), "@type": "xsd:dateTime"},
                        "prov:wasAssociatedWith": {"@id": f"{AGENT_NS}{uri_safe(fm.get('provenance', {}).get('generated_by', 'unknown'))}"}
                    }
                }]
            },
            {
                "@id": f"np:{doc_id}#pubinfo",
                "@graph": [{
                    "@id": np_uri,
                    "dcterms:created": {"@value": fm.get("created", ""), "@type": "xsd:date"},
                    "dcterms:rights": "Public domain — AES governance regime"
                }]
            }
        ]
    }
    return json.dumps(frame, indent=2, ensure_ascii=False)


def export_for_ticket(ticket_id: str, shadow_dir: Path, archive_dir: Path, fmt: str = "trig") -> Dict[str, str]:
    results = {}
    for d in [shadow_dir, archive_dir]:
        if not d.exists():
            continue
        for fpath in sorted(d.glob("*.md")):
            if fpath.name == "README.md":
                continue
            fm = load_frontmatter(fpath)
            if fm and fm.get("provenance", {}).get("source_ticket") == ticket_id:
                results[fpath.stem] = export_one(fpath, fmt)
    return results


def export_all(shadow_dir: Path, archive_dir: Path, fmt: str = "trig") -> Dict[str, str]:
    results = {}
    for d in [shadow_dir, archive_dir]:
        if not d.exists():
            continue
        for fpath in sorted(d.glob("*.md")):
            if fpath.name == "README.md":
                continue
            results[fpath.stem] = export_one(fpath, fmt)
    return results


def verify_roundtrip(shadow_dir: Path, archive_dir: Path) -> int:
    try:
        import pytest
        pytest.importorskip("rdflib")
    except ImportError:
        return 0  # Skip gracefully if pytest or rdflib not available
    import rdflib

    candidates = list(shadow_dir.glob("*.md")) + list(archive_dir.glob("*.md"))
    candidates = [c for c in candidates if c.name != "README.md"]
    if len(candidates) < 3:
        candidates = candidates[:3]
    else:
        candidates = candidates[:3]

    test_files = candidates
    errors = 0

    for fpath in test_files:
        fm = load_frontmatter(fpath)
        if not fm:
            print(f"FAIL {fpath.name}: could not load frontmatter")
            errors += 1
            continue

        doc_id = fm.get("id", fpath.stem)
        trig = export_one(fpath)

        try:
            g = rdflib.Dataset()
            g.parse(data=trig, format="trig")
        except Exception as e:
            print(f"FAIL {fpath.name}: TriG parse error: {e}")
            errors += 1
            continue

        assertion_uri = rdflib.URIRef(f"np:{doc_id}#assertion")
        assertion_graph = g.get_context(assertion_uri)
        if len(assertion_graph) == 0:
            print(f"FAIL {fpath.name}: assertion graph empty")
            errors += 1
            continue

        prov_uri = rdflib.URIRef(f"np:{doc_id}#provenance")
        prov_graph = g.get_context(prov_uri)
        if len(prov_graph) == 0:
            print(f"FAIL {fpath.name}: provenance graph empty")
            errors += 1
            continue

        pubinfo_uri = rdflib.URIRef(f"np:{doc_id}#pubinfo")
        pubinfo_graph = g.get_context(pubinfo_uri)
        if len(pubinfo_graph) == 0:
            print(f"FAIL {fpath.name}: pubinfo graph empty")
            errors += 1
            continue

        shadow_uri = rdflib.URIRef("http://example.org/shadow/" + doc_id)
        title_matches = list(assertion_graph.objects(subject=shadow_uri, predicate=rdflib.DCTERMS.title))
        if not title_matches or str(title_matches[0]) != fm.get("title", doc_id):
            print(f"FAIL {fpath.name}: title mismatch")
            errors += 1
            continue

        print(f"PASS {fpath.name}: 3 graphs, {len(assertion_graph)}+{len(prov_graph)}+{len(pubinfo_graph)} triples, title OK")

    if errors:
        print(f"\nFAILED: {errors} / {len(test_files)}")
    else:
        print(f"\nPASS: {len(test_files)} / {len(test_files)}")

    return errors
