#!/usr/bin/env python3
"""Bootstrap the AES ticket set for castlevania-re-1 remediation."""
import pathlib, textwrap, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
TICKETS = ROOT / "aes" / "tickets"
TICKETS.mkdir(parents=True, exist_ok=True)
TODAY = "2026-10-21"

T = {}

T["T001"] = dict(
    name="il2cpp-metadata-stride-derivation",
    tier="heavy",
    title="Rebuild the Il2CPP metadata extractor with derived struct strides and cross-section invariants",
    priority="P0",
    moscow="Must",
    estimate=8,
    context=(
        "The round-1 peer review returned NÃO APROVADO with F-001 (BLOCKER: 19,843 types claimed "
        "vs 4,056 shipped) and F-006 (MAJOR: 71% of type names carry control characters). "
        "Independent reconnaissance (aes/shadow/SD-CI-001) established the root cause: the extractor "
        "hardcoded a 104-byte Il2CppTypeDefinition stride and a 16-byte Il2CppFieldDefinition stride. "
        "The true strides for this build (metadata version 24) are 100 and 12 bytes, giving 20,637 types "
        "and 187,726 fields. The 104-byte stride resolves cleanly for roughly the first 12,405 entries and "
        "then desynchronises, which is why the shipped JSON had a self-consistent type_count of 4,056 while "
        "carrying garbage names. The methods array layout is still NÃO-VERIFICÁVEL."
    ),
    ac=[
        "A new extractor at scripts/extract_il2cpp_metadata.py reads global-metadata.dat and emits extracted/work/full_metadata.json.",
        "Every struct stride is DERIVED at runtime from the section length and a candidate set; no stride is a literal in the source.",
        "The extractor fails loudly (non-zero exit) if any cross-section invariant fails; it never filters bad entries out.",
        "len(types) == type_count == the count implied by the derived stride, and every type name resolves to a heap string.",
        "The count of type names containing control characters is 0.",
        "sum(type[i].field_count) == fields_count and max(type[i].method_start + type[i].method_count) == methods_count, or the extractor reports which invariant is unverifiable and by how much.",
        "The methods section layout is either resolved with a documented stride plus proof, or emitted as an explicit NÃO-VERIFICÁVEL block with the tested candidate set and the failure metric for each.",
        "extracted/work/full_metadata.json is regenerated and the previous corrupt file is removed or moved to extracted/work/superseded/ with a README stating why.",
        "The extractor prints a machine-readable stride-derivation report to stdout (JSON) recording every candidate stride tried and its score.",
    ],
    notes=(
        "Do not port the existing extractor. Derive the layout from first principles using the header pairs at "
        "byte 8, then prove each stride with a semantic invariant (nameIndex resolves to a heap string; "
        "declaringTypeIndex is in range; fieldStart is monotone). SD-CI-001 already fixes the type stride at "
        "100 and the field stride at 12. The methods layout is the open question: 32 bytes leaves a 4-byte "
        "remainder and only about 60% of nameIndex values resolve, so the stride or the intra-entry field "
        "order is wrong. Search candidate strides against the invariant 'nameIndex resolves AND the "
        "declaringType is either -1 or a valid type index' and record the winner."
    ),
    deps="none (root of the chain)",
    rollback="The old extracted/work/full_metadata.json is moved aside, not deleted; git is not initialised so keep a byte-for-byte copy under extracted/work/superseded/.",
    risks=(
        "The 100-byte typeDefinition stride is empirically strong (99.95%) but only one build's layout; if a "
        "future APK version differs the extractor must detect it via the invariant, not assume. "
        "The methods layout may resist discovery; the ticket explicitly permits an honest NÃO-VERIFICÁVEL "
        "outcome provided the search space and the metrics are recorded."
    ),
)

