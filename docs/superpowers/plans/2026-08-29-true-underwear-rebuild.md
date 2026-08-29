# True Underwear Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, slot-correct true-underwear ledger and a TEST PAK containing only base-game, SCO, and Sindae items whose effective game slot is `Underwear`.

**Architecture:** An isolated `workstreams/true_underwear` package resolves stats inheritance, records concrete creation paths, audits existing routes, selects or builds target meshes, and packages only qualifying routes. Root-template and named-stats paths remain distinct records when their effective slots differ.

**Tech Stack:** Python 3.11+, pytest, JSON Schema, BG3 LSX/LSF/GR2 resources, Divine.exe for package round trips, existing ClothMorph position-patching utilities.

**Spec:** `docs/superpowers/specs/2026-08-29-clothmorph-class-first-coverage-design.md`

## Global Constraints

- Effective stats inheritance resolving to `Slot = "Underwear"` is the only inclusion rule.
- Display names, filenames, visual appearance, and substrings such as `thong`, `bikini`, or `underwear` are not classification evidence.
- Root-template and named-stats creation paths are separate ledger records when their slots differ.
- Sources are limited to base game, SCO, and Sindae.
- The retired mixed `ClothMorphUnderwearBCBPak_TEST.pak` is evidence only and must not be used as the new package baseline.
- Every dependency must match installed folder, name, UUID, and `Version64` exactly.
- Runtime must be declared when `RegisterExternalRefits` is used.
- `collision_free` requires calculated or gameplay evidence and is never assigned by default.
- Passing/native modes remain protected.
- Gameplay result fields remain `NOT RUN` until live evidence exists.

---

### Task 1: Create the slot-resolution model and fixtures

**Files:**
- Create: `workstreams/true_underwear/slot_resolver.py`
- Create: `workstreams/true_underwear/models.py`
- Create: `workstreams/true_underwear/tests/fixtures/armor_stats.txt`
- Create: `workstreams/true_underwear/tests/fixtures/root_templates.lsx`
- Create: `workstreams/true_underwear/tests/test_slot_resolver.py`

**Interfaces:**
- Produces: `resolve_slot(stats_name: str, stats: dict[str, StatRecord]) -> SlotResolution`
- Produces: `SlotResolution(slot: str | None, inheritance: tuple[str, ...], cycle: bool, missing_parent: str | None)`

- [ ] **Step 1: Write failing inheritance tests**

```python
def test_resolves_underwear_through_using_chain():
    records = parse_stats(FIXTURE_STATS)
    result = resolve_slot("NAMED_TRUE_UNDERWEAR", records)
    assert result.slot == "Underwear"
    assert result.inheritance == (
        "NAMED_TRUE_UNDERWEAR", "ARM_Underwear", "_Underwear"
    )

def test_vanity_root_does_not_inherit_named_underwear_slot():
    records = parse_stats(FIXTURE_STATS)
    result = resolve_slot("ARM_Vanity_Body_Citizen", records)
    assert result.slot == "VanityBody"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/true_underwear/tests/test_slot_resolver.py -v`

Expected: import or assertion failure because the resolver does not exist.

- [ ] **Step 3: Implement strict parsing and cycle detection**

```python
@dataclass(frozen=True)
class SlotResolution:
    slot: str | None
    inheritance: tuple[str, ...]
    cycle: bool = False
    missing_parent: str | None = None

def resolve_slot(stats_name: str, stats: dict[str, StatRecord]) -> SlotResolution:
    chain: list[str] = []
    seen: set[str] = set()
    current = stats_name
    while current:
        if current in seen:
            return SlotResolution(None, tuple(chain + [current]), cycle=True)
        seen.add(current)
        chain.append(current)
        record = stats.get(current)
        if record is None:
            return SlotResolution(None, tuple(chain), missing_parent=current)
        if record.slot:
            return SlotResolution(record.slot, tuple(chain))
        current = record.using
    return SlotResolution(None, tuple(chain))
```

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest workstreams/true_underwear/tests/test_slot_resolver.py -v`

Expected: all resolver tests pass.

- [ ] **Step 5: Commit**

```powershell
git add workstreams/true_underwear
git commit -m "feat: add strict underwear slot resolver"
```

### Task 2: Build the complete true-underwear inventory

**Files:**
- Create: `workstreams/true_underwear/inventory.py`
- Create: `workstreams/true_underwear/schema.json`
- Create: `workstreams/true_underwear/tests/test_inventory.py`
- Create: `workstreams/true_underwear/evidence/TRUE_UNDERWEAR_LEDGER.json`
- Create: `workstreams/true_underwear/evidence/TRUE_UNDERWEAR_LEDGER.md`

**Interfaces:**
- Consumes: `resolve_slot`
- Produces: `build_inventory(source_roots: SourceRoots) -> list[GarmentRecord]`
- Produces one record per concrete tuple defined in the spec.

- [ ] **Step 1: Write failing classification tests**

```python
def test_inventory_contains_only_effective_underwear_slots(tmp_sources):
    records = build_inventory(tmp_sources)
    assert records
    assert {r.effective_slot for r in records} == {"Underwear"}

