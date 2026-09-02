# Padded Oracle Target and Evidence Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Use strict TDD for new corrections.

**Goal:** Correct oracle-infeasible target construction and prove current run evidence derives from verified input bytes and current failure/gate serialization before reevaluating Padded.
**Architecture:** Construct targets along the closest triangle's geometric normal scaled by its projection onto the stored interpolated normal; certify every rounded target with the exact retained oracle. Reparse verified inputs at the production output boundary, recompute failure reasons and selected-candidate gates, and bind long runs to an unchanged implementation snapshot.
**Tech Stack:** Python 3.12, NumPy, pytest, existing DAE/GLB parsers and exact surface oracle.
**Spec:** `docs/superpowers/specs/2026-09-01-clothmorph-terminal-exclusion-policy.md`

## Global Constraints

- Retain the exact predeclared stored-vertex-normal clearance oracle and `0.001 m` acceptance threshold.
- Retain the literal 160-case grid, topology/material/skin/coverage/atomic gates, and six-decimal POSITION readback.
- Invalid target construction or inconsistent run evidence is an implementation failure, never proof of garment impossibility.
- Preserve all old ignored artifacts. New runs use new empty directories; no deletion or overwrite.
- No GR2, PAK, live game, save/profile, protected route, or source-asset mutation.
- Do not modify source modules while a real search process has them loaded; freeze the code commit and hashes before the run and verify them afterward.
- Current `oracle-restored-r1` is rejected as closure evidence; its files remain historical diagnostics only.

## Confirmed failures

The controller independently reproduced the flat-triangle case with stored normal `[0.6,0,0.8]`: old target `[0.2506,0.25,0.0008]` has measured clearance `0.00064`, below `0.001`. It also independently counted 114 rows whose moved-ROI metrics contradict their serialized failure reasons in the retained run.

### Task 1: Certify targets under the acceptance oracle

**Files:** `geometry.py`, `solver.py` only if explicit failure propagation is needed, and focused geometry/solver tests under `workstreams/padded_bgwatch_closure/`.

**Interfaces:** `build_surface_constraints` retains its public arguments. A production constraint carries a target-certification result; uncertified constraints cannot enter a search that concludes exhaustion.

- [ ] Add a RED tilted-normal plane test and a simple feasible-shell control using the real target builder and exact clearance query. Include ordinary parallel normals and six-decimal roundtrip.
- [ ] Run focused tests and record the existing under-clearance failure.
- [ ] For closest point q, geometric unit face normal g, stored interpolated unit normal n, choose g's sign so dot(g,n) is positive. For nondegenerate projection, compute target along g with offset `(0.001 + 2 * 10**-6) / dot(g,n)`; the added two serialization quanta are a target margin, not an acceptance-threshold relaxation.
- [ ] Round target POSITIONs to six decimals, then rerun the exact closest-point/stored-normal query on every target. Require nonambiguous clearance at least `0.001`. Reject zero/near-zero projection, nonfinite targets, or failed target certification with a stable explicit setup failure; do not count these as failed geometry cases.
- [ ] Add direct target-verification tests for changed nearest triangles, projection degeneracy, and failed certification. Confirm the feasible-shell `scale=1, fairness=0` path can reach the clearance gate; retain all other gates.
- [ ] Run focused and workstream tests, report RED/GREEN, self-review, commit.

### Task 2: Bind writer evidence to input bytes and current gate logic

**Files:** `closure.py`, `integration.py`, `search.py`, and their focused tests.

**Interfaces:** Keep one canonical function deriving failure reasons and production pass/fail from gate fields. Production preparation must be reconstructible from the exact verified source/body bytes.

- [ ] Add RED tests: verified GLB bytes unrelated to parsed body; source DAE bytes unrelated to parsed source; inconsistent normal/ROI/cohort/constraint arrays; GateReport fields inconsistent with failure reasons or production_passed; selected candidate whose recomputed actual gates fail despite supplied passing metadata.
- [ ] Reparse actual verified DAE/GLB bytes, compare every production-relevant parsed array and semantic identity, and derive/compare active, ROI, cohort, and constraints through the same pure preparation path.
- [ ] Recompute reasons/status from every record's gate fields; reject contradictions before output. Do not trust stored production_passed booleans without deriving them from all gate fields.
- [ ] Roundtrip and evaluate the selected candidate against freshly prepared source/body/cohort/constraints; require exact agreement with its stored gate record and passing selection.
- [ ] Replace synthetic tests using arbitrary `b"synthetic body bytes"` with minimal valid byte-encoded DAE/GLB fixtures. Keep fabricated-byte rejection as an explicit negative case.
- [ ] Record input digests, implementation commit, and an ordered implementation-file hash manifest at run start; verify unchanged code/input hashes immediately before output. A mismatch refuses evidence emission.
- [ ] Run focused/workstream tests, report RED/GREEN, self-review, commit before the real run.

### Task 3: Produce a coherent new run and authoritative handoff

**Files:** public checkpoint, ignored plan progress/report, and a fresh ignored run directory.

- [ ] Verify clean committed implementation and certified target setup first. If setup cannot certify every required target, emit a blocked setup report with exact target IDs/reasons, not a 0-of-160 exhaustion claim.
- [ ] Otherwise run the exact 160-case search twice from the same frozen commit and inputs, with no code editing during execution.
- [ ] Verify equal run bytes, exact 160-tuples, gate-derived pass counts and failure reasons, input/code hashes, output hashes, and selected-candidate gates if present.
- [ ] Preserve both prior runs as rejected/historical. Append clear supersession notices to the old progress/report and point all current checkpoint links at the new run.
- [ ] Produce only an offline candidate or nonattachable pending evidence packet; actual canonical source-profile/record/event binding remains a separate gate.
- [ ] Run required regression suites and independently review the complete correction before any exclusion attachment.
