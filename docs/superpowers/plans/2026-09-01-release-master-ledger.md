# ClothMorph Source-Complete Release Master Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical `REMAINING_TARGET_MASTER_LEDGER.json` generator and a current, hash-locked local ledger that represents every registered release-source observation exactly once, reconciles all 32 immutable protected records without mutation, and reports source/identity/evidence gaps as release blockers.

**Architecture:** Add a new `workstreams/release_master_ledger` package. It reads only explicitly registered, SHA-256-pinned evidence inputs; converts each source into a normalized observation envelope; joins only evidence with the same canonical concrete identity; emits one deterministic record per identity; and produces a separate anti-omission audit. Machine-local paths and generated ledgers stay under the workstream's ignored `local/` directory, while schema, import logic, synthetic fixtures, tests, and a public evidence-boundary checkpoint are committed.

**Tech Stack:** Python 3.12, pytest, Python standard library (`dataclasses`, `hashlib`, `json`, `pathlib`), JSON artifacts.

**Spec:** `C:\Claude Projects\BG3 Mods\ChatGPT Work Files\ClothMorph_Shippable_Release_Program_20260830\docs\superpowers\specs\2026-08-30-clothmorph-shippable-release-program-design.md` (SHA-256 `5B4DECF16701F576E2BFAA1F40F4D0818FA91114EF731A1EC5F8ED0F61C72487`; sections 7-9, 18-19)

## Global Constraints

- Do not read or write live BG3/BG3MM/profile/save paths. Evidence inputs are offline retained artifacts only.
- Do not edit, copy over, reset, clean, commit, or reuse `C:\Claude Projects\BG3 Mods\New-Body-and-Clothing-Morph\.worktrees\bcb-cleanup-runtime`.
- Do not implement or modify Runtime, schema-7, provider API, cleanup API, PAK, GR2, installer, or rollback code in this plan.
- Preserve `PROTECTED_ACCEPTANCE_REGISTRY.json` SHA-256 `7AFA8A00E8D491F419A32851D316C74C4E283DA4E0E4C2DBFB1E968FF9119924` and `PROTECTED_HASH_MANIFEST.json` SHA-256 `56DD4FB852166D587FDAC0B35746CA222CA935B42F893FBA0DAE7F1EFB568F8A` byte-for-byte.
- Reconcile exactly 32 protected registry records and 32 protected files. `GAMEPLAY_PASS`, `USER_ACCEPTED_RESIDUAL`, and `PROTECTED_SOURCE_NATIVE` remain immutable. The four `PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY` Recluse records remain gameplay-unproven.
- Preserve `ClothMorphTieflingBT1_TEST.pak` UUID `b57bab2c-5679-5445-8fee-ca8c282990a5`, byte count `844122`, and SHA-256 `01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141`; this plan never writes the PAK.
- The canonical record key follows spec section 8.1: source module UUID, source-profile digest, creation-path kind, root UUID, named Stats entry, full Stats-inheritance digest, effective slot, body tuple, ordered source VRs, and ordered component-contract digest.
- The output record contains every field family in spec section 9.2. Binding fields cannot be blank. Unknown evidence uses stable uppercase blocker codes; it is never inferred.
- Dispositions use the spec section 8.5 vocabulary. `UNCLASSIFIED` is construction-only and must be zero in emitted output.
- The anti-omission audit emits exactly `missing_from_ledger`, `duplicate_identity`, `unreferenced_prior_evidence`, `packaged_without_ledger`, `ledger_without_source`, and `in_scope_nonterminal`.
- A current ledger may be generated while `source_complete=false` and `release_complete=false`; the report must name every blocking set and must never promote offline/package evidence to gameplay acceptance.
- The current registry-scoped SCO/Sindae ledger, 68-row true-underwear ledger, 271-row VanityBody ledger, BCBScantily contracts, permissions manifest, Recluse package evidence, and named-target evidence are inputs, not authorities that can rewrite protected acceptance.
- All implementation follows strict RED-GREEN-REFACTOR. Each new behavior gets a test that fails for the expected missing behavior before production code is written.

## File Structure