T["T002"] = dict(
    name="game-strings-extraction",
    tier="standard",
    title="Rebuild the game string extraction to ship both the 213,293 heap tokens and the 19,297 literals",
    priority="P0",
    moscow="Must",
    estimate=4,
    context=(
        "F-002 (BLOCKER as filed) claims the report's 213,293 strings are unsupported because "
        "extracted/work/game_strings.json holds only 31,902 categorized entries. Independent verification "
        "(SD-META-001) shows the report's number is CORRECT: the string heap at offset 626,752 contains "
        "exactly 213,293 distinct non-empty null-terminated tokens in 4,168,612 bytes (4.17 MB decimal). "
        "The defect is the artifact, not the report. A second, distinct set also exists: stringLiteral at "
        "offset 272 holds 19,297 literals (length + dataIndex, 8 bytes each) whose payloads live in "
        "stringLiteralData at offset 154,648. The current file conflates identifiers with literals and "
        "loses the addressing that makes either usable."
    ),
    ac=[
        "A new extractor at scripts/extract_game_strings.py emits extracted/work/string_heap.jsonl and extracted/work/string_literals.jsonl.",
        "string_heap.jsonl has exactly 213,293 records, each with a heap_offset field giving the absolute byte offset of the string in global-metadata.dat.",
        "string_literals.jsonl has exactly 19,297 records, each with length, data_offset and the decoded literal.",
        "The old extracted/work/game_strings.json is either deleted or replaced by a file that is a strict superset; if retained, it is renamed with a README stating that it is a lossy view.",
        "A categorisation step writes extracted/work/game_strings_categorised.json as a derived view that records the category rule and the source offset for every entry, and that is byte-traceable back to the jsonl files.",
        "Every record in every emitted file can be located in global-metadata.dat by its recorded offset; a verification script re-reads the file at those offsets and asserts equality.",
        "The report's '213,293 strings / 4.17 MB' claim is backed by a command whose output is the count.",
    ],
    notes=(
        "Preserve the categorisation work that exists, but demote it from 'the artifact' to 'a derived view'. "
        "The categoriser currently keys by substring heuristics over symbol names; keep the rules, but record "
        "them in a machine-readable rules file so a reader can reproduce any single category assignment. "
        "Do not use regex keyword matching to select individual strings out of the heap for the canonical "
        "artifacts - the heap is small enough to ship whole."
    ),
    deps="none (independent of T001; consumes the same source file)",
    rollback="Keep the existing game_strings.json untouched until the new artifacts verify; then move it aside.",
    risks=(
        "The categories in the current file were hand-curated; dropping them loses curation value. "
        "Mitigation: the categorised view preserves the 12 category names and their membership lists."
    ),
)

T["T003"] = dict(
    name="table-catalog-normalisation",
    tier="standard",
    title="Normalise the table catalog so every reported table exists as an exact key and categories sum to the total",
    priority="P1",
    moscow="Must",
    estimate=3,
    context=(
        "F-007 (MAJOR) and F-015 (MINOR). The reports name eight tables explicitly - charactertable, "
        "skilltable, mobatable, skillbufftable, skillicontable, specialattacktable, gifttable, soundtable - "
        "and none of them exists as an exact key in extracted/work/table_catalog.json. Only suffixed variants "
        "exist (charactertableo, skilltablel, skillbufftablei, skillicontablej, specialattacktablev, "
        "questmobatable, resourcesoundtable, soundtables, mlstringgifttable). The suffix pattern is a tokeniser "
        "bug: the extractor is concatenating the table name with a trailing character from the source stream. "
        "Separately, the 11 categories cover 266 of the 350 tables; 84 are uncategorised, so the report's "
        "category counts cannot be derived from the artifact."
    ),
    ac=[
        "Every table name reported in either analysis report exists as an exact key in extracted/work/table_catalog.json.",
        "sum(len(v) for v in categories.values()) == len(tables) == total, with no uncategorised remainder.",
        "Each table entry records the byte offset in globalgamemanagers or globalgamemanagers.assets where the name was found, so the name is verifiable rather than asserted.",
        "A verification script re-reads the source file at each recorded offset and asserts the table name is present there.",
        "The categorisation rules are stored in a machine-readable rules file, not inline in the extractor.",
        "work/table_data_extracted.json, currently 2 bytes, is either populated with real data or removed from the report's file inventory.",
    ],
    notes=(
        "The root cause is a string-extraction bug in the table-name scanner, not a naming-convention mismatch. "
        "Fix the scanner, then re-derive the catalog; do not hand-patch the JSON. The 350 table references in "
        "globalgamemanagers were located by scanning for the 'table/' prefix, and the 317 Table type names in "
        "globalgamemanagers.assets are a separate population - decide explicitly whether the catalog unions them "
        "and record the decision in the artifact."
    ),
    deps="none (independent); report corrections in T007 depend on this",
    rollback="Keep the existing table_catalog.json until the new one verifies.",
    risks=(
        "If the 350 'table/' references and the 317 asset type names are different populations, the 'true' total "
        "is either 350 or 317 or their union, and the report's '350+' may itself be wrong. Resolve by measuring, "
        "not by assuming, and record the population definition in the artifact."
    ),
)

