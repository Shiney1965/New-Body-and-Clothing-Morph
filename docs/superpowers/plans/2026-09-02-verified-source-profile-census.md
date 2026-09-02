# Verified Source Profile Census Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Implement each task with independent task review and strict TDD. This is a source-evidence stage, not completion of the whole release.

**Goal:** Produce a source-complete, hash-bound census from exact package snapshots without flattening ordered race/component routes, omitting unresolved creation paths, or confusing character-creation accessories with garments.
**Architecture:** Validate immutable package/extraction snapshots first; consume hash-bound original or converted resource banks; parse source definitions into lossless normalized records; resolve creation paths with explicit dependency gaps. Emit census and profile candidates with data-derived completeness, then hand them to canonical-ledger integration as a separate reviewed step.
**Tech Stack:** Python 3.12, standard-library JSON/XML/hash handling, pytest, retained pinned Divine conversion manifests.
**Spec:** `C:\Claude Projects\BG3 Mods\ChatGPT Work Files\ClothMorph_Shippable_Release_Program_20260830\docs\superpowers\specs\2026-08-30-clothmorph-shippable-release-program-design.md`, sections 7–9, 12–14 and 19.

## Global Constraints

- No live/profile/save access, PAK installation/activation, protected mutation, source modification, or network operation.
- Public code/tests are portable; real source copies and outputs remain in ignored `workstreams/source_profile_census/local/` or read-only referenced existing frozen evidence.
- The existing frozen source directory is a read-only input: `workstreams/release_master_ledger/local/source_pak_freeze_20260902`.
- Runtime/provider artifacts and garment source modules are different roles. Do not silently drop historical provider evidence or call a provider PAK a garment source.
- No filename/display-name inference of body tuple, slot, source-native mode, transformation class, or permission.
- Preserve every ordered component and EquipmentRace MapKey binding, including duplicate references when the source contains them.
- Unresolved parents, unsupported formats, conflicting definitions, missing banks/dependencies, and unbound permission evidence are explicit blockers—not empty successful results.
- A complete byte/source census does not imply complete route, geometry, permission, package, or gameplay acceptance.
- Do not alter the current master ledger, its config, or record IDs in this stage. Canonical migration needs an explicit old-observation-to-new-identity map and a subsequent integration review.

## File responsibilities

- `snapshot.py`: immutable verified package/extraction/config input boundaries.
- `resources.py`: lossless normalized XML bank and Stats definitions with source locators.
- `creation_paths.py`: ordered route, inheritance, and character-creation joins.
- `generate.py`: deterministic census, profile-candidate completeness, and raw anti-omission output.
- Tests mirror those responsibilities; `local/` is ignored.

### Task 1: Verify frozen package snapshots

**Files:** create `workstreams/source_profile_census/{__init__.py,.gitignore,snapshot.py,tests/test_snapshot.py}`.

**Interfaces:** `load_snapshot(configuration: Mapping[str, object]) -> FrozenSnapshot`. The immutable result contains module metadata, verified package digest, exact original file byte snapshots/locators, full listing/content-manifest identities, and explicit dependency metadata. Config identifies expected SHA-256 values for the package, content manifest, listing, and conversion manifest; no caller-supplied success flags.

- [ ] Write RED tests using temporary files: a valid two-file snapshot; changed byte; missing/extra extraction entry; wrong listing size; duplicate/case-colliding path; escaped path; missing metadata; conflicting UUID/version for one declared profile; conversion output with mismatched original hash.
- [ ] Run `python -m pytest workstreams/source_profile_census/tests/test_snapshot.py -v` and record expected missing-module/behavior failures.
- [ ] Verify hashes before parsing and retain the verified bytes. Compare complete listing, manifest, and filesystem path sets; verify every file hash and size. Read exact module UUID/Folder/Name/Version64 and ordered Dependencies from meta.lsx. Declared role is checked against its metadata/configuration, never inferred from filenames.
- [ ] Reject changed/relabelled inputs with stable codes; do not follow arbitrary embedded live paths.
- [ ] Run GREEN, self-review, and commit Task 1 only.

### Task 2: Parse complete definitions without silent omission

**Files:** create `resources.py`, `tests/test_resources.py`; extend snapshot exports only as needed.

**Interfaces:** `parse_resources(snapshot: FrozenSnapshot) -> ResourceCensus`. Each definition retains package identity, original relative path/hash, conversion hash if applicable, record locator, type, complete attributes, and ordered child structure. The census lists every input file as parsed, non-definition asset, or explicitly unsupported/unresolved.