def test_root_and_named_stats_mismatch_are_separate_records(tmp_sources):
    all_paths = build_all_creation_paths(tmp_sources)
    wedding = [r for r in all_paths if r.display_name == "Wedding Body Suit"]
    assert {r.effective_slot for r in wedding} == {"Underwear", "VanityBody"}
    assert len({r.creation_path for r in wedding}) == 2
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/true_underwear/tests/test_inventory.py -v`

- [ ] **Step 3: Implement source discovery for base game, SCO, and Sindae**

The implementation must reject records with unresolved inheritance and write them to `evidence/TRUE_UNDERWEAR_REJECTIONS.json`; it must not silently exclude them.

- [ ] **Step 4: Generate ledgers and assert completeness**

```python
records = build_inventory(source_roots)
assert all(r.effective_slot == "Underwear" for r in records)
assert not [r for r in records if r.disposition == "UNCLASSIFIED"]
write_json(records, ledger_path)
```

- [ ] **Step 5: Run GREEN and schema validation**

Run: `python -m pytest workstreams/true_underwear/tests -v`

Expected: all tests pass and the JSON ledger validates against `schema.json`.

- [ ] **Step 6: Commit**

```powershell
git add workstreams/true_underwear
git commit -m "feat: inventory true underwear slot routes"
```

### Task 3: Audit route and mesh provenance

**Files:**
- Create: `workstreams/true_underwear/route_audit.py`
- Create: `workstreams/true_underwear/tests/test_route_audit.py`
- Create: `workstreams/true_underwear/evidence/TRUE_UNDERWEAR_ROUTE_AUDIT.json`

**Interfaces:**
- Produces: `audit_routes(records, visual_banks, refit_maps) -> list[RouteAudit]`

- [ ] **Step 1: Write failing tests for missing and contaminated routes**

```python
def test_audit_rejects_vanity_source_in_true_underwear_package():
    audit = audit_routes([VANITY_WEDDING_RECORD], BANKS, MAPS)
    assert audit[0].status == "OUT_OF_SCOPE"

def test_native_bcb_route_is_protected_passthrough():
    result = audit_one(TRUE_UNDERWEAR_BCB_RECORD)
    assert result.bcb.target_vr == result.source_vr
    assert result.bcb.protected is True
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/true_underwear/tests/test_route_audit.py -v`

- [ ] **Step 3: Implement exact VR/path/hash provenance**

Every target must name its source, body mode, path, SHA-256, and evidence status. Reused targets without gameplay evidence remain `READY FOR TEST`, not `ACCEPTED`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest workstreams/true_underwear/tests -v`

- [ ] **Step 5: Commit**

```powershell
git add workstreams/true_underwear
git commit -m "feat: audit true underwear route provenance"
```

### Task 4: Build the true-underwear TEST PAK

**Files:**
- Create: `workstreams/true_underwear/build_pak.py`
- Create: `workstreams/true_underwear/verify_pak.py`
- Create: `workstreams/true_underwear/tests/test_package_contract.py`
- Create: `workstreams/true_underwear/package/Mods/ClothMorphTrueUnderwearTest/meta.lsx`
- Create: `workstreams/true_underwear/package/Mods/ClothMorphTrueUnderwearTest/ScriptExtender/Config.json`
- Create: `workstreams/true_underwear/package/Mods/ClothMorphTrueUnderwearTest/ScriptExtender/Lua/BootstrapServer.lua`
- Create: `workstreams/true_underwear/package/Mods/ClothMorphTrueUnderwearTest/ScriptExtender/Lua/RefitMaps.lua`

**Interfaces:**
- Consumes: `TRUE_UNDERWEAR_LEDGER.json` and route audit.
- Produces: `ClothMorphTrueUnderwear_TEST.pak` outside Git-tracked paths.

- [ ] **Step 1: Write failing dependency and slot tests**

```python
def test_package_declares_runtime_and_all_source_dependencies(package_tree):
    deps = read_dependencies(package_tree / "Mods/ClothMorphTrueUnderwearTest/meta.lsx")
    assert RUNTIME_IDENTITY in deps
    assert required_source_identities(ledger) <= set(deps)

def test_package_has_zero_vanity_routes(package_tree):
    assert not [r for r in packaged_records(package_tree) if r.effective_slot == "VanityBody"]
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/true_underwear/tests/test_package_contract.py -v`

- [ ] **Step 3: Implement minimal package builder**

The bootstrap must fail closed if Runtime is unavailable and must log the exact number of registered routes. Dependencies must be generated from exact installed metadata records, not hand-written labels.

- [ ] **Step 4: Pack and fresh-extract**

Run the workspace-configured `Divine.exe` using BG3 pack/extract modes. Write source, stage, package, and fresh-extraction manifests.

- [ ] **Step 5: Run complete package verification**

Run: `python workstreams/true_underwear/verify_pak.py`

Expected: zero errors, zero VanityBody routes, exact dependency identities, exact route count, and fresh-extraction equality.

- [ ] **Step 6: Commit source and evidence, excluding generated PAK/GR2**

```powershell
git add workstreams/true_underwear
git commit -m "feat: build true underwear test package"
```

### Task 5: Produce the gameplay card

**Files:**
- Create: `workstreams/true_underwear/TRUE_UNDERWEAR_TEST_CARD.md`
- Create: `workstreams/true_underwear/TRUE_UNDERWEAR_GAMEPLAY_RESULTS.md`
- Test: `workstreams/true_underwear/tests/test_test_card.py`

- [ ] **Step 1: Write a failing test that every packaged item appears in the card**
- [ ] **Step 2: Generate exact spawn commands, route expectations, protected controls, and rollback instructions**
- [ ] **Step 3: Run `python -m pytest workstreams/true_underwear/tests -v`**
- [ ] **Step 4: Leave every gameplay row `NOT RUN`**
- [ ] **Step 5: Commit**

```powershell
git add workstreams/true_underwear
git commit -m "docs: add true underwear gameplay card"
```