T["T004"] = dict(
    name="missing-artifacts",
    tier="standard",
    title="Produce method_index.json and metadata_summary.json, or delete the claims that reference them",
    priority="P1",
    moscow="Must",
    estimate=2,
    context=(
        "F-003 (BLOCKER). FINAL_ANALYSIS_REPORT.md section 11 lists 'work/metadata_summary.json (189 MB)' and "
        "'work/method_index.json (índice de métodos)' as extracted deliverables. Neither file exists anywhere in "
        "the project. A 189 MB metadata_summary.json was created during the original run and deleted as a "
        "corrupted intermediate; the report was never updated."
    ),
    ac=[
        "work/method_index.json exists and is a complete index over the method section, with each record carrying the method name, the declaring type, and the byte offset in global-metadata.dat.",
        "work/metadata_summary.json exists and is a summary of the metadata: per-section offsets, lengths, derived counts and strides, plus the total string and type counts.",
        "Both files are listed in the reports with their true paths and true byte sizes.",
        "If the methods layout is still NÃO-VERIFICÁVEL under T001, method_index.json is not produced and the report no longer claims it; the report says so explicitly rather than omitting the row.",
    ],
    notes=(
        "The honest resolution is conditional. Do not ship a placeholder method_index.json whose content cannot "
        "be justified by the method array layout. If T001 could not resolve the methods stride, the correct "
        "deliverable is a report that says the method index was not produced and why."
    ),
    deps="T001 (needs the resolved type and method layout)",
    rollback="New files only; nothing to roll back.",
    risks="A 189 MB summary was previously deleted as corrupt. If a large summary is generated again, validate it before it replaces anything.",
)

T["T005"] = dict(
    name="sharedassets-unity-framing",
    tier="standard",
    title="Make sharedassets0.assets parseable and document the Unity asset framing empirically",
    priority="P1",
    moscow="Must",
    estimate=4,
    context=(
        "F-005 (BLOCKER) and F-009 (MAJOR). work/sharedassets0.assets is a byte-exact concatenation of "
        "extracted/assets/bin/Data/sharedassets0.assets.split0..3 (md5 bfeb8e0caa240991a3fa736c8192adf8, "
        "3,771,600 bytes). The concatenation is structurally correct - split0's header field at +4 equals the "
        "sum of all four splits - but the result has no UnityFS signature and begins with 0x00, so AssetStudio "
        "and stock parsers reject it. SD-CI-001 documents the actual framing: 20-byte header of four "
        "big-endian uint32 (unknown, total logical size, 17 = SerializedFile m_FileVersion, data offset) "
        "followed by a little-endian zero and the null-terminated version string '2018.4.11f1'."
    ),
    ac=[
        "A parser at scripts/parse_unity_assets.py reads a Unity asset file given the documented framing and emits a structured object listing.",
        "The parser reports the file's own header fields and the byte range it treats as the object table, so a reader can check the interpretation against the raw bytes.",
        "Either the parser successfully lists the objects in globalgamemanagers.assets, or it reports which field of the object table it could not validate and why - an honest failure is acceptable, a silent one is not.",
        "work/sharedassets0.assets either gains a valid UnityFS wrapper (with the 0x556e697479465300 signature) that AssetStudio opens, or is renamed to work/sharedassets0.raw-concatenation and documented as raw bytes pending framing.",
        "The report states which of the two happened; it does not describe the file as a Unity asset unless it is one.",
    ],
    notes=(
        "Priority is on the framing discovery being written down and verifiable, not on a complete asset "
        "extractor. The header's first big-endian word (94,582 for globalgamemanagers.assets, 30,216 for "
        "globalgamemanagers, 4,045 for split0) is unexplained and is flagged in SD-CI-001 as open. "
        "The three values are close to the corresponding data offsets, which is a lead worth following but "
        "is not yet a conclusion."
    ),
    deps="none",
    rollback="work/sharedassets0.assets can be regenerated from the splits at any time; the splits are the source of truth.",
    risks=(
        "Unity's split-file layout may not be a simple concatenation. The evidence for concatenation is strong "
        "(header total-size field, md5 match) but the mtime and chunk-boundary semantics are unverified. "
        "The parser must therefore validate the object table before claiming success."
    ),
)

