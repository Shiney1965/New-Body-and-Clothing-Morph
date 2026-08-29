# VanityBody Groin Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce new, topology-safe VanityBody meshes that remove the four confirmed Vanilla/SBBF groin or genital clipping defects without changing protected modes.

**Architecture:** The workstream records current route/mesh failures, constructs a common-frame body/garment clearance model for the defect region, applies bounded position-only corrections, and packages only corrected modes in an isolated TEST provider. Existing old provider meshes are evidence inputs, not accepted correction outputs.

**Tech Stack:** Python 3.11+, pytest, NumPy, BG3 GR2 position patching, BG3 visual banks, Divine.exe, existing ClothMorph topology/semantic verification utilities.

**Spec:** `docs/superpowers/specs/2026-08-29-clothmorph-class-first-coverage-design.md`

## Global Constraints

- Targets are Wedding Vanilla/SBBF, Satin Vanilla, Serious Business Vanilla, and Sexy Catsuit Vanilla only.
- BCB is protected for all four garments; Satin/Serious Business/Sexy Catsuit SBBF are protected.
- No TEST asset may be copied byte-for-byte from the currently clipping ClothMorphBCB target.
- Position-only edits preserve topology, skeleton, weights, UVs, normals, tangents, vertex colors, materials, and non-target components.
- No new flipped triangles, zero-area triangles, or unacceptable area collapse.
- Clearance must be calculated for the defect region; `collision_free` is never assumed.
- One anchor is solved and reviewed before any same-mechanism propagation.
- Gameplay results remain `NOT RUN` until exact route and visual evidence exist.

---

### Task 1: Freeze failing evidence and protected controls

**Files:**
- Create: `workstreams/vanitybody/anchors.py`
- Create: `workstreams/vanitybody/evidence/CONFIRMED_DEFECTS.json`
- Create: `workstreams/vanitybody/tests/test_anchor_contract.py`

**Interfaces:**
- Produces: `AnchorContract` records keyed by source VR and mode.

- [ ] **Step 1: Write failing exact-anchor tests**

```python
def test_confirmed_anchor_set_is_exact():
    actual = {(a.root_uuid, a.mode) for a in load_anchor_contracts()}
    assert actual == {
        (WEDDING_ROOT, "vanilla"),
        (WEDDING_ROOT, "sbbf"),
        (SATIN_ROOT, "vanilla"),
        (SERIOUS_BUSINESS_ROOT, "vanilla"),
        (SEXY_CATSUIT_ROOT, "vanilla"),
    }
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/vanitybody/tests/test_anchor_contract.py -v`

- [ ] **Step 3: Record exact source/target VRs, paths, hashes, screenshots, and protected hashes**
- [ ] **Step 4: Run GREEN**
- [ ] **Step 5: Commit**

```powershell
git add workstreams/vanitybody
git commit -m "test: freeze vanity clipping anchors"
```

### Task 2: Build the regional clearance evaluator

**Files:**
- Create: `workstreams/vanitybody/clearance.py`
- Create: `workstreams/vanitybody/tests/test_clearance.py`
- Create: `workstreams/vanitybody/tests/fixtures/synthetic_body.npy`
- Create: `workstreams/vanitybody/tests/fixtures/synthetic_garment.npy`

**Interfaces:**
- Produces: `measure_penetration(body, garment, region, clearance_mm) -> ClearanceReport`
- Produces: `ClearanceReport(penetrating_vertices, min_signed_distance, max_penetration, region_vertices)`

- [ ] **Step 1: Write RED tests for known penetrating and clear synthetic fixtures**

```python
def test_penetrating_fixture_is_detected():
    report = measure_penetration(BODY, PENETRATING_GARMENT, GROIN_REGION, 0.002)
    assert report.penetrating_vertices > 0
    assert report.max_penetration > 0

def test_clear_fixture_has_no_penetration():
    report = measure_penetration(BODY, CLEAR_GARMENT, GROIN_REGION, 0.002)
    assert report.penetrating_vertices == 0
```

- [ ] **Step 2: Implement a deterministic common-frame nearest-surface/signed-clearance evaluator**
- [ ] **Step 3: Validate the evaluator against one known gameplay-clipping anchor and one protected control**
- [ ] **Step 4: Run GREEN**
- [ ] **Step 5: Commit**

```powershell
git add workstreams/vanitybody
git commit -m "feat: add regional garment clearance evaluator"
```

### Task 3: Solve Wedding Vanilla as the first anchor

**Files:**
- Create: `workstreams/vanitybody/solve_anchor.py`
- Create: `workstreams/vanitybody/tests/test_wedding_vanilla.py`
- Create: `workstreams/vanitybody/evidence/WEDDING_VANILLA_SOLVE.json`

**Interfaces:**
- Produces: `solve_local_clearance(contract, body, garment) -> PositionPatch`

- [ ] **Step 1: Write a failing test requiring reduced penetration with static gates**

```python
def test_wedding_vanilla_patch_clears_region_and_preserves_contract():
    patch = solve_local_clearance(CONTRACT, BODY, GARMENT)
    result = apply_patch(GARMENT, patch)
    assert measure_penetration(BODY, result, REGION, CLEARANCE).penetrating_vertices == 0
    assert topology_signature(result) == topology_signature(GARMENT)
    assert semantic_non_position_hash(result) == semantic_non_position_hash(GARMENT)
```

- [ ] **Step 2: Run RED**
- [ ] **Step 3: Implement a bounded falloff displacement limited to the proven intersecting component/region**
- [ ] **Step 4: Run topology, area, component, and semantic gates**
- [ ] **Step 5: Export the patched position stream into a new GR2 candidate**
- [ ] **Step 6: Commit source and evidence, excluding GR2**

### Task 4: Correct the remaining confirmed modes

**Files:**
- Create: `workstreams/vanitybody/correct_targets.py`
- Create: `workstreams/vanitybody/tests/test_correct_targets.py`
- Create: `workstreams/vanitybody/evidence/TARGET_CORRECTIONS.json`

- [ ] **Step 1: Write one failing test per remaining anchor**
- [ ] **Step 2: Attempt propagation only for an exact matching mechanism/signature**
- [ ] **Step 3: Solve independently when propagation gates fail**
- [ ] **Step 4: Assert every protected target hash is unchanged**
- [ ] **Step 5: Run complete workstream tests**

Run: `python -m pytest workstreams/vanitybody/tests -v`

- [ ] **Step 6: Commit**

```powershell
git add workstreams/vanitybody
git commit -m "feat: correct confirmed vanity groin clipping"
```

### Task 5: Package and verify the VanityBody TEST provider

**Files:**
- Create: `workstreams/vanitybody/build_pak.py`
- Create: `workstreams/vanitybody/verify_pak.py`
- Create: `workstreams/vanitybody/tests/test_package.py`
- Create: `workstreams/vanitybody/VANITYBODY_GROIN_FIX_TEST_CARD.md`

- [ ] **Step 1: Write RED tests for exact target set, dependencies, and protected exclusions**
- [ ] **Step 2: Mint new target VRs and a unique TEST module UUID/folder**
- [ ] **Step 3: Declare Runtime and every exact source dependency**
- [ ] **Step 4: Pack and fresh-extract with complete manifests**
- [ ] **Step 5: Verify route count, new mesh hashes, topology gates, and zero copied old-target hashes**
- [ ] **Step 6: Generate a one-line spawn command and leave gameplay rows `NOT RUN`**
- [ ] **Step 7: Commit source, tests, evidence, and card**

```powershell
git add workstreams/vanitybody
git commit -m "feat: package vanitybody groin fix test"
```

