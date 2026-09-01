# Padded BG Watch Position-Only Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the final materially distinct topology-preserving automatic architecture for `HUM_F_ARM_BG_Watch_Leather_A_Body` and produce either one offline position-only candidate or evidence that position-only repair is exhausted under the current topology.

**Architecture:** A new public solver workstream reads hash-pinned external geometry through ignored local configuration. It derives exact closest-triangle constraints for the original 593 active vertices, solves one coherent connected-ROI Laplacian displacement field over a fixed 160-case grid, and applies all topology/coverage/contract gates after six-decimal serialization.

**Tech Stack:** Python 3.12, NumPy, pytest/unittest-compatible tests, retained DAE/GLB evidence.

**Spec:** `docs/superpowers/specs/2026-09-01-clothmorph-terminal-exclusion-policy.md` and `C:\Claude Projects\BG3 Mods\ChatGPT Work Files\Padded_BGWatch_TopologyRecovery_20260826\TOPOLOGY_RECOVERY_FINDINGS.md`

## Global Constraints

- No GR2, VisualBank, Lua, PAK, install, profile, or gameplay action until every offline gate passes.
- Use pristine source DAE SHA `DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262` and BCB body SHA `51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C`.
- Exactly 8,033 LOD0 vertices and 14,943 faces; preserve all non-POSITION data and LOD1+ positions.
- Exact 160-case grid: 10 scales × 4 fairness weights × 4 iteration counts; no adaptive expansion.
- Pass requires 0 penetration/deep penetration, 0 fixed-cohort coverage loss, 0 flips/zeros, published area `[0.5,2.0]`, internal `[0.51,1.99]`, orientation cosine `>=0.05`, and every original active vertex `>=+0.001m` clear.
- If 0/160 pass, emit `POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY`; do not weaken gates or build a PAK.

---

### Task 1: Freeze baseline evidence and local boundary

**Files:**
- Create: `workstreams/padded_bgwatch_closure/__init__.py`
- Create: `workstreams/padded_bgwatch_closure/configuration.py`
- Create: `workstreams/padded_bgwatch_closure/models.py`
- Create: `workstreams/padded_bgwatch_closure/tests/test_baselines.py`
- Create: `workstreams/padded_bgwatch_closure/.gitignore`
- Create ignored: `workstreams/padded_bgwatch_closure/local/config.json`

- [ ] Write RED tests pinning local-repair `421/411/40`, historical `115/1574/31`, input hashes, and path containment.
- [ ] Implement hash-before-read configuration and immutable baseline records.
- [ ] Run GREEN and commit.

### Task 2: Implement coherent ROI constraints and synthetic solver

**Files:**
- Create: `workstreams/padded_bgwatch_closure/geometry.py`
- Create: `workstreams/padded_bgwatch_closure/solver.py`
- Create: `workstreams/padded_bgwatch_closure/tests/test_solver.py`

**Interfaces:**
- `derive_minimal_roi(base_positions, faces, active_ids) -> RoiContract`
- `build_surface_constraints(base_positions, body_mesh, active_ids) -> SurfaceConstraints`
- `solve_coherent_field(base, faces, roi, constraints, scale, fairness, iterations) -> Candidate`
- `evaluate_candidate(source, candidate, contract) -> GateReport`

- [ ] RED: synthetic connected shell where independent pushes fail topology.
- [ ] Implement fixed-boundary, neighborhood-coupled solve; reject illegal face updates before write.
- [ ] GREEN: nonzero coherent result or explicit no-solution, never weakened gates.
- [ ] Commit.

### Task 3: Implement deterministic 160-case search

**Files:**
- Create: `workstreams/padded_bgwatch_closure/search.py`
- Create: `workstreams/padded_bgwatch_closure/tests/test_search.py`

- [ ] RED: require exactly 160 unique ordered parameter tuples and complete failure records.
- [ ] Implement deterministic search, stable selection ordering, and candidate/evidence serialization.
- [ ] Require two runs to produce identical JSON and selected DAE hash.
- [ ] Commit.

### Task 4: Run real offline closure and record terminal result

**Files:**
- Create ignored: `workstreams/padded_bgwatch_closure/local/generated/position_only_search.json`
- Create ignored only on pass: `workstreams/padded_bgwatch_closure/local/generated/HUM_F_ARM_BG_Watch_Leather_A_Body_CMcover_candidate.dae`
- Create: `workstreams/padded_bgwatch_closure/PUBLIC_CHECKPOINT.md`
- Create: `workstreams/padded_bgwatch_closure/tests/test_local_integration.py`

- [ ] Run the hash-locked local integration twice.
- [ ] If one or more pass, select deterministically and label only `OFFLINE_POSITION_ONLY_CANDIDATE`.
- [ ] If zero pass, record all 160 failures and `POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY`; prepare an exclusion-event input under the terminal policy but do not invent mathematical impossibility.
- [ ] Run the full workstream and release-ledger suites, independent review, and commit the public checkpoint/code only.
