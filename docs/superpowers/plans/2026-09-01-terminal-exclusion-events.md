# ClothMorph Terminal Exclusion Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add append-only, fail-closed terminal exclusion events so an exact release-ledger route can stop blocking only after it satisfies the approved exclusion policy.

**Architecture:** A dedicated exclusion module validates canonical event digests, reason-specific evidence, protected impact, and record bindings. Generation consumes a hash-locked local exclusion-event directory, attaches only valid newest events, and audits excluded records separately; invalid events never change `release_blocking`.

**Tech Stack:** Python 3.12, pytest, standard-library JSON/hash/path handling.

**Spec:** `docs/superpowers/specs/2026-09-01-clothmorph-terminal-exclusion-policy.md`

## Global Constraints

- Never edit the protected registry/manifest or accepted files.
- Never auto-create an exclusion from a blocker code, display name, or failed package.
- Exclusion events are append-only and bind exact `record_id`, `identity_sha256`, source profile, mode, evidence hashes, and protected-impact result.
- `OUT_OF_SCOPE_WITH_PROOF` is terminal only with a valid event and `release_blocking=false`.
- The accepted Tiefling provider cannot be excluded or regraded.
- Invalid/missing/conflicting/revoked events remain release-blocking and appear in explicit audit sets.
- No live BG3, PAK installation, Runtime cleanup, or gameplay mutation is in scope.

---

### Task 1: Define and validate exclusion events

**Files:**
- Create: `workstreams/release_master_ledger/exclusions.py`
- Create: `workstreams/release_master_ledger/tests/test_exclusions.py`
- Modify: `workstreams/release_master_ledger/__init__.py`

**Interfaces:**
- `canonical_exclusion_payload(event: Mapping[str, object]) -> str`
- `exclusion_event_id(event: Mapping[str, object]) -> str`
- `validate_exclusion_event(event, *, ledger_record, evidence_hashes) -> list[str]`
- `select_current_exclusion(events, record_id, mode) -> ExclusionSelection`

- [ ] **Step 1: Write RED tests for digest, record binding, reasons, evidence, protected impact, and Tiefling prohibition**

```python
def test_valid_event_binds_record_and_digest():
    event = exclusion_fixture()
    event["event_id"] = exclusion_event_id(event)
    assert validate_exclusion_event(event, ledger_record=RECORD, evidence_hashes=HASHES) == []

def test_tiefling_record_cannot_be_excluded():
    errors = validate_exclusion_event(
        exclusion_fixture(record_id=TIEFLING_RECORD_ID),
        ledger_record=TIEFLING_RECORD,
        evidence_hashes=HASHES,
    )
    assert "EXCLUSION_FORBIDDEN_ACCEPTED_TIEFLING" in errors
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_exclusions.py -v`

Expected: import failure because `exclusions.py` does not exist.

- [ ] **Step 3: Implement exact schema/reason validation and newest-event selection**

Reject blank binding fields, non-uppercase hashes, unknown reasons, missing reason-specific evidence, protected mutations, mismatched record identity, duplicate event IDs, same-time conflicting events, and a revocation without a prior event.

- [ ] **Step 4: Run GREEN and commit**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_exclusions.py -v`

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: validate terminal exclusion events"
```

### Task 2: Add exclusion input configuration and attachment

**Files:**
- Modify: `workstreams/release_master_ledger/configuration.py`
- Modify: `workstreams/release_master_ledger/generate.py`
- Modify: `workstreams/release_master_ledger/models.py`
- Modify: `workstreams/release_master_ledger/schema.json`
- Modify: `workstreams/release_master_ledger/validation.py`
- Create: `workstreams/release_master_ledger/tests/test_exclusion_generation.py`
- Create ignored: `workstreams/release_master_ledger/local/exclusion_events/`

**Interfaces:**
- Configuration accepts an optional canonical local `exclusion_events_dir` inside the workstream `local/` boundary.
- Generated records carry `terminal_exclusion` as either a validated event summary or `null`.

- [ ] **Step 1: Write RED tests for path containment, hash-before-parse, invalid-event refusal, and valid attachment**
- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_exclusion_generation.py -v`

- [ ] **Step 3: Implement local-only discovery and exact event attachment**

Sort event files by normalized relative path, hash each before parsing, validate against the reconciled record, and attach only the selected valid event. Never rewrite an event or evidence file.

- [ ] **Step 4: Require full generated-document validation**

Update `validate_generated_ledger()` so a record with `OUT_OF_SCOPE_WITH_PROOF` or `release_blocking=false` fails unless its event validates.

- [ ] **Step 5: Run GREEN and commit**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_exclusion_generation.py workstreams/release_master_ledger/tests/test_generated_validation.py -v`

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: attach hash-locked exclusion events"
```

### Task 3: Make terminal audit behavior explicit

**Files:**
- Modify: `workstreams/release_master_ledger/audit.py`
- Modify: `workstreams/release_master_ledger/generate.py`
- Modify: `workstreams/release_master_ledger/PUBLIC_CHECKPOINT.md`
- Modify: `workstreams/release_master_ledger/tests/test_audit.py`
- Modify: `workstreams/release_master_ledger/tests/test_local_integration.py`

**Interfaces:**
- Audit emits `excluded_with_proof`, `exclusion_validation_failures`, and `excluded_but_packaged`.
- `OUT_OF_SCOPE_WITH_PROOF` is omitted from `in_scope_nonterminal` only when the event is valid and no package/provider still claims the route.

- [ ] **Step 1: Write RED tests for valid terminal exclusion and every invalid branch**

Include packaged-route conflict, missing evidence, protected impact, stale event, identity mismatch, forbidden reason, and release-blocking still true.

- [ ] **Step 2: Run RED**

Run: `python -m pytest workstreams/release_master_ledger/tests/test_audit.py -v`

- [ ] **Step 3: Implement exact audit sets without altering other terminal states**
- [ ] **Step 4: Run full verification**

Run: `python -m pytest workstreams/release_master_ledger workstreams/coverage_ledger workstreams/true_underwear workstreams/vanitybody -q`

Run the real current generator twice and require identical hashes. With no approved exclusion events present, current record counts and nonterminal counts must not decrease.

- [ ] **Step 5: Commit**

```powershell
git add workstreams/release_master_ledger
git commit -m "feat: audit evidence-backed exclusions"
```
