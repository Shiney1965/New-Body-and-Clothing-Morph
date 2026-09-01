# Bard and Authority Geometry Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve Bard Vanilla/SBBF and Robe of Authority through materially distinct geometry/contract tests, producing safe offline candidates or evidence-backed exclusions without changing protected BCB routes.

**Architecture:** Bard first applies a one-ring constrained repair to the single SBBF sleeve failure, then tests a component-specific landmark/cage architecture for Vanilla. Authority first reconstructs the exact nine-object/optional-skirt contracts and forbids the ten-object Netherstone substitute; geometry begins only for a fully admitted exact contract with defect localization.

**Tech Stack:** Python 3.12, NumPy, retained GLB/GR2-derived evidence, pytest/unittest-compatible tests.

**Spec:** `docs/superpowers/specs/2026-09-01-clothmorph-terminal-exclusion-policy.md`

## Global Constraints

- Bard base+thong is atomic per mode; no partial route emission.
- Bard requires zero flips/zeros/sub-25%-area faces, exact non-POSITION semantics, and a nontrivial completion floor of 0.50.
- Native BCB base/thong bytes and routes remain protected; generate zero BCB replacements.
- Authority must preserve the nine-object BCBScantily main contract and item-specific optional skirt; any Netherstone/tenth-object candidate is forbidden.
- No GR2/PAK until complete static gates pass; no live action.

---

### Task 1: Freeze Bard and Authority contracts

**Files:**
- Create: `workstreams/bard_authority_closure/__init__.py`
- Create: `workstreams/bard_authority_closure/configuration.py`
- Create: `workstreams/bard_authority_closure/contracts.py`
- Create: `workstreams/bard_authority_closure/tests/test_contracts.py`
- Create: `workstreams/bard_authority_closure/.gitignore`

- [ ] RED: pin Bard component hashes/82-bone contract and Authority nine-object/no-Netherstone contract; fail the four unresolved Authority geometry IDs.
- [ ] Implement hash-locked local configuration and contract readers.
- [ ] GREEN and commit.

### Task 2: Test Bard SBBF sleeve-only constrained repair

**Files:**
- Create: `workstreams/bard_authority_closure/bard_sbbf_repair.py`
- Create: `workstreams/bard_authority_closure/tests/test_bard_sbbf_repair.py`

**Interfaces:**
- `failing_face_neighborhood(source, candidate, faces, threshold=0.25) -> RepairRegion`
- `solve_local_area_constrained_positions(...) -> CandidateResult`
- `verify_outside_region_exact(...) -> GateReport`

- [ ] RED: retained SBBF alpha-0.50 sleeve has one sub-25% triangle at ratio `0.159049789992582`.
- [ ] Implement one-ring position-only solve; every outside vertex remains exact float32.
- [ ] Require complete SBBF base plus retained passing thong gates.
- [ ] Emit candidate only if the pair passes; otherwise record method exhaustion.
- [ ] Commit.

### Task 3: Test Bard Vanilla component landmark/cage architecture

**Files:**
- Create: `workstreams/bard_authority_closure/bard_landmark_cage.py`
- Create: `workstreams/bard_authority_closure/tests/test_bard_landmark_cage.py`
- Create ignored: `workstreams/bard_authority_closure/local/landmarks.json`

**Interfaces:**
- `load_component_landmark_contract(component, mode) -> LandmarkContract`
- `solve_harmonic_cage_displacement(...) -> ndarray`
- `build_complete_mode_candidate(mode) -> CompletePairResult`

- [ ] RED: pin current Vanilla base/thong failure counts and reject missing/duplicate/out-of-component anchors.
- [ ] Implement component-specific cage solve with exact topology/semantic preservation.
- [ ] Require all base streams plus thong to pass at the 0.50 floor.
- [ ] If no declared contract passes, record `UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING` for Vanilla under this final architecture.
- [ ] Commit.

### Task 4: Resolve Authority contract and conditional geometry

**Files:**
- Create: `workstreams/bard_authority_closure/authority_contracts.py`
- Create: `workstreams/bard_authority_closure/tests/test_authority_contracts.py`
- Create only after contract admission: `workstreams/bard_authority_closure/authority_landmark_cage.py`
- Create only after contract admission: `workstreams/bard_authority_closure/tests/test_authority_landmark_cage.py`

- [ ] Reject the ten-object SCO/Netherstone substitute.
- [ ] Resolve normal versus skirt/Alt item contracts and every required geometry ID from retained exact sources.
- [ ] If any exact source geometry/defect region remains absent after exhaustive audit, prepare an `UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT` exclusion event.
- [ ] Only with complete admission, run a component-specific POSITION-only cage test with exact non-POSITION preservation.
- [ ] Commit the evidence-backed terminal result.

### Task 5: Run local closure, review, and ledger integration

- [ ] Run every solver twice for determinism.
- [ ] Generate ignored candidates/evidence only; commit public code/tests/checkpoints.
- [ ] Produce exclusion-event inputs for failed terminal architectures, but attach them only after terminal-policy validation exists.
- [ ] Run release-ledger integration, independent review, and verify protected BCB hashes/routes remain unchanged.
