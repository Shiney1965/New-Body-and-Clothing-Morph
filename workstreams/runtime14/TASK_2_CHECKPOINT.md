# R1 qualification - work in progress

## Dirty overlay note (2026-09-03, not a Task 2 acceptance)

Pending-refresh wait-then-apply is implemented on the current dirty
`r1_qualified_delta` overlay. Independently executed `test_r1_pending_refresh.lua`
is Wait PASS (4/4 + WAIT_NOTIFY), not RED. MCM origin-proof remains OPEN (0/2).
Task 2 is not accepted. Historical 0/4 receipts below describe prior heads, not
this dirty tree.

Latest partial review-fix evidence is in [TASK_2_FIX_ROUND1.md](TASK_2_FIX_ROUND1.md).
Six bounded findings were corrected in round 1. MCM-origin relay cases remain OPEN.
Pending-refresh on this dirty overlay is Wait PASS (see note above). Task 2 is not accepted.

The separately revisioned `runtime/r1_qualified_delta/` is a candidate, not an
accepted Runtime or playable Alfira fix. It does not change the frozen pure-R1
reference. `qualification.py` revalidates the complete Task-1 source stage and
exclusively composes the candidate without changing protected data.

Portable tests never load machine-specific configuration. Exact-source production
tests require explicit `CLOTHMORPH_RUNTIME14_INPUTS`; they load the actual staged Lua
modules with simulated game-engine boundaries. Stage receipts, source manifests,
Lua output, and NOT_RUN gameplay status are written outside the package tree.

The detailed requirement inventory is [TASK_2_REQUIREMENTS.md](TASK_2_REQUIREMENTS.md).
Task 2 remains incomplete. Registration queues, failure/event fixtures, schema
validation, diagnostics, and ordinary managed round trips are implemented in the
candidate; they do not erase the remaining inventory-refresh conflict or the
requirement for independent review. No test PAK is eligible from this checkpoint.

Core checkpoint verification: 478 tests passed, 15 explicit skips in the full
actual-source/inherited run. This includes the actual Runtime Lua control/schema/
client/master/debug checks and protected-map byte comparison, but excludes the
not-yet-implemented legacy queue suite (0/4 RED). It is not complete Task 2 or
independent-review acceptance.

## Subsequent candidate work

The historical result above belongs to commit
`0e20c29b433b8787707bfb3a9a1ca8d018b312a2`; it is not the current acceptance tally.
Subsequent work adds queued body/family/revealing activation, real legacy external
caller compatibility, explicit unresolved legacy ownership, source dependency
revalidation, process-vs-persisted activation and cross-save conflict handling,
strict schema fields, event/failure inventories, and shared-CV fallback retirement.

The original live probe disproved the native-add fixture's immediate visibility
assumption. The production fixture now defers native additions, and its initial
timing suite failed both managed application and an orphan appearing after an
External switch. The candidate uses the existing R0 writable CCA array surface
with exact current-entry preservation, replication and verified ownership
readback; see `PENDING_REFRESH_INVESTIGATION.md`. Its compatibility basis is R0's
existing use of that surface, not a claim of testing a historical SE20 binary.

Historical (prior head): the separate stateful `test_r1_pending_refresh.lua` was a mandatory RED:
an already-started managed refresh unequips an item, but immediate External gates
its delayed re-equip and leaves the equipped slot empty. There is no verified
inventory-preserving EquipmentRace refresh replacement yet. Delaying Off/External
has not been approved or implemented. This source-only blocker prevents Task 2
acceptance even if all other aggregate tests pass.

## Review checkpoint (historical): mandatory aggregate was RED

Review base: `9fe8e0739b954ee18cad9b87b8a08e133f103e11`. The latest full mandatory
run completed **1 failed, 480 passed, 15 skipped in 120.36 seconds**. The failure
is the stateful pending refresh suite: **0/4**, covering mature/family refresh
with both External and master-off. It remains in the aggregate, not skipped.

Fresh exact-source receipt:
`local/stages/qualified/5df5dd83c5434f88983eaa2c3d4948f1.evidence.json`.
It binds 746 composed files, 21 successful Lua syntax checks, zero harness drift,
and qualification contract digest
`F600F164B2DB13B5DA73BA47AD19558017BD471C18A5DD750F5E347C745746FD`.

Passing real-production Lua suites: production 29/29; schema 37/37; client 4/4;
master journals 5/5; debug 5/5; registration 11/11; mutator inventory 18/18;
failure matrix 11/11; events 4/4; master resume 6/6; diagnostics 4/4; mature
managed regression 24/24; legacy external 6/6; native visual timing 11/11.

The last timing cases distinguish a verified server-array write from later
replication. A rejected assignment or failed readback creates no claim. Once an
append is actually verified, its claim is recorded before propagation; failed
propagation invokes owned rollback and retains the real claim plus partial
journal if removal fails. Direct managed debug and state-manager callers are
both covered, including unrelated visuals appended before rollback.

Fresh public index exports `_r14pub_8d311a6c/false` and `/true` each passed
59 tests with 5 explicit skips, in 12.66 and 11.40 seconds respectively. These
portable runs deliberately do not claim the local actual-source test passed.

Unfulfilled on this dirty tree: MCM origin-proof OPEN, independent
review and resulting fixes, and Task 2 acceptance. Full provider remint/reverse
and rollback acceptance remains mandatory DEFERRED_TO_TASK5. Gameplay NOT_RUN;
no PAK build/install or Alfira/whole-release completion. The pending refresh
implementation and the user's unanswered switching-behavior approval are intact.
