# SCO and Sindae Coverage Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Account for every SCO and Sindae wearable route, reconcile all prior targeted projects, and produce complete class-based correction and gameplay queues with zero unclassified records.

**Architecture:** A read-only source scanner emits concrete wearable identities, a reconciler imports prior route/test evidence, and a deterministic disposition engine generates the master JSON/Markdown ledger and bounded class queues. The ledger is an inventory and decision system, not a blanket deformation system.

**Tech Stack:** Python 3.11+, pytest, JSON Schema, BG3 LSX/LSF/root templates/stats/VisualBank data, existing ClothMorph reports and gameplay evidence.

**Spec:** `docs/superpowers/specs/2026-08-29-clothmorph-class-first-coverage-design.md`

## Global Constraints

- Every discovered SCO/Sindae wearable source route appears exactly once.
- Concrete identity uses source module, root template, stats entry, effective slot, source VR, and body family.
- Route existence is not gameplay acceptance.
- Signature similarity may produce `READY FOR TEST`; it may not directly authorize edits.
- Passing assets are `ACCEPTED / PROTECT` and excluded from mutation.
- Prior work is reconciled, not duplicated or silently superseded.
- Allowed dispositions are exactly those in the specification.
- Zero records may remain `UNCLASSIFIED` at completion.

---

### Task 1: Define the master schema and source registry

**Files:**
- Create: `workstreams/coverage_ledger/schema.json`
- Create: `workstreams/coverage_ledger/models.py`
- Create: `workstreams/coverage_ledger/source_registry.json`
- Create: `workstreams/coverage_ledger/tests/test_schema.py`

**Interfaces:**
- Produces: `GarmentRecord` and `RouteRecord` dataclasses matching `schema.json`.

- [ ] **Step 1: Write RED schema tests**

```python
def test_disposition_enum_is_binding():
    schema = load_schema()
    assert set(schema["$defs"]["disposition"]["enum"]) == {
        "ACCEPTED / PROTECT",
        "READY FOR TEST",
        "CONFIRMED DEFECT / CORRECT",
        "MISSING ROUTE / BUILD",
        "DEFERRED WITH CAUSE",
        "OUT OF SCOPE",
    }
```

- [ ] **Step 2: Implement schema and explicit source-module registry**
- [ ] **Step 3: Run GREEN**
- [ ] **Step 4: Commit**

### Task 2: Scan every SCO/Sindae wearable creation path

**Files:**
- Create: `workstreams/coverage_ledger/scan_sources.py`
- Create: `workstreams/coverage_ledger/tests/test_scan_sources.py`
- Create: `workstreams/coverage_ledger/evidence/RAW_WEARABLE_INVENTORY.json`

**Interfaces:**
- Produces: `scan_source(SourceModule) -> list[GarmentRecord]`

- [ ] **Step 1: Write failing fixtures for root/stats mismatch, multiple VRs, and shared mesh paths**
- [ ] **Step 2: Implement root-template, stats, slot-inheritance, and VisualResource joins**
- [ ] **Step 3: Emit unresolved joins to `SCAN_REJECTIONS.json` with reasons**
- [ ] **Step 4: Assert duplicate concrete identities are zero**
- [ ] **Step 5: Run GREEN and commit**

### Task 3: Reconcile prior project evidence

**Files:**
- Create: `workstreams/coverage_ledger/reconcile.py`
- Create: `workstreams/coverage_ledger/prior_sources.json`
- Create: `workstreams/coverage_ledger/tests/test_reconcile.py`
- Create: `workstreams/coverage_ledger/evidence/RECONCILIATION_REPORT.json`

**Interfaces:**
- Produces: `reconcile(records, evidence_sources) -> ReconciliationResult`

- [ ] **Step 1: Write RED tests proving accepted evidence outranks stale ready-to-test cards**

```python
def test_gameplay_pass_supersedes_stale_ready_card():
    result = reconcile([GARMENT], [STALE_CARD, LATER_GAMEPLAY_PASS])
    assert result.records[0].disposition == "ACCEPTED / PROTECT"
    assert result.records[0].controlling_evidence == LATER_GAMEPLAY_PASS.path
```

- [ ] **Step 2: Register prior evidence families**

Include SindaeSeven, Recluse, SoulVestAlt, Bard, Bard Dress, Butler, Oathbreaker, Scalemail/Soul Vest, BCBScantily, Padded Armour/BG Watch, additional modded garments, and prior accepted/rejected waves.

- [ ] **Step 3: Implement chronological and evidence-strength precedence**
- [ ] **Step 4: Emit conflicts rather than choosing silently**
- [ ] **Step 5: Run GREEN and commit**

### Task 4: Generate the complete ledger and class queues

**Files:**
- Create: `workstreams/coverage_ledger/build_ledger.py`
- Create: `workstreams/coverage_ledger/tests/test_completeness.py`
- Create: `workstreams/coverage_ledger/evidence/SCO_SINDAE_MASTER_GARMENT_LEDGER.json`
- Create: `workstreams/coverage_ledger/evidence/SCO_SINDAE_MASTER_GARMENT_LEDGER.md`
- Create: `workstreams/coverage_ledger/evidence/CLASS_TEST_QUEUES.json`

- [ ] **Step 1: Write RED completeness tests**

```python
def test_every_raw_identity_has_exactly_one_master_record():
    raw = load_raw_inventory()
    master = build_master_ledger(raw, load_prior_evidence())
    assert Counter(r.identity for r in master) == Counter({r.identity: 1 for r in raw})

def test_no_unclassified_dispositions():
    assert all(r.disposition != "UNCLASSIFIED" for r in load_master_ledger())
```

- [ ] **Step 2: Implement deterministic disposition rules**
- [ ] **Step 3: Group `READY FOR TEST` by proven class/mechanism and dependency-compatible profile**
- [ ] **Step 4: Separate missing-route builds from confirmed-defect corrections**
- [ ] **Step 5: Run GREEN and commit**

### Task 5: Produce class-based gameplay cards and handoff

**Files:**
- Create: `workstreams/coverage_ledger/generate_test_cards.py`
- Create: `workstreams/coverage_ledger/tests/test_test_cards.py`
- Create: `workstreams/coverage_ledger/test_cards/`
- Create: `workstreams/coverage_ledger/COVERAGE_STATUS.md`

- [ ] **Step 1: Write RED tests requiring every `READY FOR TEST` record in exactly one card**
- [ ] **Step 2: Generate dependency-isolated waves with exact spawn commands and route gates**
- [ ] **Step 3: Include protected controls, rollback, evidence filenames, and `NOT RUN` result rows**
- [ ] **Step 4: Validate that no accepted/protected record appears in a mutation target list**
- [ ] **Step 5: Run the complete workstream suite**

Run: `python -m pytest workstreams/coverage_ledger/tests -v`

- [ ] **Step 6: Commit**

```powershell
git add workstreams/coverage_ledger
git commit -m "feat: complete SCO and Sindae garment coverage ledger"
```

