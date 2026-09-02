# Alfira physical dependency correction and Runtime integration gate

## TL/DR

Fresh inspection of the exact accepted Tiefling PAK disproves the earlier assumption that it bundles the BCB body mesh. The provider owns its BCB CCSV and VisualResource definitions, but the VisualResource's physical mesh is an external BCBPak path; the dependency-free Python adapter is therefore not approved for Runtime integration or a playable-fix claim.

The same accepted bootstrap explicitly requires BodyFamilyApiVersion 1, while the normative shipping Runtime requires 2. A retained legacy hook alone is insufficient: a tested compatibility bridge is required without modifying the accepted PAK or lying about the global API version.

## Authority and scope

This correction supersedes only the erroneous physical-ownership/dependency-free assertions in the 2026-09-01 Alfira profile-decoupling design and its offline Task 2 model. It does not modify that worktree, the accepted provider, the separate Tiefling closure project, the BCB cleanup project, a protected route, or a user save. Ordinary Tiefling Tav gameplay acceptance remains valid for its tested environment.

The user objective remains a functional Alfira/whole-mod test package or a valid evidence-backed terminal disposition. Rejecting the incomplete adapter is an intermediate correction, not a substitute for solving Alfira and not evidence of impossibility.

Normative Runtime authority remains `ClothMorph.SharedRuntimeLineage.2026-08-30.r1`, matrix SHA-256 `5134237A6AD8F6F5BDB1721EE279A07A336727F9E88119CCB3B4B320D9D19A67`. R2 retains package 1.4.0.0, Version64 36591746972385280, code v4.23-api2, schema 7, SE 29, BodyFamily API 2, and Cleanup API 0.

## Fresh artifact evidence

Controller read-only inspection date: 2026-09-02. The source PAK was hashed, copied to a new ignored directory, and source/copy hashes were checked equal. Divine list-package, fresh extraction, and VisualBank LSF-to-LSX conversion operated only on retained/copied artifacts.

| Artifact | SHA-256 |
|---|---|
| Accepted provider PAK, 844122 bytes | `01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141` |
| Fresh extracted provider BootstrapServer.lua, 3048 bytes | `1BFF821977E5BF71B79ADE5AD01B91D17CEBB979BFFAE4B0DB882AF7620975BE` |
| Fresh extracted packed VisualBank, 5976 bytes | `E3D14FF497DDBD2EA2ACEC189521763B1827366698D7300E795791B4CBE0D691` |
| Converted VisualBank readback | `4155663170F99A397FB9AE3B03DB0D62D9374A9D71C76474B067285975C354CC` |
| Divine.exe | `65C47A5050E55F686B55484A901A01D0F1A1D5BA0E776F65FEC71D3E1B2A16B7` |

Local evidence is retained under `.superpowers/research/runtime_reference_20260902/`: `DEPENDENCY_PROBE.json`, `accepted_visualbank.lsx`, `accepted_provider/`, the copied accepted PAK, and `probe_legacy_api.lua`. These ignored source extracts are not public distribution payloads.

### Physical mesh dependency

The accepted PAK lists exactly seven files. Its only GR2s are:

- `Generated/Public/ClothMorphTieflingBT1Test/Assets/Bodies/Vanilla/TIF_F_NKD_Body_A.GR2`
- `Generated/Public/ClothMorphTieflingBT1Test/Assets/Bodies/SBBF/TIF_F_NKD_Body_A.GR2`

BCB VisualResource `eab8e30e-0207-58d8-8764-e3b4477133fa` has this exact SourceFile:

`Generated/Public/BCBPak/Assets/Characters/_Models/Tieflings/_Female/Resources/TIF_F_NKD_Body_A.GR2`

The provider-owned CCSV `eca05d33-9887-5d5e-868a-8be722c2eb12` and VisualResource definition do not imply ownership or availability of that external mesh. A successful VisualResource lookup alone is not physical dependency closure.

Fresh complete package-list checks found:

| Exact package | Listed entries | Exact BCBPak mesh path present |
|---|---:|---|
| Accepted Tiefling provider, SHA 01E96CF2... | 7 | No |
| Accepted R0 Runtime, SHA 6610090C... | 739 | No |
| BCBPak, SHA ABB53996... | 706 | Yes, 467892 bytes |
| BCBUniqueTav, SHA 0E08D6D8... | 425 | No |