- `workstreams/release_master_ledger/models.py`: immutable normalized observation and ledger-record data structures.
- `workstreams/release_master_ledger/identity.py`: canonical JSON serialization and identity digest construction.
- `workstreams/release_master_ledger/validation.py`: binding-field, status, hash, and record-shape validation without third-party schema dependencies.
- `workstreams/release_master_ledger/configuration.py`: canonical local-config boundary, input existence/hash verification, and output-boundary validation.
- `workstreams/release_master_ledger/adapters.py`: protected, workstream-ledger, permission, package, and named-target observation adapters.
- `workstreams/release_master_ledger/reconcile.py`: exact-identity joins, precedence, blocker union, and protected immutability enforcement.
- `workstreams/release_master_ledger/audit.py`: exact-once and closure-set computation.
- `workstreams/release_master_ledger/generate.py`: deterministic local JSON/Markdown generation.
- `workstreams/release_master_ledger/schema.json`: committed public contract for the generated ledger envelope and records.
- `workstreams/release_master_ledger/tests/`: synthetic unit tests plus opt-in hash-locked local integration tests.
- `workstreams/release_master_ledger/local/`: ignored local configuration and generated current evidence.

---

### Task 1: Define the canonical identity and ledger schema

**Files:**
- Create: `workstreams/release_master_ledger/__init__.py`
- Create: `workstreams/release_master_ledger/models.py`
- Create: `workstreams/release_master_ledger/identity.py`
- Create: `workstreams/release_master_ledger/validation.py`
- Create: `workstreams/release_master_ledger/schema.json`
- Create: `workstreams/release_master_ledger/pytest.ini`
- Create: `workstreams/release_master_ledger/tests/test_identity.py`
- Create: `workstreams/release_master_ledger/tests/test_validation.py`

**Interfaces:**
- Produces: `canonical_json(value: object) -> str`
- Produces: `sha256_text(value: str) -> str`
- Produces: `build_identity(fields: CanonicalIdentityFields) -> tuple[str, str]`
- Produces: `validate_record(record: dict[str, object]) -> list[str]`
- Produces: `Observation` and `LedgerRecord` dataclasses whose `to_dict()` output is deterministic.

- [ ] **Step 1: Write RED identity tests**

```python
def test_identity_is_order_stable_and_binds_every_spec_field():
    fields = CanonicalIdentityFields(
        source_module_uuid="11111111-1111-1111-1111-111111111111",
        source_profile_digest="A" * 64,
        creation_path_kind="root_template",
        root_template_uuid="22222222-2222-2222-2222-222222222222",
        stats_entry="ARM_Test",
        inheritance_digest="B" * 64,
        effective_slot="Underwear",
        body_tuple=("Human", "Female", "BT1", "Regular", "HUM_F"),
        ordered_source_vrs=("33333333-3333-3333-3333-333333333333",),
        component_contract_digest="C" * 64,
    )
    canonical, digest = build_identity(fields)
    assert canonical == canonical_json(fields.to_dict())
    assert len(digest) == 64
    assert digest == sha256_text(canonical)

def test_identity_changes_when_ordered_source_vrs_change_order():
    first = identity_fixture(ordered_source_vrs=("vr-a", "vr-b"))
    second = identity_fixture(ordered_source_vrs=("vr-b", "vr-a"))
    assert build_identity(first)[1] != build_identity(second)[1]
```

- [ ] **Step 2: Run RED**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_identity.py -v`

Expected: collection fails because `workstreams.release_master_ledger.identity` does not exist.

- [ ] **Step 3: Implement deterministic identity construction and dataclasses**

```python
def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()

def build_identity(fields: CanonicalIdentityFields) -> tuple[str, str]:
    canonical = canonical_json(fields.to_dict())
    return canonical, sha256_text(canonical)
```

- [ ] **Step 4: Write RED validation tests for blank fields, lowercase/short hashes, missing modes, and `UNCLASSIFIED` output**

```python
def test_binding_blank_is_rejected():
    record = complete_record_fixture()
    record["source_module"]["uuid"] = ""
    assert "BLANK:source_module.uuid" in validate_record(record)

def test_emitted_record_requires_all_four_mode_routes():
    record = complete_record_fixture()
    del record["mode_routes"]["external"]
    assert "MISSING:mode_routes.external" in validate_record(record)