T["T006"] = dict(
    name="reproducible-pipeline",
    tier="standard",
    title="Add a reproducible extraction pipeline with a SHA-256 artifact manifest",
    priority="P0",
    moscow="Must",
    estimate=4,
    context=(
        "F-008 (MAJOR). No Makefile, no shell script, no tool invocation log, no input hashes and no output "
        "hashes exist. A second analyst cannot reproduce, verify or extend any of the findings. The peer "
        "review had to re-derive the metadata layout from scratch, which is what exposed the stride bug."
    ),
    ac=[
        "work/Makefile exposes extract, verify and clean targets, each of which is a single deterministic command.",
        "scripts/manifest.py walks the extracted artifacts and writes extracted/work/MANIFEST.json containing, for every artifact, its path, byte size and SHA-256, plus the SHA-256 and byte size of every input (the APK and the global-metadata.dat).",
        "The input APK's SHA-256 is recorded and matches the file at castlevania-grimoire-of-souls-1-1-4.apk.",
        "make verify re-runs the extractors into a temporary directory and asserts the regenerated artifacts are byte-identical to the committed ones, or reports the specific difference.",
        "Every script has a --help that states the input paths it reads and the output paths it writes, and the Makefile's targets invoke them with explicit paths rather than relying on the working directory.",
        "A README at the project root states the pipeline order, the runtime prerequisites (python3 version, no third-party packages required), and the exact command sequence.",
    ],
    notes=(
        "Keep the toolchain to the Python standard library plus pyyaml. capstone, lief and zstandard are "
        "available but must not become hard dependencies, because a third-party package is the most likely "
        "reason a reproduction attempt fails on another machine."
    ),
    deps="none (but it should wrap the extractors produced by T001, T002, T003 and T005)",
    rollback="Additive only.",
    risks="Byte-identical regeneration requires deterministic JSON: sort keys, fixed separators, no timestamps embedded in the artifacts, and the manifest written to a separate file so it does not hash itself.",
)

T["T007"] = dict(
    name="report-correction",
    tier="standard",
    title="Correct the two analysis reports: numbers, file paths, unsubstantiated claims and the ethics scope",
    priority="P1",
    moscow="Must",
    estimate=3,
    context=(
        "F-004 (BLOCKER), F-010 (MINOR), F-011 (MINOR), F-012 (MINOR), plus the R5 security and ethics gap "
        "raised by the round-1 review. Both reports state 19,843 types, ~212,000 strings, 350+ tables, "
        "libgpg.so at 2.5 MB, and reference work/metadata_summary.json, work/table_catalog.json and "
        "work/method_index.json. The round-1 scope also asserted that Steam Deck analysis with radare2 in "
        "podman had been performed; no radare2 output, no podman log and no Steam Deck artifact exists "
        "anywhere in the project, and the string 'radare2' appears only in the planned-next-steps sections. "
        "Both reports publish a live development WebSocket endpoint without any handling guidance."
    ),
    ac=[
        "Every number in the 'Key Stats' table of both reports is produced by a command in the README and matches that command's output exactly.",
        "The type count reads 20,637, the field count 187,726, and the string count 213,293 heap tokens plus 19,297 literals - each stated with the section it came from.",
        "libgpg.so is stated as 3,718,560 bytes (3.5 MB), matching os.path.getsize on the extracted file.",
        "Every file path listed in the deliverables section exists at that path, and every listed file size matches the file on disk.",
        "All Steam Deck, radare2 and podman claims are either backed by a file in the repository or deleted. If deleted, no trace of the claim remains in either report.",
        "The DMG analysis section states the actual outcome (the file was removed as unusable) or is deleted, and no .dmg path is referenced.",
        "The battle AI state and status effect sections are backed by two new CSV files in work/, each with columns string_value, utf8_offset_in_global-metadata.dat, referencing_type and referencing_field_index, and every row is regenerable by a script in scripts/.",
        "A new 'Security and Ethics' section states: no probing of ws://160.13.90.143:3001/_sys was performed and none will be; Konami assets are not redistributed; intended use is interoperability research; and a responsible-disclosure path is named.",
        "The reports name the exact AES peer-review round that judged them and link to aes/peer-reviews/castlevania-re-1/final-synthesis.md.",
    ],
    notes=(
        "Write the reports LAST, after T001 through T006 land. Every number in them must be quotable from a "
        "command, not typed by hand - that is the mechanism that let 19,843 survive in the first place."
    ),
    deps="T001, T002, T003, T004, T005, T006",
    rollback="Reports are markdown; keep the originals under work/superseded/ until the corrected pair verifies.",
    risks=(
        "The reports are written in mixed Portuguese and English. Preserve the existing language convention "
        "rather than normalising it, so the diff stays reviewable."
    ),
)

