# Task 2 fix round 1 - partial checkpoint

Status: six bounded independent-review findings corrected and individually
verified; Task 2 NOT COMPLETE. Review base is
`e4abe5af13c803f0f133285cad4a7fed0d47cc19`.

## Finding dispositions

| Finding | Disposition / focused result |
|---|---|
| MCM origin-free master relay | OPEN, approval-dependent; related body-choice relay also reproduced; 0/2 RED |
| Persisted-only ACTIVE provider claims | Corrected: process digest and fresh dependencies required; detached snapshots distinguish saved evidence; 4/4 |
| Master enable erases rollback blocker | Corrected: preserve inner health/journal/failures, append summary; 1/1 |
| Cross-save restoration ignores readback | Corrected: exact readback before retiring process ownership, warning and retry on failure; 1/1 |
| First-use shared-CV baseline | Corrected: only exact still-owned process original is eligible; stale/arbitrary minted controls; 3/3 |
| Schema invariants/history/maps/enums | Corrected: nullable archived originals preserved, effective history bound, contradictory state rejected; 22/22 |
| Printed master-status GUID lists | Corrected: actual output and exact classifications tested; 1/1 |
| Pending equipment refresh | OPEN, 0/4 RED; mature/family paths with External/master-off |

The source-backed MCM options and integration requirements are in
[MCM_AUTHORITY_REVIEW.md](MCM_AUTHORITY_REVIEW.md). No UI change, disabling of the
old control, private widget interception, rebroadcast-derived identity, delayed
Off/External, equipment-write exception, or removed functional refresh was
implemented. The unanswered layout question covers both master and body controls.

## Covering verification

One covering combined run completed **1 failed, 480 passed, 15 skipped in
119.59 seconds**. The single failed aggregation reports both known RED surfaces.
The review suite is **32/34**; only its two MCM cases fail. All prior implemented
production suites pass, including CCA timing/propagation **11/11**. Pending
refresh remains **0/4**, not skipped.

Exact receipt on the originating workstation:
`local/stages/qualified/4760ae2db1d643b29d7999d4786f00d7.evidence.json`.
It binds **746 files**, **21 syntax successes**, **zero harness drift**, and
qualification contract
`0993490FC6E3880DB8DF791496E65D9AEBDA52C08ED7BEB6E06EBC8A8917914B`.
Gameplay remains NOT_RUN. Full per-defect commands/stdout/stderr and complete
combined Lua outputs are appended to the local SDD `task-2-report.md`; each focus
also has an exclusive `review-*.focus.json` receipt. The current regression file
also reproduces the unfixed baseline after a complete 746-file manifest check.

## Scope and self-review

Production changes this round are confined to qualified `BootstrapServer.lua`,
`MasterState.lua`, `ProviderRegistry.lua`, and `StateSchema7.lua`, plus their
separate allowed-delta hashes. Test runner, regression, and evidence docs are
source-only. Historical R1/lineage, embedded maps, accepted provider/routes and
pending-refresh production paths have no change in this round. All actual stage
compositions reverify historical inputs. No separate project, live game/profile/
save, application, network or PAK action was performed.

Self-review checked claim admission versus historical restoration; retained
failure codes versus summary; failed-write retry; exact process-baseline binding;
nullable history versus trusted originals; inactive history versus current
provider; printed diagnostics; and complete reporting of unresolved failures.

Required next work: scoped independent review of this fix diff, approved MCM
interaction implementation, and a valid pending-refresh resolution. Task3/R2
remains held. Full remint/reverse/rollback qualification stays mandatory Task5.
The source-only reverse path's no-provider historical identity must be resolved
there rather than invented here. This checkpoint neither excludes outstanding
requirements nor declares them impossible or gameplay-passed.
