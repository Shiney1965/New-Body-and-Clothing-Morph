# Authority Task 4 — fresh-source audit checkpoint

## TL/DR

The current result is `BLOCKED_SOURCE_AUDIT_INCOMPLETE`, not an exhaustive source exclusion and not geometry admission. All four formerly missing SCO GR2 paths are present in the newly frozen full Scantily package, while the packed VisualBank readback binds each to a ten-object contract containing Netherstone; those contracts cannot substitute for the protected nine-object BCBScantily main.

## Scope and preserved state

- Resumed from `10897cc` with existing untracked `authority_contracts.py` and `tests/test_authority_contracts.py`; neither was reset or discarded.
- Task 4 only. Task 1–3 code, source assets, protected BCB assets/routes, the source freeze, and live/game/save state were not edited.
- No geometry module, conditional geometry candidate, GR2, or PAK was created. The only binary-resource conversion was read-only LSF input to ignored LSX evidence in this worktree.
- The normal Human item requires the exact nine-object main only. The Human skirt and Alt items require that exact main plus the item-specific one-object optional skirt. Seven retained item/race routes remain distinct.

## Exact fresh inputs

Read-only source freeze:

`C:\Claude Projects\BG3 Mods\New-Body-and-Clothing-Morph\.worktrees\clothmorph-everything-else-release\workstreams\release_master_ledger\local\source_pak_freeze_20260902`

| Evidence | SHA-256 |
|---|---|
| `Scantily.pak` — 677360478 bytes | `182A77E669F1576A3B07D29F226161A43F76EA10D8D3EFEE442D36AEA9F7A891` |
| `SOURCE_PAK_COPY_MANIFEST.json` | `84484226DD8751D8092CAB4A2ACD323BC4C94B97D55A088FFD26D6F6C9A2779B` |
| `FRESH_EXTRACTION_SUMMARY.json` | `FCB8931D8D7030DBC7CD49BB011ED089FAE41DE71B378994D3242EEABADC83CC` |
| `listings/Scantily.listing.txt` | `9E778183837C255E481683B0229487BEE7A7450FED5323D0434780E3D5C29400` |
| Canonical manifest of every extracted path, size and SHA-256 | `419C1CF20FF024C4DEFABD8D5618B0842372B1503CB40D1B424D438538AFEE7B` |

The fresh audit reads and hashes all 955 extracted files and verifies exact listing/path/size equality. It records 28 alias queries across every filename/hash and 10 textual/readback inputs, with exact text-line hits and zero-result arrays. Compressed binary contents are not misrepresented as decoded text searches. No source access gaps occurred in this run; semantic audit gaps remain below.

The ignored `local/authority_config.json` retains the previous hash-pinned inputs and adds only the absolute `fresh_scantily_root` key above; SHA-256 `A007180B9F82BDD1F42005890D03116DE14F64D4AD8610680245B0BB3B29E5F6`. Reproduction also requires the two exact ignored readback files below. Missing source/config/readback evidence is a failure, never a fallback to the older partial-extraction conclusion.

## Four geometry rechecks

Paths below are under `extracted/Scantily/Generated/Public/SCO/Assets/`.

| Visual resource UUID | Filename | Exact bytes | SHA-256 |
|---|---|---:|---|
| `a913de25-257e-4e42-a677-c663effbe25a` | `TIF_FS_ARM_Authority_Robe.GR2` | 2201876 | `72B77D45C0D632764C45E5F8440F20FF0BB51D8ED95432790E1262676BC07A0A` |
| `f1f789d3-c09e-485b-8f84-173e41fe9f96` | `HFL_F_ARM_Authority_Robe.GR2` | 2209088 | `36FCF4E18ED7B85FA7759129DFA700E80B0138F73F26B0FE76AD99B69FA5CF42` |
| `9bebc3db-3e3a-4faf-85fe-f19f589c247d` | `TIF_FS_ARM_Authority_Robe_Alt.GR2` | 2244136 | `14DE4F398B93F52C9DF3F6EF973437468265FA4509ADFDCC545715A76B77B573` |
| `94e2bcb1-8c38-4687-9833-c761536f0b0a` | `HFL_F_ARM_Authority_Robe_Alt.GR2` | 2268400 | `C91983FF4E666F3E99705883C29199345DCCCF0274477E7EA761847BC69DB038` |

