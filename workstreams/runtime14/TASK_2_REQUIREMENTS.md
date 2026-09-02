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