- [ ] Write RED fixtures for VisualBank ordered Objects/materials; CharacterVisual maps; RootTemplate item without local Stats; duplicate resource ID conflicts; Stats `type`, `using`, `data`; missing and cyclic inheritance; source text carrying Unicode or CRLF; material/texture banks; unknown region and binary input lacking a verified conversion.
- [ ] Include a literal two-component route fixture whose reordered/deduplicated references fail the expected ordered result.
- [ ] Implement XML parsing from verified bytes. Converted inspection bytes are accepted only with their original-to-inspection hash mapping and pinned converter provenance. Do not parse a bundled stale textual duplicate as if it were the packed LSF without recording its role and contradictions.
- [ ] Parse every named Stats entry, preserve type/inheritance/all data, and record duplicate definitions with source precedence evidence or an explicit unresolved conflict.
- [ ] Run focused GREEN and snapshot regression tests, self-review, commit.

### Task 3: Resolve concrete creation paths and non-garment scope

**Files:** create `creation_paths.py`, `tests/test_creation_paths.py`.

**Interfaces:** `resolve_creation_paths(census: ResourceCensus, dependencies: Sequence[ResourceCensus]) -> CreationPathCensus`. Results preserve source observation IDs and separate root-template, named-Stats, inherited-spawn, body-family, and character-creation observations. This raw census does not assign final release-ledger IDs.

- [ ] RED: one root with two EquipmentRace keys and ordered two-component MapValues must produce distinct exact route bindings; a named Stats path that shares the root but has another inherited Slot remains a separate creation path.
- [ ] RED: an unresolved parent still emits a discovery observation and stable blocker; it is never skipped.
- [ ] RED: a character-creation accessory set joins through SharedVisual UUID to VisualBank and mesh path/hash; Piercing records are typed non-garment observations, not clothing refits.
- [ ] RED: named Stats inheriting RootTemplate, conflicting parent definitions, cycles, direct VisualTemplate plus mapped variants, and missing VisualBank/source file all preserve their exact evidence or blocker.
- [ ] Resolve only explicit source/dependency relationships; body tuple absent from exact EquipmentRace/body evidence remains unresolved. Root/display prefixes are diagnostic hints only.
- [ ] Preserve independently discovered input observation IDs and source relationships so later ledger integration can prove exact-once coverage.
- [ ] Run focused/full census tests, self-review, commit.

### Task 4: Generate current census and profile candidates

**Files:** create `generate.py`, `tests/test_generate.py`, `tests/test_local_integration.py`, `PUBLIC_CHECKPOINT.md`; ignored `local/config.json` and fresh named output directories.

**Interfaces:** `generate_census(config: CensusConfiguration) -> CensusResult`. Emit deterministic source snapshots, raw definitions/creation paths, complete input manifests, source-profile candidates, and anti-omission sets. Profile contract uses parent section 7.1; unavailable binding fields never receive invented hashes.

- [ ] RED: dropping any raw discovery row appears in `missing_from_census`; an extra output path appears in `census_without_source`; permission and dependency incompleteness keep `release_profile_complete=false`.
- [ ] Require complete section-7.1 fields and exact permission-evidence/version bindings before emitting an admissible source-profile contract. If incomplete, emit a candidate plus named blockers, not a completed profile with placeholder authority.
- [ ] Freeze all ten controller-provided source copies; reuse complete per-file manifests. Sources without verified conversion coverage remain explicitly incomplete. Add other core retained source packages only through the same exact manifest boundary—never substitute an older extraction by name.
- [ ] For Etheirys, independently reproduce all 164 binary-bank definitions, 61 accessory sets, 70 shared-visual joins, 42 distinct GR2 names, and the two unreferenced mesh names recorded in the controller audit. These are exact-source regression controls, not inferred garment routes.
- [ ] For SCO, compare all fresh packed RootTemplate/VisualBank entries to the old registry input and enumerate additions/changed relationships rather than retaining the old flattened population as authority.
- [ ] Generate twice from an unchanged input/code snapshot and compare exact bytes. Preserve previous outputs; refuse overwrite.
- [ ] Record exact current counts, hashes, unresolved inputs/permissions/dependencies, and next canonical-ledger integration requirements. Run all census and existing release-ledger regressions, self-review, commit public code/tests/checkpoint only.

## Completion boundary

This stage is complete only when the public pipeline has independent review and the current census truthfully accounts for every configured source entry. It does not complete the release goal, attach exclusions, or permit packaging. Canonical ledger migration, source-scope events, remaining source profiles, Runtime 1.4, mesh correction, packaging and gameplay remain required.