BCBUniqueTav contains a differently named source path and a unique-Tav path. Those paths do not satisfy the accepted provider's exact BCBPak path merely because their filenames or byte counts resemble it. Fresh hashes of retained, previously extracted comparison meshes are distinct:

- BCBPak mesh: `CBFA7E6F53761DCD48D059FD76C66A5C8FE0E51D9CCBB57DD8D5981EE37D3419`.
- BCBUniqueTav mesh: `C7BEBE8FA6B11CB2F7441FD93B4D88A0314CC4E7B07AC02297415446082ED90A`.

These comparison meshes were rehashed, not freshly re-extracted by this probe. No claim is made about every currently installed source, its winner, loose overrides, or save-state cause.

### Actual legacy call contract

The extracted accepted bootstrap declares `requiredModUuid` as the actual UUID `1d24059d-ff23-4a79-8892-57c85d512416`, not the string `BCBPak`. The older Python constant named `BCBPAK_REQUIRED_MOD_UUID` uses the symbolic name and must not be represented as exact Lua descriptor evidence.

The accepted bootstrap tests `tonumber(runtime.BodyFamilyApiVersion) ~= 1` before registration. Executing the exact extracted script against isolated Lua mocks reproduced:

| Advertised BodyFamilyApiVersion | Observed calls | Warning count |
|---:|---|---:|
| 1 | body registration, family-refit registration, reapply | 0 |
| 2 | none | 1 |

This is an executable bootstrap-contract result, not game rendering or save evidence. The warning includes the exact phrase `paired Runtime body-family API v1 is unavailable; provider disabled`.

## Required implementation corrections

1. Distinguish definition ownership, transitive physical asset availability, exact source profile, and permission. None substitutes for another.
2. Correct the Python descriptor to the actual UUID and replace unconditional BCB-body availability with evidence-backed dependency closure. Keep the prior result as superseded diagnostic history, not a current passing-fix claim.
3. Keep the accepted BCBPak-present body/garment routes and accepted PAK bytes unchanged. No BCBUniqueTav impersonation, in-place accepted VisualResource replacement, or third-party path overwrite is permitted.
4. Investigate a source-independent correction only in new provider-owned resource namespaces after exact body/component/material/skin/dependency and permission proof. Missing permission is not proof of prohibition; missing fit evidence is not impossibility.
5. Implement and independently test an exact legacy bridge under globally truthful BodyFamilyApiVersion 2. A native import of a build-verified, exact allowlisted legacy descriptor is a candidate architecture, not yet implemented or accepted. Unknown legacy owners remain rejected; no temporary global API downgrade, polling, or accepted-bootstrap patch.
6. Runtime observes module UUID/version and resource contracts. Offline verification observes physical PAK/content hashes. Do not claim Runtime Lua independently hashes an installed PAK.
7. Test the genuine extracted bootstrap, actual provider resource metadata, and real Runtime Lua control flow in addition to pure Python models. Retain public synthetic tests and opt-in exact-source tests with explicit, distinct provenance.

## Unresolved evidence and next actions

- Full transitive BCB body asset/material/skeleton/softbody ownership graph and the exact active source winner remain to be bound.
- A permitted, source-independent BCB target and exact new resource/route identity have not been established.
- Alfira's dedicated failure save has not been inspected. On the current controller process check BG3 and BG3ModManager were running; no save operation was attempted.
- The same-mod-list Tav observation remains user evidence, not proof that Alfira and Tav use the same body path or persistent state.
- Alfira outfit geometry remains a separate unresolved workstream.
- No source exclusion, geometry exclusion, gameplay pass, install authorization, or finished package follows from this correction.

## R1 reuse boundary

The separate cleanup worktree was read only and remains clean at `cf62d7fe2953bdda376c2d6df94c3968dc97ec07`. Its designated pure R1 overlay has twelve files matching the declared manifest; manifest-file SHA is `DEAFCB8734AB3558D490253BD00F99226179BEB758F6277BAC62A27A2B70DD0A`. Its Task 1 progress records a narrow review-clean checkpoint at `26e479c`.

That is reference/provenance evidence, not full shippable-R1 or R2 acceptance. Actual source inspection shows legacy body registration is guarded separately from the external-provider registry, and the MCM choice is `External` rather than the pass-through specification's exact `External / Pass-through`. A fresh full-contract Runtime review and real-Lua regression suite are required before reusing the pure foundation. No R1C cleanup functionality or separate cleanup task state may be imported or changed.