T["T008"] = dict(
    name="peer-review-correction",
    tier="light",
    title="Correct the round-1 peer review: the rubric hash, the header-parse finding, and the F-002 error",
    priority="P1",
    moscow="Should",
    estimate=1,
    context=(
        "F-013 (MINOR) and F-014 (MINOR) are synthesis-level findings, and F-002 as filed is partly wrong. "
        "The rubric states sha256 3b3a1c8f9d2e4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9, but the "
        "actual SHA-256 of the rubric file is 815bd730eb726a710b5589fb6c1598696f2ab96eee7a325ffeefa47a9f8911eb - "
        "the stated value is a placeholder, so the rubric was never genuinely hash-committed. F-014: the "
        "synthesis recorded a 'Unity endianness parsed as 13' finding, but the real framing is four "
        "big-endian uint32 in the first 20 bytes (SD-CI-001), so the finding's diagnosis was wrong even "
        "though its conclusion (the file does not open in stock parsers) was right. F-002: the review judged "
        "the report's 213,293 string claim to be unsupported, but the number is correct - the artifact was "
        "incomplete. A peer review that grades a correct claim as false is itself a defect."
    ),
    ac=[
        "review-rubric.md states the real SHA-256 of the file, and the value is verified by running sha256sum on it.",
        "F-013 and F-014 are corrected in final-synthesis.md with the accurate diagnosis for each.",
        "F-002 is amended to state that the reported 213,293 is SUPORTADA (verified against the string heap) and that the defect is the missing artifact, not a false claim.",
        "A correction notice is appended to final-synthesis.md and to the pragmatico findings file, identifying the corrected findings and the reason.",
        "The final verdict is re-stated, and it is unchanged: NÃO APROVADO, because the BLOCKERs were independently confirmed.",
    ],
    notes=(
        "Amend, do not delete. The original findings files are the audit trail and must stay readable; the "
        "correction is additive. A peer review that hides its own errors teaches the wrong lesson."
    ),
    deps="none",
    rollback="Append-only edits.",
    risks="Amending findings after they have been shown to the user could look like moving the goalposts. The correction is to a factual claim about a number, and the verdict does not change - that distinction must be stated explicitly in the notice.",
)

ORDER = ["T001", "T002", "T003", "T004", "T005", "T006", "T007", "T008"]

for tid in ORDER:
    d = T[tid]
    fn = TICKETS / f"{tid}-{d['name']}.md"
    body = f"""---
type: task
okf_version: 0.1
tags:
  - task
  - reverse-engineering
  - remediation
ticket: {tid}
title: {d['title']}
phase: ticket
status: ready
created: {TODAY}
tier: {d['tier']}
requires:
  - aes/kanban.md
  - aes/tickets/{tid}-{d['name']}.md
produces:
  - aes/tickets/{tid}-plan.md
blocked_by: ""
moscow: {d['moscow']}
priority: {d['priority']}
estimate_hours: {d['estimate']}
source_findings: {tid}
---

# {tid} — {d['title']}

## Context

{d['context']}

## Acceptance Criteria

"""
    for i, ac in enumerate(d["ac"], 1):
        body += f"- [ ] AC-{i:02d}: {ac}\n"
    body += f"""
## Implementation Notes

{d['notes']}

## Dependencies

{d['deps']}

## Rollback

{d['rollback']}

## Known Risks

{d['risks']}
"""
    fn.write_text(body)
    print(f"wrote {fn.relative_to(ROOT)}")

print(f"\n{len(ORDER)} tickets written")