Each UUID is present in the packed RootTemplates readback and maps to the exact listed path in the packed VisualBank readback. Each VisualBank resource has ten ordered objects and one Netherstone object. This is metadata evidence, not GR2 semantic readback or a proof that an exact nine-object replacement/defect region exists.

## Packed-resource provenance

Tool: `C:\bg3-sidecar-work\Tools\Divine.exe`, SHA-256 `65C47A5050E55F686B55484A901A01D0F1A1D5BA0E776F65FEC71D3E1B2A16B7`.

Action: `-g bg3 -a convert-resource -s <exact frozen LSF> -d <new ignored LSX>`.

Ignored output directory: `workstreams/bard_authority_closure/local/task-4-fresh-readback-20260902/`.

| Source / output | SHA-256 |
|---|---|
| `Public/SCO/Content/Assets/Characters/[PAK]_Armor/_merged.lsf` | `C9AF449B84D27E4136D9ADCCBA5A02CDD324721328A7C974C32E8E88102EDBD5` |
| `visualbank.lsx` readback | `DAF00D2A04FF05C1E0E1B7BD59E9FC559148F46529A66F387E15198F36B7D2EF` |
| `Public/SCO/RootTemplates/_merged.lsf` | `8C51AD9F17AF671EA2DF888DBC729DA3E7D4625EE44D08FC907BD9381DD81C2F` |
| `roottemplates.lsx` readback | `2EC3D885AF511340EEF9F07BDD4B9499A7C9B907C18A5C6962C0D0ACF8262D34` |

## Blocking gaps and integration boundary

The packet names 11 unresolved retained evidence files. They include the four newly available GR2 files lacking semantic/defect-region readback; legacy provider geometry inventory; retained class findings and additional old source aliases; and separator/add-on/SBBF dependency archives with listing-only coverage in this task. Exact absolute paths are retained in `unresolved_retained_evidence_files`; none is silently dismissed because an older alias report asserted an empty unreviewed list.

### Sanitized retained-gap appendix

Task 4 remains **incomplete/blocked**. The full local report is `.superpowers/sdd/2026-09-01-bard-authority-geometry-closure/task-4-report.md`; it records every exact absolute gap path, the observed RED/GREEN history, and the limitations of that history. The table below uses source-relative labels only and does not copy source assets or license text.

| Gap | Retained evidence label | Unresolved reason | Next admissible offline action |
|---|---|---|---|
| 01 | `BCBScantily_BardClassGeneralization_20260826/BCBSCANTILY_CLASS_FINDINGS.md` | Relevant legacy findings were not semantically reconciled to the newly available full source. | Read completely, hash-bind claims and cited inputs, and document which conclusions are supported or superseded. |
| 02 | `BCBScantily_BardClassGeneralization_20260826/evidence/GEOMETRY_INVENTORY.json` | Historical inventory lacks the four newly found SCO paths. | Create a separate old-versus-fresh inventory comparison; preserve the original and reject its use as exhaustive absence proof. |
| 03 | `_sco_unpack/Public/SCO/Stats/Generated/Data/Armor.txt` | Legacy Stats/inheritance alias remains semantically unbound to the current source. | Trace exact item/inheritance/RootTemplate relationships and reconcile source versions. |
| 04 | `_sco_unpack/sco_visualbank_merged.lsx` | Additional legacy VisualBank alias is not reconciled with the packed readback. | Parse and compare UUID, ordered-object, material, and path bindings; retain conflicts. |
| 05 | `task-4-source-audit/sco-addon-archive/SCO-Addon.pak` | Hash and listing coverage do not exhaust packed resource contents. | Fresh isolated extraction, complete inventory, and exact metadata/alias audit. |
| 06 | `Scantily/Generated/Public/SCO/Assets/HFL_F_ARM_Authority_Robe.GR2` | Bytes/metadata present; GR2 semantics and defect region unassessed. | Read-only semantic decode and exact defect evidence; retain the nine-object/no-Netherstone gate. |
| 07 | `Scantily/Generated/Public/SCO/Assets/HFL_F_ARM_Authority_Robe_Alt.GR2` | Alt geometry semantics/defect evidence not admitted. | Independently audit the exact Alt bytes and route; do not substitute normal geometry. |
| 08 | `Scantily/Generated/Public/SCO/Assets/TIF_FS_ARM_Authority_Robe.GR2` | Race/body-specific semantic and defect readback incomplete. | Decode into separate evidence and compare exact component/body boundaries without substitution. |
| 09 | `Scantily/Generated/Public/SCO/Assets/TIF_FS_ARM_Authority_Robe_Alt.GR2` | Exact Alt component/defect contract unestablished. | Audit this exact Alt/race binding; do not infer defect regions or replace protected components. |
| 10 | `SBBF(L) SCO patch Main-4899-1-0-1701827114.zip` | Alternative patch has listing-only coverage, not exact-contract admission. | Fresh isolated expansion, full entry accounting, and source/version-bound resource audit. |
| 11 | `Scantily Outfit Separator-6643-1-8-0-1743296556/Scantily_Separator.pak` | Separator names/components do not prove the required combined garment contract. | Fresh isolated extraction and ordered-component/provider audit; reject merely similar object sets. |

