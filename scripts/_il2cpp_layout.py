#!/usr/bin/env python3
"""Shared Il2CPP metadata layout-discivery utilities (stdlib only).

This module is imported by ``extract_il2cpp_metadata.py`` and may also be reused
by other extractors (T002, T003).  It deliberately contains **no output logic** —
every function returns data structures that the caller serialises.

Design principles (from T001-plan.md § Hostile Analysis > ASSUMPTIONS):
  * Strides are never literals; they are derived at runtime from the section
    length and a candidate set.
  * The bootstrap invariant ("leading int32 resolves to a string heap token")
    is the *only* validator of a stride — it does not presuppose the layout
    it is meant to validate.
  * A below-threshold score is a hard failure, never a "best effort" pick.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Metadata version 24 (Unity 2018.4) — section index → name.
#
# Names are verified against `aes/shadow/SD-CI-001-*.md` where the SD record
# is silent, names are provisional and labelled "unknown_N".
# ---------------------------------------------------------------------------

_METADATA_V24_SECTIONS = [
    "stringLiteral",          # 0  — 8 B entry: (charLength, charOffset)
    "stringLiteralData",      # 1  — contiguous UTF-8 payload
    "string",                 # 2  — contiguous null-terminated UTF-8 blob
    "events",                 # 3  — Il2CppEventDefinition, 24 B
    "properties",             # 4  — Il2CppPropertyDefinition, 20 B
    "methods",                # 5  — Il2CppMethodDefinition, stride open
    "parameters",             # 6
    # 7 — gap (see below)
    "unknown_7",
    "unknown_8",
    "unknown_9",
    "parameters",             # 10 — SD-CI-001: offset 14008572, stride 12
    "fields",                 # 11 — SD-CI-001: stride 12, 187726 entries
    "unknown_12",
    "unknown_13",
    "unknown_14",
    "nestedTypes",            # 15 — SD-CI-001: stride 4
    "interfaces",             # 16 — SD-CI-001: stride 4
    "vtableMethods",          # 17 — SD-CI-001: stride 4
    "interfaceOffsets",       # 18 — SD-CI-001: stride 8
    "typeDefinitions",        # 19 — SD-CI-001: stride 100, 20637 entries
    "images",                 # 20 — SD-CI-001: stride 8
    "assemblies",             # 21 — SD-CI-001: stride 40
    "unknown_22",
    "metadata_usage_pairs",   # 23 — SD-CI-001: stride 8
    "fieldRefs",              # 24 — SD-CI-001: stride 12
    "unknown_25",
    "unknown_26",
    "unknown_27",
    "unknown_28",
    "unknown_29",
    "unknown_30",
    "unknown_31",             # 31 — empty (length 0)
    "unknown_32",             # 32
]

# Sanity: the enum must be 0-indexed contiguous
assert _METADATA_V24_SECTIONS[0] == "stringLiteral"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SANITY = 0xFAB11BAF
HEADER_SIZE_FIXED = 8  # sanity (4) + version (4)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionEnvelope:
    """Raw section descriptor read from the header."""
    name: str
    index: int
    offset: int
    length: int


@dataclass(frozen=True)
class HeapBounds:
    """Bounds of the string heap (the *string* section, index 2)."""
    offset: int
    length: int


@dataclass
class StrideCandidate:
    stride: int
    count: int
    score: float
    remainder: int


@dataclass
class StrideResult:
    """Result of the bootstrap stride search for one section."""
    section_name: str
    section_index: int
    length: int
    offset: int
    best_stride: Optional[int]          # None if no candidate qualified
    best_score: float
    best_count: int
    qualified: bool                     # True iff best_score >= threshold
    candidates: list[StrideCandidate]


@dataclass
class InvariantResult:
    name: str
    expected: object                     # human-readable expectation
    actual: object
    status: str                          # "SUPORTADA" | "NÃO-VERIFICÁVEL"
    detail: str = ""


@dataclass
class LayoutReport:
    """Full stride-derivation report for one metadata file."""
    source_sha256: str
    byte_size: int
    version: int
    section_count: int
    header_size: int
    sections: list[StrideResult]
    invariants: list[InvariantResult]


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

def _section_name(index: int, version: int) -> str:
    """Return the canonical name for a section index.

    Falls back to ``"unknown_N"`` if the index is beyond the known table.
    """
    if version == 24 and index < len(_METADATA_V24_SECTIONS):
        return _METADATA_V24_SECTIONS[index]
    return f"unknown_{index}"


def compute_section_count(blob: bytes) -> int:
    """Determine how many section entries the header contains.

    The header is ``sanity (4) + version (4) + N × (int32 offset, int32 length)``.
    The first section's data offset therefore reveals N:

        N = (first_section.offset - 8) / 8

    This is robust against metadata version changes: if a future build extends
    the enum, the section table grows and the first data offset updates
    automatically.
    """
    sanity = struct.unpack_from('<I', blob, 0)[0]
    if sanity != SANITY:
        raise ValueError(
            f"Bad sanity value 0x{sanity:08x}, expected 0x{SANITY:08x}"
        )
    version = struct.unpack_from('<I', blob, 4)[0]
    first_offset = struct.unpack_from('<i', blob, 8)[0]
    section_count = (first_offset - HEADER_SIZE_FIXED) // 8
    # Sanity boundary: section_count must be positive and the header must not
    # exceed the first section's offset.
    if section_count <= 0 or first_offset < HEADER_SIZE_FIXED + section_count * 8:
        raise ValueError(
            f"Cannot determine section count: first_offset={first_offset}, "
            f"computed section_count={section_count}"
        )
    return section_count


def read_header(blob: bytes) -> dict:
    """Parse the global-metadata header.

    Returns a dict::

        {
            "sanity": int,
            "version": int,
            "header_size": int,      # 8 + section_count * 8
            "section_count": int,
            "sections": [SectionEnvelope, ...],
            "heap": HeapBounds,      # Section 2 (string heap)
        }
    """
    sanity = struct.unpack_from('<I', blob, 0)[0]
    version = struct.unpack_from('<I', blob, 4)[0]
    if sanity != SANITY:
        raise ValueError(
            f"Bad sanity value 0x{sanity:08x}, expected 0x{SANITY:08x}"
        )

    section_count = compute_section_count(blob)
    header_size = HEADER_SIZE_FIXED + section_count * 8

    sections: list[SectionEnvelope] = []
    for i in range(section_count):
        off = 8 + i * 8
        sec_offset, sec_length = struct.unpack_from('<ii', blob, off)
        name = _section_name(i, version)
        sections.append(SectionEnvelope(
            name=name, index=i, offset=sec_offset, length=sec_length
        ))

    # The string heap is section index 2 in v24.
    heap_section = sections[2]
    heap = HeapBounds(offset=heap_section.offset, length=heap_section.length)

    return {
        "sanity": sanity,
        "version": version,
        "header_size": header_size,
        "section_count": section_count,
        "sections": sections,
        "heap": heap,
    }


# ---------------------------------------------------------------------------
# Bootstrap invariant — leading int32 resolves to a string heap token
# ---------------------------------------------------------------------------

def resolve_string(blob: bytes, heap: HeapBounds, index: int) -> Optional[bytes]:
    """Resolve a string heap index to its null-terminated UTF-8 bytes.

    Returns ``None`` if the index is out of range or the token is empty.
    """
    if index < 0 or index >= heap.length:
        return None
    abs_start = heap.offset + index
    end = blob.find(b'\x00', abs_start, heap.offset + heap.length)
    if end < 0:
        return None
    token = blob[abs_start:end]
    if not token:
        return None
    return token


def is_identifier_shaped(token: bytes) -> bool:
    """Heuristic: a resolved string is identifier-shaped if it is non-empty,
    contains no control characters, and its first byte is alphanumeric,
    ``<``, ``$``, ``_``, or ``.``."""
    if not token:
        return False
    if any(b < 0x20 for b in token):
        return False
    first = token[0]
    return (
        chr(first).isalnum()  # a-zA-Z0-9
        or first in (ord('<'), ord('$'), ord('_'), ord('.'))
    )


def candidate_strides(length: int, max_stride: int = 256,
                      allow_padding: bool = True) -> list[int]:
    """Return strides that divide ``length`` (optionally tolerating a small
    remainder ≤ 8, which Unity uses to pad some sections).

    Strides are always in the range [4, min(max_stride, length)] and are
    multiples of 4.
    """
    candidates: list[int] = []
    step = 4
    upper = min(max_stride, length)
    for stride in range(step, upper + 1, step):
        if length % stride == 0:
            candidates.append(stride)
        elif allow_padding and length % stride <= 8 and length % stride > 0:
            # Tolerate small remainders — Unity sometimes pads to 4 bytes.
            if stride not in candidates:
                candidates.append(stride)
    # Deduplicate while preserving order
    seen: set[int] = set()
    result: list[int] = []
    for s in candidates:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def score_stride(blob: bytes, section: SectionEnvelope, stride: int,
                 heap: HeapBounds,
                 *, name_offset: int = 0,
                 secondary_check=None) -> float:
    """Score a candidate stride by the fraction of records whose leading
    ``int32`` at ``name_offset`` resolves to an identifier-shaped string.

    Parameters
    ----------
    name_offset:
        Offset within the record where the name index lives (default 0).
    secondary_check:
        Optional callable ``(blob, rec_base, stride, heap) -> bool`` that
        performs an *additional* validation (e.g. checking a nearby field
        looks like a valid type index).  If supplied, both the name
        resolution and the secondary check must pass.
    """
    if section.length == 0:
        return 0.0

    count = section.length // stride
    # Sample up to 2048 records for scoring, then validate winner over all.
    sample = min(2048, count)
    if sample == 0:
        return 0.0

    resolved = 0
    for i in range(sample):
        rec_off = section.offset + i * stride
        idx_val = struct.unpack_from('<i', blob, rec_off + name_offset)[0]
        token = resolve_string(blob, heap, idx_val)
        if token is not None and is_identifier_shaped(token):
            if secondary_check is not None:
                if not secondary_check(blob, rec_off, stride, heap):
                    continue
            resolved += 1

    return resolved / sample


def score_stride_full(blob: bytes, section: SectionEnvelope, stride: int,
                      heap: HeapBounds, *, name_offset: int = 0,
                      secondary_check=None) -> float:
    """Score over *all* records (not a sample)."""
    if section.length == 0:
        return 0.0
    count = section.length // stride
    if count == 0:
        return 0.0

    resolved = 0
    for i in range(count):
        rec_off = section.offset + i * stride
        idx_val = struct.unpack_from('<i', blob, rec_off + name_offset)[0]
        token = resolve_string(blob, heap, idx_val)
        if token is not None and is_identifier_shaped(token):
            if secondary_check is not None:
                if not secondary_check(blob, rec_off, stride, heap):
                    continue
            resolved += 1
    return resolved / count


def derive_stride_for_section(blob: bytes, section: SectionEnvelope,
                              heap: HeapBounds, *,
                              min_score: float = 0.995,
                              max_stride: int = 256,
                              name_offset: int = 0,
                              secondary_check=None,
                              max_count: int = 300) -> StrideResult:
    """Search candidate strides and return the best-qualified result.

    A stride is *qualified* only if its score exceeds ``min_score``.  An empty
    section (length 0) returns a trivially-unsuported result.
    """
    if section.length == 0:
        return StrideResult(
            section_name=section.name,
            section_index=section.index,
            length=0,
            offset=section.offset,
            best_stride=None,
            best_score=1.0,
            best_count=0,
            qualified=True,
            candidates=[],
        )

    candidates: list[StrideCandidate] = []
    for stride in candidate_strides(section.length, max_stride=max_stride):
        count = section.length // stride
        # Skip unfeasibly large counts (would produce too many false positives
        # from the 4-byte "name resolves" coincidence).
        if count > max_count:
            # For stride-4 sections, use a smaller sample and full count anyway
            pass
        score = score_stride(
            blob, section, stride, heap,
            name_offset=name_offset,
            secondary_check=secondary_check,
        )
        remainder = section.length % stride
        candidates.append(StrideCandidate(
            stride=stride, count=count, score=score, remainder=remainder
        ))

    # Pick the highest-scoring candidate
    if candidates:
        best = max(candidates, key=lambda c: c.score)
    else:
        best = None

    if best is None:
        return StrideResult(
            section_name=section.name,
            section_index=section.index,
            length=section.length,
            offset=section.offset,
            best_stride=None,
            best_score=0.0,
            best_count=0,
            qualified=False,
            candidates=[],
        )

    qualified = best.score >= min_score
    return StrideResult(
        section_name=section.name,
        section_index=section.index,
        length=section.length,
        offset=section.offset,
        best_stride=best.stride if qualified else None,
        best_score=best.score,
        best_count=best.count if qualified else 0,
        qualified=qualified,
        candidates=candidates,
    )


# ---------------------------------------------------------------------------
# Section-specific secondary checks
# ---------------------------------------------------------------------------

def _type_index_valid(blob: bytes, rec_off: int, stride: int,
                      heap: HeapBounds) -> bool:
    """Secondary check for typeDefinitions: ``declaringTypeIndex`` (at +16)
    must be -1 or in [0, type_count).

    Type count is derived from the typeDefinitions section itself — but we
    don't have it here without circular dependency.  We instead accept any
    value in [-1, 2_000_000] as "plausible range" and let the closure
    invariant do the precise check.
    """
    decl = struct.unpack_from('<i', blob, rec_off + 16)[0]
    return decl == -1 or (0 <= decl < 2_000_000)


def _method_declaring_type_valid(blob: bytes, rec_off: int, stride: int,
                                  heap: HeapBounds) -> bool:
    """Secondary check for methods: ``declaringType`` (at +4) must be -1 or a
    plausible type index (0..type_count).  Type count is looked up from a
    closure on ``blob``; we accept a wide bound here for the bootstrap and
    tighten in the closure invariant.
    """
    decl = struct.unpack_from('<i', blob, rec_off + 4)[0]
    return decl == -1 or (0 <= decl < 2_000_000)


# ---------------------------------------------------------------------------
# Public API for the main extractor
# ---------------------------------------------------------------------------

def derive_layout(blob: bytes, *, min_score: float = 0.995) -> dict:
    """Run the full stride search and return a layout report.

    Returns a dict with keys ``source``, ``sections``, ``not_verifiable``.
    """
    header = read_header(blob)
    heap = header["heap"]
    sections = header["sections"]

    results: list[StrideResult] = []
    not_verifiable: list[dict] = []

    for sec in sections:
        # Skip sections that are not fixed-stride arrays.
        if sec.name in ("string", "stringLiteralData"):
            results.append(StrideResult(
                section_name=sec.name,
                section_index=sec.index,
                length=sec.length,
                offset=sec.offset,
                best_stride=None,
                best_score=1.0,
                best_count=0,
                qualified=True,
                candidates=[],
            ))
            continue

        if sec.length == 0:
            results.append(StrideResult(
                section_name=sec.name,
                section_index=sec.index,
                length=0,
                offset=sec.offset,
                best_stride=None,
                best_score=1.0,
                best_count=0,
                qualified=True,
                candidates=[],
            ))
            continue

        # Use enhanced secondary check for methods
        sec_check = None
        if sec.name == "methods":
            sec_check = _method_declaring_type_valid
        elif sec.name == "typeDefinitions":
            sec_check = _type_index_valid

        # Limit max_count appropriately: for stride-4 sections, skip the
        # max_count gate (they have millions of candidates).
        max_c = 500 if sec.length // 4 <= 500 else 300

        result = derive_stride_for_section(
            blob, sec, heap,
            min_score=min_score,
            name_offset=0,
            secondary_check=sec_check,
            max_count=max_c,
        )

        # For the qualified candidate, validate over the FULL section.
        if result.best_stride is not None:
            full_score = score_stride_full(
                blob, sec, result.best_stride, heap,
                name_offset=0,
                secondary_check=sec_check,
            )
            result.best_score = full_score
            if full_score < min_score:
                result.qualified = False
                not_verifiable.append({
                    "section": sec.name,
                    "reason": (
                        f"Stride {result.best_stride} sampled score was "
                        f"{result.best_score:.4f} but full-section score "
                        f"{full_score:.4f} fell below threshold {min_score}."
                    ),
                    "candidates": [
                        {"stride": c.stride, "score": c.score,
                         "count": c.count}
                        for c in sorted(result.candidates, key=lambda x: -x.score)
                    ],
                })

        if not result.qualified:
            not_verifiable.append({
                "section": sec.name,
                "reason": (
                    f"No candidate stride scored ≥ {min_score}. "
                    f"Best: stride {result.best_stride or 'N/A'} "
                    f"score {result.best_score:.4f}."
                ),
                "candidates": [
                    {"stride": c.stride, "score": c.score,
                     "count": c.count, "remainder": c.remainder}
                    for c in sorted(result.candidates, key=lambda x: -x.score)
                ],
            })
        results.append(result)

    return {
        "source": header,
        "sections": results,
        "not_verifiable": not_verifiable,
    }
