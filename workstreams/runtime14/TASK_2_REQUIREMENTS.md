# R1 qualification requirement matrix

Status: implementation in progress; no qualification or gameplay acceptance.
Authority: pass-through specification sections 13.1-13.3 and the normative
SHARED_RUNTIME_LINEAGE_MATRIX.json (digest pinned by contracts/lineage.json).
All test names below are planned obligations until the task report records an
executed result. A source hash or a synthetic fixture is not gameplay evidence.

| Requirement | Production consumer / verification obligation |
|---|---|
| 13.1.1 exact enum, managed cycle | Real Shared, client, MCM, server/API requests; malformed types and labels rejected |
| 13.1.2 schema migration | Real StateSchema7 through bootstrap before events; all schema-6 trusted fields retained, reverted/external, missing originals, legacy claim, family, repeat migration |
| 13.1.3 effective mode | Real central gate for master on/off, explicit External, every transition, pending/partial/blocked health and malformed schema |
| 13.1.4 owned visual merge | Real body writes and OwnershipLedger; exact claims only, later external additions, order, proven removed originals, failed write/readback |
| 13.1.5 baseline trust | Actual capture and bootstrap trust callbacks; Runtime-minted body/ER and wrong CV rejected, trusted saved originals not rejected merely because live value is managed |
| 13.1.6 shared CV | Actual SetBaseBody and fallback CCSV; mixed External/managed and differing managed targets restore shared original, per-character owned fallback |
| 13.1.7 interruptions | Character and ordinary-master journals before each write; every phase reload rolls back/resumes; no ordinary event capability |
| 13.1.8 off preferences | Real console/API/MCM; configuration-only while off, apply latest on explicit enable, External remains External |
| 13.1.9 provider remint history | Task 5 acceptance; Task 2 must retain fields and gate any non-null ProviderTransition, never implement API2 early |
| 13.1.10 rollback preparation | Task 5 acceptance; Task 2 must preserve current refusal and no package-downgrade claim |
| 13.2 managed/External round trips | Vanilla/SBBF/BCB plus mature and Tiefling families with actual Shared/EquipRace/BodyFamily/Targeting code |
| 13.2 multi-character master | Instantiated/unavailable/late records, partial enable success; configured choices retained, exact GUID lists |
| 13.2 lifecycle | Session/load/level events and cross-save process CV writes; every character transition phase |
| 13.2 equip/armour | Actual reconcile, OnEquipped, ReapplyAll and refresh paths; zero gameplay reads/writes while gated, delayed refresh rechecks |
| 13.2 tattoo | Preference persists while off; actual HUM_F reapply skips gated records |
| 13.2 external content preservation | Third-party visuals/status/item identity untouched; no refresh during restore |
| 13.2 registration | Legacy refits/family/revealing queue while off, explicit enable revalidation/one activation; cleanup states reject and never queue |
| 13.2 snapshots | Deep-copy active/queued/rejected descriptor evidence and all normative owner/resource fields; no mutable table leak |
| 13.2 authority | Actual Targeting and network host/owner checks; unauthorized guest master refused and checkbox restored |
| 13.3 static boundary | Syntax, valid MCM JSON, no polling/consumer-specific literals; explicit mutation inventory backed by executable spies |
| 13.3 unchanged assets | Verified composition preserves full R0 protected data/maps and immutable historical R1 bytes |
| public signatures | SetCharacterMode(guid,choice,source)->boolean,status; SetDesiredBody delegates; SetMasterEnabled(boolean,source)->boolean,summary; GetOwnershipStatus read-only |
| top-level schema | Version, MasterEnabled, MutationGateClosed, MasterState, PassThroughRestoreComplete, MasterTransition, CleanupState, CleanupTransaction, Bodies, OptoutTemplates, ProviderDescriptors, BodyTattooPolicy, CleanupAudit |
| body-record schema | Choice, PreferredChoice, OrigBodySetVisual, CvGuid, OrigEquipRace, FamilyOrigEquipRace, OriginalVisuals, OwnedCcsvs, RemovedOriginalVisuals, AppliedCcsv, DesiredCcsv, ClothedChoice, BodyFamilyId, FamilyClothedChoice, Transition, RestoreState, RestoreFailures, ActiveProvider, ProviderTransition, HistoricalOriginals |
| ownership claims | ProviderId, OwnerModuleUuid, ProviderDigest, ResourceKind, AddedForCvGuid; active descriptor binding, failed writes never gain ownership |
| versions | R1 package 1.3.1.0 / 36451011631513600, code v4.22-s7-foundation, schema7, SE20, PassThrough1, ExternalRefit1, BodyFamily1, Snapshot1, Cleanup0 |