These are proposed audit steps, not work performed in the documentation follow-up. They do not authorize source/live mutation, topology changes, protected-object substitution, geometry admission, or terminal-event attachment. No tests were rerun solely to add this prose; the recorded implementation results below retain their original provenance.

Independent anti-omission review has not occurred in this resumed worker. No canonical release-ledger profile, record, identity digest, or event ID is supplied or invented. The exact module UUID is reported as module metadata only. The writer has no approval/attachment authority.

Consequently:

- `status = BLOCKED_SOURCE_AUDIT_INCOMPLETE`
- `geometry_admitted = false`
- `ready_for_attachment = false`
- `release_blocking = true`
- `exclusion_event_input = null`
- Zero replacement routes and zero protected mutations.

The old ignored `task-4-output*` exclusion-input files are preserved historical artifacts, superseded by this checkpoint. Do not attach them or reuse their synthesized profile/identity fields. The current exclusion writer refuses to emit an exclusion for the blocked real snapshot.

## Deterministic evidence and tests

Two freshly generated packets at `local/task-4-fresh-source-output-20260902/run-1/authority-source-audit-evidence.json` and `run-2/authority-source-audit-evidence.json` are byte-identical: 219974 bytes, SHA-256 `495FA95243BC32F63F96CD154713C02D6E084E54D8D5DC024F4CEC741DEAD739`.

After the final provenance guard, new `run-3` and `run-4` packets were regenerated and compared exactly against each other and `run-1`; the byte count and digest remained identical.

Observed history, without reconstructing unavailable earlier TDD evidence:

- Preserved baseline: 15 focused tests passed. This resumed worker did not observe the original files' pre-implementation RED runs.
- Fresh-source/noncanonical regression round: 5 failures, 12 passes before fixes.
- Packed-readback/source-family/evidence-writer round: 3 failures, 1 pass before fixes; the unavailable-source test covered already-failing-closed behavior.
- Manifest-drift and malformed-evidence round: 2 failures before fixes; both passed afterward.
- Local-config identity relabeling round: 3 failures before fixes, then 3 passes. Source PAK/main/skirt bytes can no longer be relabeled using a changed local expected hash.
- Full workstream suite before the final provenance guard: 91 passed. Final full workstream suite after the guard: 94 passed in 43.18 seconds.

Verification command from the worktree:

`& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/bard_authority_closure/tests -q`

Self-review covered the exact item/skirt matrix, source-family/Netherstone rejection, replacement of old absence assumptions with fresh hashes, complete extracted-manifest drift detection, no fabricated canonical identities, explicit audit gaps, and refusal to write terminal exclusions while blocked. This is not an independent review or a release/gameplay claim.
