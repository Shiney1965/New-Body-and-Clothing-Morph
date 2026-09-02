# Terminal Exclusion Production Reachability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a valid exclusion reachable through the real reconcile-to-attachment-to-audit lifecycle while rejecting unresolved geometry component contracts.

**Architecture:** The shared exclusion validator receives an explicit lifecycle phase. Pre-attachment validation trusts only a hash-locked independent provider/package claim snapshot and permits the reconciled mode's pre-attachment representation; attachment deterministically writes the excluded representation; post-attachment audit and generated-ledger validation require both representations to be claim-free. Geometry validation rejects unresolved markers in every component source.

**Tech Stack:** Python 3.12, pytest, standard-library JSON/hash/path handling.

**Spec:** `docs/superpowers/specs/2026-09-01-clothmorph-terminal-exclusion-policy.md`

## Global Constraints

- One event closes one exact mode only; all four advertised release modes must be independently terminal before a record becomes nonblocking.
- Pre-attachment independent claim snapshots must be empty across provider IDs, target VRs, target paths, payload hashes, provenance, package ownership, and shipped-package claims.
- Post-attachment mode records and independent snapshots must both be claim-free and schema-valid.
- `UNKNOWN_*`, `UNRESOLVED_*`, `UNASSESSED_*`, and equivalent placeholder component identifiers never prove complete geometry exhaustion.
- Preserve the zero-event `3,173` record / `3,173` nonterminal baseline and every protected/Tiefling control.
- No real exclusion event, PAK, Runtime, save, profile, protected file, or live BG3 mutation.

---

### Task 1: Make the production attachment lifecycle reachable

**Files:**
- Modify: `workstreams/release_master_ledger/exclusions.py`
- Modify: `workstreams/release_master_ledger/generate.py`
- Modify: `workstreams/release_master_ledger/audit.py`
- Modify: `workstreams/release_master_ledger/validation.py`
- Modify: `workstreams/release_master_ledger/tests/test_exclusion_generation.py`
- Modify: `workstreams/release_master_ledger/tests/test_audit.py`

**Interfaces:**
- `validate_exclusion_event(..., lifecycle: Literal["pre_attachment", "attached"]) -> list[str]`
- Pre-attachment selection consumes the independent claim snapshot and does not require the reconciled mode record to already contain the excluded representation.
- Attached validation requires exact excluded sentinels/empty arrays in the mode record as well as an empty independent claim snapshot.

- [ ] **Step 1: Add the failing production-path regression**

Create a real observation fixture, run `reconcile_observations()`, attach four exact valid mode events through the production attachment function, and build the audit. Assert that the pre-attachment record validates, each mode is deterministically rewritten to the excluded representation, the record becomes `OUT_OF_SCOPE_WITH_PROOF`, and it leaves `in_scope_nonterminal` only after the fourth event.

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_exclusion_generation.py workstreams/release_master_ledger/tests/test_audit.py -k "production_lifecycle or lifecycle_claim" -v`

Expected: the current pre-attachment selection rejects the reconciled record because its mode arrays are not yet empty.

- [ ] **Step 3: Implement lifecycle-aware validation**

Use one shared closed structural/semantic validator with an explicit lifecycle. In `pre_attachment`, require the discovered event, event-file provenance, protected impact, exact approval/mode/identity, and independent claim snapshot to validate; do not treat the current reconciled mode representation as proof of absence. In `attached`, additionally require `advertised_scope=false`, `OUT_OF_SCOPE_WITH_PROOF`, `NO_PROVIDER_FOR_EXCLUDED_MODE`, empty target/payload arrays, `NO_PROVENANCE_FOR_EXCLUDED_MODE`, and no shipped/package claim.

- [ ] **Step 4: Add fail-closed claim regressions**

Mutate each independent claim channel individually before attachment and each record claim channel after attachment. Every mutation must remain in `exclusion_validation_failures` and `in_scope_nonterminal`, never `excluded_with_proof`.

- [ ] **Step 5: Run GREEN and commit**

Run the two focused test files and commit only Task 1 files.

### Task 2: Reject unresolved geometry components and reverify the real baseline

**Files:**
- Modify: `workstreams/release_master_ledger/exclusions.py`
- Modify: `workstreams/release_master_ledger/tests/test_exclusions.py`
- Modify: `workstreams/release_master_ledger/PUBLIC_CHECKPOINT.md`

**Interfaces:**
- Geometry exhaustion validates resolved component identifiers in `record.transformation.allowed_components`, `proof.expected_components`, and every architecture's ordered `components` list before comparing their complete sets/digests.

- [ ] **Step 1: Add RED tests for unresolved component markers**

Use the same unresolved marker consistently in the record, proof, and all architectures and assert a stable `EXCLUSION_GEOMETRY_COMPONENT_UNRESOLVED` error. Cover `UNKNOWN_ALLOWED_COMPONENT`, `UNRESOLVED_COMPONENT`, and `UNASSESSED_COMPONENT`.

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_exclusions.py -k "unresolved_component" -v`

Expected: current validation returns no error for the consistent placeholder.

- [ ] **Step 3: Implement the shared unresolved-marker gate**

Reject unresolved markers before exact-set/digest/atomic-pair checks. Do not weaken complete-set equality, per-component fixed gates, or architecture-family requirements.

- [ ] **Step 4: Run full deterministic verification**

Run: `python -m pytest workstreams/release_master_ledger workstreams/coverage_ledger workstreams/true_underwear workstreams/vanitybody -q`

Run the real zero-event generator twice and require byte-identical ledger, audit, manifest, and Markdown. Confirm exactly `3,173` records and `3,173` nonterminal/release-blocking records, zero exclusion sets, and unchanged protected `25/1/2/4` distribution.

- [ ] **Step 5: Update the checkpoint and commit**

Record only freshly verified hashes/counts. Commit Task 2 files and provide the full SDD report.