## Immutable input and harness notes (Task 1 Minor findings)

Read-only hard-linked input files are supported when their actual content passes
the complete verification. Symlinks and Windows reparse redirects are rejected.
This is not a claim of unique input-file ownership; inputs must still be rehashed
before and after composition. It grants no mutation authority over other links.

The hashes of harnesses in the immutable lineage contract identify the historical
copied input files, not their adapted current versions. Current adapted harnesses
are recorded separately in contracts/adapted_harnesses.json, computed from actual
tracked bytes. Historical pins are never rewritten to make qualification pass.

## Executable trace and remaining boundaries

The exact-source runner freezes the current harness files and their SHA256
receipts, then composes an independently verified source stage. The evidence JSON
records each suite's actual result. This trace identifies coverage, not a waiver
or a claim that a single synthetic engine fixture proves all possible gameplay.

| Requirement group | Executable evidence / status boundary |
|---|---|
| enums, signatures, authority, feedback, versions | `test_r1_production.lua`, `test_r1_client.lua`, `test_r1_diagnostics.lua`, `test_r1_controls.py` |
| migration, top-level/body schema, original trust, recorded legacy claim | `test_r1_schema.lua`, production migration/CV cases; saved AppliedCcsv plus saved CvGuid only, including accepted provider/absent resource cases |
| ownership merge, shared CV, fallback retirement | production shared-CV cases, `test_r1_master_journals.lua`, `test_r1_master_resume.lua`, `test_r1_native_visual_timing.lua` |
| ordinary interruptions, failed restoration/readback, late characters | `test_r1_failure_matrix.lua`, `test_r1_master_journals.lua`, `test_r1_master_resume.lua`; non-null provider transitions remain gated |
| ordinary off preferences and re-enable | production/master/journal suites; queued provider activation precedes character apply |
| mature/family managed behavior | `test_r1_managed_regression.lua`, genuine accepted provider execution in `test_r1_registration.lua`; geometry/gameplay NOT_RUN |
| mutator/event/delay gates, tattoo, debug | `test_r1_mutator_inventory.lua`, `test_r1_event_matrix.lua`, `test_r1_debug.lua`, production timer/tattoo cases |
| equipped identity across pending refresh | **UNRESOLVED RED** `test_r1_pending_refresh.lua`; gating a delayed re-equip alone leaves an item unequipped; no acceptance or exclusion |
| native CCSV timing | native add deferred in fixture; RED 1/3, 2/8, then propagation/rollback RED 8/11; final source-backed synchronous append and proven-write rollback cases 11/11 in receipt `5df5dd83c5434f88983eaa2c3d4948f1` |
| queued legacy metadata / exact callers / snapshots | `test_r1_registration.lua`, `test_r1_external_legacy.lua`; legacy unknown owner stays empty string + ownerUnresolved, never v2/cleanup assurance |
| cross-save process mappings | registration cases distinguish persisted ACTIVE from process activation, fresh exact-descriptor reattachment, and saved conflicting digest/owner restart requirement; exact mutation spies |
| protected source and embedded maps | `test_qualification.py`, `test_qualified_exact.py`, original provenance integrations; historical R0/R1 unchanged |
| 13.1.9 provider remint/reverse transaction | **DEFERRED_TO_TASK5**; Task 2 only preserves/validates fields and gates ordinary entrypoints; not passed |
| 13.1.10 full rollback preparation/qualification | **DEFERRED_TO_TASK5**; current refusal/rollback-prepared gates retained; not passed |
| independent review / release | **NOT_ACCEPTED**; mandatory review and unresolved refresh resolution before Task 3; no PAK or gameplay claim |
