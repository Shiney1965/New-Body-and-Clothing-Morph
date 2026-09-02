# Exact-source census public checkpoint — 2026-09-02

## TL/DR

The exact-source generator accounts for all 2,970 configured files across ten immutable source packages and emits 3,062 raw definitions plus 6,681 creation observations. The final repeated outputs are byte-identical, but all ten profiles remain incomplete candidates: this is a source-evidence checkpoint, not a release, permission, geometry, gameplay, or canonical-ledger completion.

## Scope and current counts

Source authority is the hash-bound retained freeze at `workstreams/release_master_ledger/local/source_pak_freeze_20260902`, with the original and controller-provided conversion manifests. No older extraction is substituted for a current source. The old SCO registry's explicit RootTemplate and VisualBank files are comparison-only inputs.

| Exact metadata name | Input files | Binary-bank files / verified conversions | Raw definitions | Creation observations |
|---|---:|---:|---:|---:|
| SMH_Gloomstalker_Gear | 14 | 2 | 45 | 328 |
| Scantily Camp Outfit | 955 | 4 | 2057 | 2310 |
| Clavicula Nox | 327 | 105 | 132 | 668 |
| Etheirys Exports | 365 | 164 | 301 | 131 |
| Critical Hit | 185 | 65 | 80 | 105 |
| Fashion in the streets - Dishonored 2 outfits | 632 | 176 | 265 | 1952 |
| Lord Protector - Corvo Attano's outfit | 118 | 33 | 40 | 220 |
| The Brigmore Witch - Delilah Copperspoon's outfit | 123 | 34 | 45 | 490 |
| Shadar-Kai Outfit | 25 | 15 | 27 | 227 |
| Reaper Doll | 226 | 59 | 70 | 250 |
| Total | 2970 | 657 | 3062 | 6681 |

Every file is accounted for even when unsupported. All 657 configured binary-bank files have verified conversion coverage; this does **not** mean their schemas or relationships are completely understood. Unsupported XML regions/structures, Stats statements, duplicate/conflicting definitions, missing parents, unresolved visual resources, unresolved body tuples and other issues remain present in `UNRESOLVED_EVIDENCE.json`.

The raw anti-omission audit has empty `missing_from_census`, `census_without_source`, `duplicate_source_rows` and `duplicate_census_rows` sets. Duplicate *resource IDs* remain retained independent observations and are not hidden by that unique-observation audit.

## Exact-source controls

Etheirys reproduces **164 binary-bank files**, **61 accessory sets**, **70 shared-visual mesh joins**, and **42 distinct GR2 names**. The independently calculated definition population is **301**: 61 CharacterCreationAccessorySet, 70 CharacterCreationSharedVisual, 70 VisualBank, 33 MaterialBank and 67 TextureBank. The only mesh *names* unreferenced by observed VisualBank SourceFile values are `PRC_Luminiari_Historia_Dyeable_L.GR2` and `PRC_Luminiari_Zormor_L_Tintable.GR2`; unmatched duplicate *paths* are reported separately. These are raw source-name observations, not geometry failures or proven absence of all possible engine references.

Etheirys uses the neutral explicit `source` role. Its creation observations are `NON_GARMENT_PIERCING`, not approved exclusions or garment routes. The controller approved this narrow addition to the snapshot role enum; existing garment_source/provider/runtime/dependency roles remain supported, and no role grants route or release eligibility.

SCO retains **1,714 fresh RootTemplate/VisualBank occurrences** (262 RootTemplate and 1,452 VisualBank), compared with **857 legacy occurrences**. All occurrences—including packed XML and separately converted binary definitions—remain visible. Of **854** grouped population changes, **835** are multiplicity-only and **19** also differ in retained content. The one added key is malformed `VisualBank/null`; the one missing key is malformed `VisualBank/""`. These are not asserted new/removed valid resource UUIDs. There is one duplicated legacy identity group and 855 duplicated fresh identity groups. Nested structure, ordered attributes and the full before/after populations are retained; no precedence winner is inferred.

## Profile/permission boundary

Candidate fields use section 7.1 of the parent release design. Exact module metadata, PAK hash, content-manifest hash and observed Root/Stats/VisualBank digest are populated from verified inputs. Canonical profile IDs, supported body tuples, forbidden-module authority, permission evidence/credit/restrictions and route-partition authority remain unresolved, with unavailable fields left null rather than fabricated hashes.

A supplied hash-pinned contract can be inspected for syntax and exact observed bindings, but cannot self-authorize: this stage has no independently approved permission-scope, body-map, precedence or canonical-profile authority validators. `admissible_contract=null`, `release_profile_complete=false` and `release_complete=false` remain explicit even for syntactically complete supplied documents.

Eight source modules declare GustavX UUID `cb555efe-2d9e-131f-8195-a89329d218ea`; that dependency is not in this configured ten-source set. Base-game aggregate/multi-module packages are not forced through the one-module reader. Missing declarations/references are unresolved inputs, not claims that the dependency is absent from any installation. Exact version equality is an evidence check, not an inference about the engine's dependency-version semantics.

## Reproducible local evidence

Final config: `workstreams/source_profile_census/local/task4_neutral_source_20260902/config.json`, SHA-256 `D343F992AC53E2252C95BE5E88EA56F2FCCE0579356B16D03773E68C55D9442F`.

Final fresh output directories:

- `workstreams/source_profile_census/local/task4_neutral_source_20260902/run_a`
- `workstreams/source_profile_census/local/task4_neutral_source_20260902/run_b`

Both were generated from unchanged production-code/input snapshots. Exact file bytes, full output path sets, output-manifest sizes/hashes, raw-file/definition/creation accounting, Etheirys controls and all input hashes were checked in the full regression run. Prior configs and probe/verified outputs remain preserved; generation refuses any existing output directory.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `CENSUS_AUDIT.json` | 83216 | `A7F027172DF98A9BF9F14F9D42C46E7B47EB09636B176A5BBD3C39696B4BE93E` |
| `INPUT_MANIFEST.json` | 3077255 | `CDEC2597F6E7C467233D09930DB7B13DF008F666844A5D648A150953E1EF28CF` |
| `LEGACY_COMPARISONS.json` | 246430586 | `1C6B98D2BE07B05309B866BA1B343BC60D183B0BFE677893FE9520D2D6920F0E` |
| `RAW_CREATION_PATHS.json` | 54527385 | `AEA05E9A606D49BB1B70952419BC84577280C5F9BDB17AEDE9D4B68E317B66DA` |
| `RAW_DEFINITIONS.json` | 159874656 | `870F7442665C42581A25352830100BB967E6581B3CD62F83A62730E6AED23AEE` |
| `RAW_FILES.json` | 231000874 | `9D7B394548B2E247E31FF6D88D1A236ED3B99204B761469265AF6827BC8E26A1` |
| `SOURCE_PROFILE_CANDIDATES.json` | 28345 | `C9A28F9BD8DF561C1DF82D010B7631C2ECDD627EF032C302383ECE994695B948` |
| `SOURCE_SNAPSHOTS.json` | 2918785 | `15C8312919ADE407DCD62E536F2199DF475E5F94488EE23CB9CA8D5178FBC0F4` |
| `UNRESOLVED_EVIDENCE.json` | 14802751 | `C79DF6D181C60254EAF66B8B920BC451943C87359D464C6FFCD21342CA905358` |
| `OUTPUT_MANIFEST.json` | 1461 | `749EE12F97AB4FD9E0AC69F617DEE465309D8ABBBF6E3FDF4777D491C95A2F6C` |

The complete per-file input manifest includes package, content-manifest, listing, every source file, every conversion manifest/inspection, explicitly selected legacy/supporting inputs and the production Python modules. Normalized configuration is also bound, excluding only the output leaf for repeatability. Original source payloads remain in their retained freeze; JSON snapshots carry exact locators/hashes/sizes instead of duplicating binary payloads.

## Frozen package hashes

| Exact metadata name | Version64 | PAK SHA-256 |
|---|---|---|
| SMH_Gloomstalker_Gear | `36028799166447616` | `8A039D59AA301357D42A1E10879D4342C3D95703C91D92612579D0EB87E19341` |
| Scantily Camp Outfit | `72057772279070722` | `182A77E669F1576A3B07D29F226161A43F76EA10D8D3EFEE442D36AEA9F7A891` |
| Clavicula Nox | `36028797018963969` | `04F8E78A4E45AAE56F205FFCD1CD0EAC80EAA02108D786196AF45B4D16A3FF3F` |
| Etheirys Exports | `36028797018963971` | `29C81F71982B4FF651CFDE0E3C13E267C0E6AC3224CB024BE21FCAD2DDFB4733` |
| Critical Hit | `36028797018963969` | `C1E4376B8A0B3A5B511C88384A0C4BB1A8AD5FCBFE4EF5250396E43520171909` |
| Fashion in the streets - Dishonored 2 outfits | `36028797018963974` | `EE62B631B1FCE830E5252F19CF5309B6F1DE0860EC1817F6986629A0B2D18898` |
| Lord Protector - Corvo Attano's outfit | `36028797018963974` | `FB909D2957ED9F414AB39DFA3089A0FB9381446EA8DF22ED27738ED0BBD30FD4` |
| The Brigmore Witch - Delilah Copperspoon's outfit | `36028797018963972` | `2D77701703FA2E7D2A76A4C89E8D5DDAE5890926E57CEAC426556393CB82CA26` |
| Shadar-Kai Outfit | `36028797018963978` | `DDFD704E0E895DE5421B6449123CC3BAFD3190BE63376F646F46BFD4E258A1FD` |
| Reaper Doll | `36028797018963969` | `D84F1DC59C4B227EE9B735A278E30B4086DA9E557089B024FC19E78D6F268B56` |

## Verification and next gate

Precommit regression command, with `CLOTHMORPH_CENSUS_RUN_A` and `CLOTHMORPH_CENSUS_RUN_B` set to the final output directories:

`python.exe -B -m pytest workstreams/source_profile_census workstreams/release_master_ledger workstreams/coverage_ledger workstreams/true_underwear workstreams/vanitybody --import-mode=importlib -q -p no:cacheprovider`

Result: **655 passed, 13 existing skips in 29.07s**, exit 0. Importlib collection is required because the prescribed local-integration filename is also used by an existing workstream; no cache deletion or unrelated configuration changes were made.

Independent review of this stage is still required. Subsequent work must supply remaining exact source profiles and accepted authority validators, explicitly migrate old observation IDs to canonical identities, review source-scope events and anti-omission mappings, and then address Runtime 1.4, mesh correction, packaging and gameplay. Current ledger/config/IDs/events and all protected/live/profile/save state remain untouched.