def test_unclassified_cannot_be_emitted():
    record = complete_record_fixture()
    record["disposition"] = "UNCLASSIFIED"
    assert "FORBIDDEN_DISPOSITION:UNCLASSIFIED" in validate_record(record)
```

- [ ] **Step 5: Implement the standard-library validator and schema envelope, then run GREEN**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_identity.py workstreams/release_master_ledger/tests/test_validation.py -v`

Expected: all Task 1 tests pass with no warnings.

- [ ] **Step 6: Commit**

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: define release master ledger identity contract"
```

### Task 2: Add the hash-locked evidence configuration boundary

**Files:**
- Create: `workstreams/release_master_ledger/.gitignore`
- Create: `workstreams/release_master_ledger/configuration.py`
- Create: `workstreams/release_master_ledger/source_manifest.example.json`
- Create: `workstreams/release_master_ledger/tests/test_configuration.py`
- Create: `workstreams/release_master_ledger/tests/fixtures/evidence/minimal.json`

**Interfaces:**
- Produces: `load_local_configuration() -> LocalConfiguration`
- Produces: `verify_evidence_inputs(config: LocalConfiguration) -> list[VerifiedInput]`
- Produces: `validate_output_path(path: Path, workstream_root: Path) -> Path`
- `VerifiedInput` includes `input_id`, `kind`, `path`, `bytes`, `expected_sha256`, and `actual_sha256`.

- [ ] **Step 1: Write RED tests for canonical config, hash mismatch, missing input, and output escape**

```python
def test_hash_mismatch_fails_before_adapter_reads_json(tmp_path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("not json", encoding="utf-8")
    config = configuration_fixture(evidence, expected_sha256="0" * 64)
    with pytest.raises(EvidenceIntegrityError, match="EVIDENCE_HASH_MISMATCH"):
        verify_evidence_inputs(config)

def test_generated_output_cannot_escape_local_generated(workstream_root):
    with pytest.raises(ConfigurationError, match="OUTPUT_OUTSIDE_LOCAL_GENERATED"):
        validate_output_path(workstream_root.parent / "escaped.json", workstream_root)
```

- [ ] **Step 2: Run RED**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_configuration.py -v`

Expected: import failure because the configuration boundary does not exist.

- [ ] **Step 3: Implement fail-closed path and hash verification**

The loader accepts only `workstreams/release_master_ledger/local/config.json`. Every registered input is hashed before JSON parsing. Generated paths must resolve under `workstreams/release_master_ledger/local/generated`. The workstream `.gitignore` ignores `local/` and no other path.

- [ ] **Step 4: Populate the example manifest with required input kinds**

The example contains these stable input IDs with nonfunctional example paths: `protected_registry_v1`, `protected_hash_manifest_v1`, `coverage_master_registry_scoped`, `coverage_raw_registry_scoped`, `true_underwear_ledger_v2`, `true_underwear_route_audit`, `vanitybody_ledger_bcbpak`, `vanitybody_route_protection`, `bcbscantily_class_ledger`, `bcbscantily_item_contracts`, `external_permission_manifest_v1`, `recluse_provider_contract_v2`, `soul_vest_alt_decision`, `padded_findings`, `bard_findings`, and `source_profile_inventory`.

- [ ] **Step 5: Run GREEN and the existing suites**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_configuration.py workstreams/coverage_ledger workstreams/true_underwear workstreams/vanitybody -q`

Expected: Task 2 tests pass; existing suite results retain zero failures.

- [ ] **Step 6: Commit**

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: add hash-locked release evidence boundary"
```

### Task 3: Import protected controls and bounded workstream observations

**Files:**
- Create: `workstreams/release_master_ledger/adapters.py`
- Create: `workstreams/release_master_ledger/tests/test_protected_adapter.py`
- Create: `workstreams/release_master_ledger/tests/test_workstream_adapters.py`
- Create: `workstreams/release_master_ledger/tests/test_permission_adapter.py`
- Create: `workstreams/release_master_ledger/tests/fixtures/protected_registry.json`
- Create: `workstreams/release_master_ledger/tests/fixtures/protected_manifest.json`
- Create: `workstreams/release_master_ledger/tests/fixtures/coverage_records.json`
- Create: `workstreams/release_master_ledger/tests/fixtures/underwear_records.json`
- Create: `workstreams/release_master_ledger/tests/fixtures/vanity_records.json`
- Create: `workstreams/release_master_ledger/tests/fixtures/permission_records.json`

**Interfaces:**
- Produces: `read_observations(verified_input: VerifiedInput) -> list[Observation]`
- Produces adapter functions for protected registry, hash manifest, coverage, true-underwear, VanityBody, BCBScantily, permission, package, and named-target inputs.
- Every observation carries `observation_id`, `input_id`, `input_sha256`, normalized identity fields, evidence status, blocker codes, evidence pointers, and source payload unchanged under `raw_evidence` only when required for audit traceability.

- [ ] **Step 1: Write RED protected-import tests**

```python
def test_protected_adapter_preserves_status_and_route_fingerprint():
    observations = adapt_protected_registry(load_fixture("protected_registry.json"), VERIFIED_REGISTRY)
    protected = observations[0]
    assert protected.authority == "IMMUTABLE_V1"
    assert protected.protected_relations["registry_ids"] == ["fixture-protected-1"]
    assert protected.protected_relations["route_fingerprint"] == "D" * 64

def test_package_only_protection_does_not_become_gameplay_acceptance():
    observation = protected_fixture(status="PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY")
    normalized = adapt_one_protected(observation, VERIFIED_REGISTRY)
    assert normalized.disposition == "PACKAGE_ONLY_PROTECTED"
    assert normalized.release_blocking is True
```

- [ ] **Step 2: Run protected RED, implement exact status mapping, and run GREEN**

Status mapping is exact: `GAMEPLAY_PASS` and `USER_ACCEPTED_RESIDUAL` to `ACCEPTED_PROTECTED`; `PROTECTED_SOURCE_NATIVE` to `SOURCE_NATIVE_PROTECTED`; `PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY` to `PACKAGE_ONLY_PROTECTED` with `GAMEPLAY_UNASSESSED_PACKAGE_ONLY`.

- [ ] **Step 3: Write RED workstream and permission adapter tests**

```python
def test_underwear_missing_route_remains_blocking():
    observation = adapt_true_underwear([underwear_fixture(disposition="MISSING ROUTE / BUILD")], VERIFIED_UNDERWEAR)[0]
    assert observation.disposition == "BLOCKED_WITH_CAUSE"
    assert "TARGET_ROUTE_UNRESOLVED" in observation.blocker_codes

def test_permission_scope_mesh_is_an_observation_not_a_garment_assumption():
    observations = adapt_permission_manifest(permission_fixture(scope_resolved=["HUM_F_Test.GR2"]), VERIFIED_PERMISSION)
    assert observations[0].observation_kind == "PERMISSION_SCOPE_MESH"
    assert observations[0].classification["effective_slot"] == "AMBIGUOUS_SLOT"
    assert "ITEM_CONTRACT_UNRESOLVED" in observations[0].blocker_codes
```

- [ ] **Step 4: Implement adapters without extrapolation**

Coverage dispositions map to spec vocabulary; the 68 true-underwear rows remain blocking until route contracts exist; VanityBody `READY FOR TEST` becomes `DEFERRED_WITH_CAUSE` unless its complete spec-section-9 contract is present; BCBScantily missing VR/component evidence remains blocking; permission mesh names never become wearable routes without item/creation-path/VR joins; package evidence never becomes gameplay evidence.

- [ ] **Step 5: Run GREEN and full workstream suite**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_protected_adapter.py workstreams/release_master_ledger/tests/test_workstream_adapters.py workstreams/release_master_ledger/tests/test_permission_adapter.py workstreams/coverage_ledger workstreams/true_underwear workstreams/vanitybody -q`

Expected: zero failures and no test-output warnings.

- [ ] **Step 6: Commit**

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: normalize release ledger evidence inputs"
```

### Task 4: Reconcile exact identities and compute the anti-omission audit

**Files:**
- Create: `workstreams/release_master_ledger/reconcile.py`
- Create: `workstreams/release_master_ledger/audit.py`
- Create: `workstreams/release_master_ledger/tests/test_reconcile.py`
- Create: `workstreams/release_master_ledger/tests/test_audit.py`

**Interfaces:**
- Produces: `reconcile_observations(observations: Iterable[Observation]) -> ReconciliationResult`
- Produces: `build_completeness_audit(result: ReconciliationResult, inventories: InventorySets) -> dict[str, object]`
- `ReconciliationResult` contains deterministic `records`, `observation_to_record`, and `conflicts`.

- [ ] **Step 1: Write RED tests for exact joins, protected precedence, and unresolved conflicts**

```python
def test_same_canonical_identity_joins_observations_once():
    result = reconcile_observations([coverage_observation(), underwear_observation()])
    assert len(result.records) == 1
    assert set(result.records[0].evidence_paths) == {"coverage.json", "underwear.json"}

def test_protected_fields_cannot_be_overwritten_by_newer_nonprotected_evidence():
    protected = protected_observation(target_path="protected.gr2", payload_hash="A" * 64)
    proposed = correction_observation(target_path="replacement.gr2", payload_hash="B" * 64)
    result = reconcile_observations([protected, proposed])
    assert result.records[0].mode_routes["bcb"]["target_paths"] == ["protected.gr2"]
    assert "PROTECTED_ROUTE_CONFLICT" in result.records[0].blocker_codes

def test_incomplete_identity_never_merges_on_display_name():
    first = incomplete_observation(display_name="Same Name", root_uuid="root-a")
    second = incomplete_observation(display_name="Same Name", root_uuid="root-b")
    assert len(reconcile_observations([first, second]).records) == 2
```

- [ ] **Step 2: Run RED, implement deterministic exact-identity reconciliation, and run GREEN**

Precedence is `IMMUTABLE_V1` first, then exact item gameplay, package/static evidence, design/classification evidence, and unresolved observations. Conflicting evidence is retained as evidence and blocker codes; it is never silently discarded.

- [ ] **Step 3: Write RED anti-omission tests for all six required sets**

```python
def test_missing_source_observation_is_reported():
    audit = build_completeness_audit(result_with_records("obs-1"), inventories(source_observations={"obs-1", "obs-2"}))
    assert audit["missing_from_ledger"] == ["obs-2"]

def test_in_scope_nonterminal_is_not_hidden_by_zero_unclassified():
    audit = build_completeness_audit(result_with_disposition("DEFERRED_WITH_CAUSE"), inventories())
    assert audit["unclassified_count"] == 0
    assert audit["in_scope_nonterminal"]
    assert audit["source_complete"] is False
    assert audit["release_complete"] is False
```

- [ ] **Step 4: Implement exact sorted audit sets and generated summaries**

`source_complete` is true only when the first five omission/ownership sets are empty and every required source profile is complete. `release_complete` additionally requires `in_scope_nonterminal` empty and all spec-section-19 gates true. This task has no authority to set later package/gameplay/installer gates true.

- [ ] **Step 5: Run GREEN and mutation check**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_reconcile.py workstreams/release_master_ledger/tests/test_audit.py -v`

Then temporarily invert one protected payload hash in the synthetic fixture, confirm the protected-conflict test fails, restore the fixture, and rerun the same command to green.

- [ ] **Step 6: Commit**

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: reconcile canonical routes and audit omissions"
```

### Task 5: Generate the current hash-locked master ledger and checkpoint

**Files:**
- Create: `workstreams/release_master_ledger/generate.py`
- Create: `workstreams/release_master_ledger/PUBLIC_CHECKPOINT.md`
- Create: `workstreams/release_master_ledger/tests/test_generate.py`
- Create: `workstreams/release_master_ledger/tests/test_local_integration.py`
- Create ignored: `workstreams/release_master_ledger/local/config.json`
- Generate ignored: `workstreams/release_master_ledger/local/generated/REMAINING_TARGET_MASTER_LEDGER.json`
- Generate ignored: `workstreams/release_master_ledger/local/generated/REMAINING_TARGET_MASTER_LEDGER.md`
- Generate ignored: `workstreams/release_master_ledger/local/generated/RELEASE_LEDGER_COMPLETENESS_AUDIT.json`
- Generate ignored: `workstreams/release_master_ledger/local/generated/EVIDENCE_INPUT_MANIFEST.json`

**Interfaces:**
- Produces: `generate(config: LocalConfiguration) -> GenerationResult`
- CLI: `python -m workstreams.release_master_ledger.generate`

- [ ] **Step 1: Write RED deterministic-generation tests**

```python
def test_generation_is_byte_deterministic(tmp_path):
    first = generate(synthetic_config(tmp_path / "first"))
    second = generate(synthetic_config(tmp_path / "second"))
    assert first.ledger_sha256 == second.ledger_sha256
    assert first.audit_sha256 == second.audit_sha256

def test_summary_is_recomputed_from_records(tmp_path):
    result = generate(synthetic_config(tmp_path))
    payload = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    assert payload["summary"]["record_count"] == len(payload["records"])
```

- [ ] **Step 2: Run RED, implement deterministic JSON/Markdown generation, and run GREEN**

JSON uses `indent=2`, `sort_keys=True`, UTF-8, and one trailing newline. Markdown is derived from the generated JSON and cannot contain hand-entered counts.

- [ ] **Step 3: Create the ignored local config with current exact evidence identities**

Pin the five release authorities from Global Constraints and the current local evidence. At minimum pin these observed inputs: coverage master, coverage raw, true-underwear ledger, true-underwear route audit, VanityBody ledger, VanityBody route/protection evidence, BCBScantily class ledger SHA-256 `266575498CFA9A6130A693DFBB90B3B30A57945CA499C401BF1F9D3595BBC1A4`, BCBScantily item contracts SHA-256 `2914AA90144E9AF8529993A22580F4391080743C8061DA44DD2F5211BD1BBBBC`, external permission manifest SHA-256 `C02DFB56B6F246C7902F31EA371405763F1BB555CA5CE016CB06A31895EBA908`, Recluse provider contract SHA-256 `C56B0208C09D04531258BFCC01BF7319C05EC47C36FCA750C84428A4CEC0DA01`, and Soul Vest Alt decision SHA-256 `2FE915214CFAAB8953A923EACA47FCF98803ED8A37BAA257D03DF5FD78E67E23`.

- [ ] **Step 4: Write and run the opt-in current-evidence integration test**

The integration test is marked `integration` and skips when the canonical local config is absent. With the created config, require: all registered hashes match; protected registry and manifest counts are exactly 32; status distribution is 25 gameplay pass, 1 accepted residual, 2 source-native, and 4 package-only; bounded input channel counts remain 2,534 coverage records, 68 true-underwear records, and 271 VanityBody records; `UNCLASSIFIED` output is zero; and every omission/nonterminal set is emitted even when nonempty.

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger/tests/test_local_integration.py -v`

- [ ] **Step 5: Generate current artifacts and verify truthful status**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m workstreams.release_master_ledger.generate`

Verify the generated audit reports `release_complete=false`. Verify `source_complete` strictly from the audit output; do not predetermine it. Confirm every blocker has a stable code, evidence pointer, owner, next admissible action, and `release_blocking` flag.

- [ ] **Step 6: Run full verification**

Run: `& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest workstreams/release_master_ledger workstreams/coverage_ledger workstreams/true_underwear workstreams/vanitybody -q`

Run: `git diff --check`

Run: `git status --short`

Expected: zero test failures; only committed workstream source/tests/checkpoint and this plan are tracked changes; local config/generated evidence remain ignored; no Runtime, protected authority, Tiefling, BCB cleanup, PAK, GR2, or live BG3 path appears in the diff.

- [ ] **Step 7: Commit**

```powershell
git add workstreams/release_master_ledger docs/superpowers/plans/2026-09-01-release-master-ledger.md
git commit -m "feat: generate ClothMorph release master ledger"
```

## Plan rulings

- Runtime/matrix contradictions found during preflight are out of scope for this ledger milestone. The normative Runtime matrix remains untouched; this plan consumes only the release-design ledger contract. Cost if wrong: later Runtime integration may require a field-name adapter, but no Runtime behavior or protected asset is changed here.
- Ignored local evidence in the clean `main` checkout is read-only input, not copied release authority. Each file must match its pinned hash before use. Cost if wrong: a retained evidence file that changes requires an explicit config/hash update and a full regeneration; the generator refuses silently drifted inputs.
- `source-complete` is an audited result, not a name-based claim. The generator is allowed to emit a useful canonical ledger with `source_complete=false` and explicit missing-source sets. Cost if wrong: the first ledger may expose additional inventory work instead of immediately closing the milestone, which is preferable to false completeness.
