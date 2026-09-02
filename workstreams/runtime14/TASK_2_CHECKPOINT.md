# R1 qualification - work in progress

The separately revisioned `runtime/r1_qualified_delta/` is a candidate, not an
accepted Runtime or playable Alfira fix. It does not change the frozen pure-R1
reference. `qualification.py` revalidates the complete Task-1 source stage and
exclusively composes the candidate without changing protected data.

Portable tests never load machine-specific configuration. Exact-source production
tests require explicit `CLOTHMORPH_RUNTIME14_INPUTS`; they load the actual staged Lua
modules with simulated game-engine boundaries. Stage receipts, source manifests,
Lua output, and NOT_RUN gameplay status are written outside the package tree.

The detailed requirement inventory is [TASK_2_REQUIREMENTS.md](TASK_2_REQUIREMENTS.md).
Task 2 remains incomplete, including registration queues, exhaustive failure/event
qualification, diagnostics, and independent review. No test PAK is eligible from
this checkpoint alone.

Core checkpoint verification: 478 tests passed, 15 explicit skips in the full
actual-source/inherited run. This includes the actual Runtime Lua control/schema/
client/master/debug checks and protected-map byte comparison, but excludes the
not-yet-implemented legacy queue suite (0/4 RED). It is not complete Task 2 or
independent-review acceptance.
