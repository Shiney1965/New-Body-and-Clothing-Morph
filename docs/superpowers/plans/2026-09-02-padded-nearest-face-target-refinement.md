# Padded nearest-face target refinement implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development with strict test-driven-development and independent review. Preserve existing source/evidence and do not start the real grid until the corrected setup is certified.

**Goal:** Correct target construction when the initial outward offset changes the nearest body triangle, then resume the real Padded closure search under every unchanged acceptance gate.

**Architecture:** Retain the current initial targets and exact stored-normal clearance oracle. Re-query rounded targets and refine only under-clearance targets using the current nearest triangle's oriented geometric normal and actual remaining clearance deficit. Every result must be certified by the unchanged oracle; bounded construction failure remains a setup failure, never garment exhaustion.

**Inputs:** frozen production failure at `f538a8615310d63abca31689c1e9108e76d4bc52`, truthful checkpoint `acefcff37736362b51f9cc695ba8c906a4330122`, and diagnostic SHA `5D33CA9E5D484CF496A72FAAB8D27648DD16F681B9136F62017CE5F8A9130BC8` at `workstreams/padded_bgwatch_closure/local/generated/runs/certified-setup-f538a86/blocked_setup_diagnostics.json`.

## Evidence and rationale

Actual production setup fails at source IDs 546, 548, 4134, 5725, and 7623. Every failure changes nearest triangles without ambiguity. The initial-face formula therefore does not establish clearance from the surface actually selected by the final query.

The controller's read-only calculation recomputed the direction at that final nearest face, advanced by `(0.001 + 0.000002 - current_clearance) / dot(oriented_geometric_normal, current_stored_normal)`, rounded to six decimals, and re-queried. Each of the five passed after one correction. That calculation did not modify production code or run the garment solver.

Exploratory script/result are retained in the sibling Runtime worktree's `.superpowers/research/padded_projection_probe.py` and `padded_projection_probe_result.json`, SHA `79DD00F6B043872563BACDB5B2F752CD69F1ADE3E0272705AEF01FBB1924D4D2` and `942B632B78C33C4BC900D184495159F92363E9DA95509B1BB5746740E8720CE5`. They guide tests, not acceptance. No source IDs or successful coordinates may be hard-coded into production.

## Fixed boundaries

- Keep the stored-vertex-normal oracle, acceptance clearance `0.001 m`, and six-decimal POSITION serialization unchanged.
- Keep the literal 160-case grid, selection order, ROI, active/cohort identities, topology/material/skin/coverage/area/orientation/atomic gates, and canonical-versus-synthetic evidence boundary unchanged.
- Keep passing initial targets byte-identical. Refine only targets failing clearance; do not increase the global margin or change the oracle to make them pass.
- Ambiguity, nonfinite data, degenerate projection, stalled/cyclic refinement, and iteration-limit failure remain explicit setup errors with exact source IDs.
- No source, historical artifact, protected route, live game, save/profile, GR2, or PAK mutation. No implementation changes while a real solver process is running.

### Task 1: Implement bounded refinement against the actual nearest face

**Files:** `workstreams/padded_bgwatch_closure/geometry.py`, focused geometry/solver tests and minimal test-only fixtures. Do not modify search/grid/writer semantics.

**Interface:** `build_surface_constraints` and `TargetCertification` retain their public contract. A focused internal helper may refine initial rounded targets before their existing final certificate is constructed.

- [ ] RED: build an analytic multi-triangle synthetic fixture where the initial offset changes the nearest face and fails the current oracle. Execute the real target builder and query; retain flat/tilted-normal and feasible-shell positive controls.
- [ ] RED: verify already-passing targets remain exactly unchanged and failed targets are not silently dropped, relabeled, or certified with stale queries.
- [ ] After initial target construction, query the actual rounded positions. Reject ambiguous results. For each under-clearance target, obtain the current nearest triangle, normalize and orient its geometric normal toward the current stored interpolated normal, and reject nonfinite/near-zero projection using the existing projection threshold.
- [ ] Advance from the current target by `(TARGET_CLEARANCE_M + 2 * 10**-TARGET_SERIALIZATION_DECIMALS - actual_clearance) / positive_projection` along that oriented geometric normal. Round immediately, re-query the actual target, and accept the first nonambiguous result meeting the unchanged clearance gate.
- [ ] Use at most sixteen correction steps per target. Detect repeated/stalled rounded positions and fail with stable specific setup codes and exact source IDs. The bound prevents uncontrolled construction; reaching it is not a physical impossibility claim.
- [ ] Recompute the full final certificate from actual targets/body. Preserve the existing anti-forgery/association checks and all initial source constraints; no caller-provided passing query is trusted.
- [ ] Add negative tests for ambiguous updated faces, near-zero projection, nonfinite correction, rounding stall/cycle, and iteration cap. Test multiple simultaneously failing targets and independence from active-ID ordering.
- [ ] Run focused and full portable suites, self-review, and commit before the actual canonical setup is re-run. Independent review must be clean before Task 2.

### Task 2: Certify the real setup and resume the exact repeated search

**Files:** new ignored run directory and chronological public checkpoint/report only; do not modify production implementation during execution.

- [ ] Confirm clean committed implementation and unchanged canonical source/body identities. Re-run actual setup, requiring all 593 targets to pass the exact nonambiguous clearance certificate; verify the five previously failing IDs are included and not exempted.
- [ ] Capture exact target/body/input/code hashes, actual clearances, target correction counts where available, and unchanged active/ROI/cohort gates. Repeat setup deterministically; any failed setup keeps the task incomplete and launches no grid.
- [ ] Once setup is certified, resume Task 3 of `2026-09-02-padded-oracle-evidence-consistency.md`: run the exact 160-case search twice from the same frozen source, use `CANONICAL_PADDED` output through the reviewed writer, and verify identical evidence and all selected-candidate gates if a candidate exists.
- [ ] Preserve every older run as historical/rejected; never overwrite diagnostics or re-label old evidence as a result from this implementation.
- [ ] Update chronological progress/checkpoint with the actual outcome. No attachable exclusion until the independent geometry/policy/source-profile/record gates are satisfied. A passing setup alone is not a garment result.
- [ ] Run final regressions and independent branch review. Keep any unresolved garment work active; do not equate a method failure with exhaustion of all eligible methods.
