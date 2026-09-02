import hashlib
import json
from pathlib import Path
from copy import deepcopy
from dataclasses import replace

import pytest

from workstreams.release_master_ledger.configuration import (
    ConfigurationError,
    EvidenceInput,
    LocalConfiguration,
    load_local_configuration,
)
from workstreams.release_master_ledger.audit import InventorySets, build_completeness_audit
from workstreams.release_master_ledger.exclusions import exclusion_event_id
from workstreams.release_master_ledger.identity import canonical_json, sha256_text
from workstreams.release_master_ledger.generate import (
    _attach_terminal_exclusions as _attach_terminal_exclusions_impl,
    _manifest_payload,
    DiscoveredExclusionEvent,
    discover_exclusion_events,
)
from workstreams.release_master_ledger.models import (
    CanonicalIdentityFields,
    LedgerRecord,
    Observation,
)
from workstreams.release_master_ledger.reconcile import reconcile_observations
from workstreams.release_master_ledger.validation import (
    _terminal_schema_contract_errors,
    validate_generated_ledger,
)
from workstreams.release_master_ledger.tests.test_validation import complete_record_fixture
from workstreams.release_master_ledger.tests.test_exclusions import (
    hard_contract_proof,
    proof_for,
    signed_event,
)


RECORD_ID = "LEDGER_" + "A" * 64
IDENTITY_SHA256 = "B" * 64
PROFILE_SHA256 = "C" * 64
RELEASE_MODES = ("vanilla", "sbbf", "bcb", "external")


def _mode_scope(terminal_state="NONTERMINAL", advertised=True):
    return {
        mode: {"advertised": advertised, "terminal_state": terminal_state}
        for mode in RELEASE_MODES
    }


def _terminal_exclusions():
    return {mode: None for mode in RELEASE_MODES}


def _attach_terminal_exclusions(records, events, evidence, **kwargs):
    kwargs.setdefault("independent_provider_claims", {})
    kwargs.setdefault("independent_package_claims", {})
    return _attach_terminal_exclusions_impl(
        records, events, evidence, **kwargs
    )


def _zero_claim_route():
    return {
        "behavior": "OUT_OF_SCOPE_WITH_PROOF",
        "target_vrs": [],
        "target_paths": [],
        "payload_hashes": [],
        "provider_id": "NO_PROVIDER_FOR_EXCLUDED_MODE",
        "provenance": "NO_PROVENANCE_FOR_EXCLUDED_MODE",
        "static_status": "NOT_APPLICABLE_OUT_OF_SCOPE",
        "gameplay_status": "NOT_APPLICABLE_OUT_OF_SCOPE",
        "save_reload_status": "NOT_APPLICABLE_OUT_OF_SCOPE",
    }


def _record() -> LedgerRecord:
    return LedgerRecord(
        record_id=RECORD_ID,
        canonical_identity="synthetic",
        identity_sha256=IDENTITY_SHA256,
        source_module={
            "folder": "SYNTHETIC_PROFILE", "version64": "1",
            "profile_digest": PROFILE_SHA256,
        },
        permission={}, creation_path={}, classification={"effective_slot": "Underwear"},
        body_tuple={"race": "Human", "sex": "Female", "body_type": "BT1"},
        source_route={},
        mode_routes={mode: _zero_claim_route() for mode in RELEASE_MODES},
        protected_relations={
            "registry_ids": [], "protected_consumers": [],
            "shared_assets": [], "forbidden_targets": [],
        },
        transformation={}, gates={},
        mode_scope=_mode_scope(),
        evidence_paths=(), evidence_hashes=(), disposition="DEFERRED_WITH_CAUSE",
        blocker_codes=("SOURCE_ROUTE_UNRESOLVED",), release_blocking=True,
        next_admissible_action="Recover source.",
        acceptance_event_id="UNKNOWN_ACCEPTANCE_EVENT",
        shipped_package_id="UNKNOWN_SHIPPED_PACKAGE",
        terminal_exclusion=_terminal_exclusions(),
    )


def _event(mode="sbbf") -> dict[str, object]:
    event: dict[str, object] = {
        "schema": "clothmorph.terminal-exclusion", "schema_version": 1,
        "record_id": RECORD_ID, "identity_sha256": IDENTITY_SHA256,
        "source_profile_id": "SYNTHETIC_PROFILE", "mode": mode,
        "reason": "SOURCE_ABSENT_EXACT_PROFILE",
        "reason_proof": {
            "exact_profile": {"id": "SYNTHETIC_PROFILE", "version": "1", "sha256": PROFILE_SHA256},
            "complete_source_inventory": {"result": "COMPLETE", "evidence_path": "evidence/source-audit.json", "evidence_sha256": "D" * 64},
            "zero_route_result": {"result": "ZERO_ROUTE", "evidence_path": "evidence/source-audit.json", "evidence_sha256": "D" * 64},
            "anti_omission": {"result": "PASS", "evidence_path": "evidence/source-audit.json", "evidence_sha256": "D" * 64},
        },
        "scope_statement": "Exclude only the synthetic SBBF route.",
        "attempted_architectures": [], "fixed_acceptance_gates": {},
        "evidence": [{"path": "evidence/source-audit.json", "sha256": "D" * 64, "claim": "source audit"}],
        "protected_impact": {
            "registry_ids": [], "shared_consumers": [], "shared_assets": [],
            "forbidden_targets": [], "result": "NO_PROTECTED_MUTATION",
        },
        "next_project_if_reopened": "Recover the exact source profile.",
        "approved_by": "Alan", "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
        "created_utc": "2026-09-01T12:00:00Z",
    }
    event["event_id"] = exclusion_event_id(event)
    return event


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest().upper()


def _full_record() -> LedgerRecord:
    data = complete_record_fixture()
    data["record_id"] = RECORD_ID
    data["mode_scope"] = _mode_scope()
    data["terminal_exclusion"] = _terminal_exclusions()
    data["mode_routes"]["sbbf"] = _zero_claim_route()
    return LedgerRecord(**data)


def _discovered(event: dict[str, object], *, path="history/synthetic.json") -> DiscoveredExclusionEvent:
    content = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return DiscoveredExclusionEvent(path, hashlib.sha256(content).hexdigest().upper(), event)


def _event_for_record(record: LedgerRecord) -> dict[str, object]:
    event = _event()
    event["record_id"] = record.record_id
    event["identity_sha256"] = record.identity_sha256
    event["source_profile_id"] = record.source_module["folder"]
    event["reason_proof"]["exact_profile"] = {
        "id": record.source_module["folder"],
        "version": record.source_module["version64"],
        "sha256": record.source_module["profile_digest"],
    }
    event["protected_impact"] = {
        "registry_ids": list(record.protected_relations["registry_ids"]),
        "shared_consumers": list(record.protected_relations["protected_consumers"]),
        "shared_assets": list(record.protected_relations["shared_assets"]),
        "forbidden_targets": list(record.protected_relations["forbidden_targets"]),
        "result": "NO_PROTECTED_MUTATION",
    }
    event["event_id"] = exclusion_event_id(event)
    return event


def _production_observation() -> Observation:
    """One real reconciler input whose routes still have pre-attachment defaults."""
    return Observation(
        observation_id="production-lifecycle-observation",
        observation_kind="WORKSTREAM_EVIDENCE",
        identity_fields=CanonicalIdentityFields(
            source_module_uuid="11111111-1111-1111-1111-111111111111",
            source_profile_digest=PROFILE_SHA256,
            creation_path_kind="root_template",
            root_template_uuid="22222222-2222-2222-2222-222222222222",
            stats_entry="ARM_ProductionLifecycle",
            inheritance_digest="E" * 64,
            effective_slot="Underwear",
            body_tuple=("Human", "Female", "BT1", "Regular", "HUM_F"),
            ordered_source_vrs=("source-vr",),
            component_contract_digest="F" * 64,
        ),
        source_reference="production-lifecycle.json",
        evidence_files=("production-lifecycle.json",),
        payload={
            "source_module": {
                "folder": "SYNTHETIC_PROFILE",
                "version64": "1",
                "profile_digest": PROFILE_SHA256,
            },
            "protected_relations": {
                "registry_ids": ["REGISTRY_REVIEWED"],
                "protected_consumers": ["UNACCEPTED_CONSUMER"],
                "shared_assets": ["Public/Synthetic/Shared.GR2"],
                "forbidden_targets": ["EMBEDDED_BODY_DATA"],
            },
            "disposition": "DEFERRED_WITH_CAUSE",
            "release_blocking": True,
            "next_admissible_action": "Recover source.",
        },
    )


def _production_events(record: LedgerRecord) -> tuple[DiscoveredExclusionEvent, ...]:
    discovered = []
    for index, mode in enumerate(RELEASE_MODES):
        event = _event_for_record(record)
        event["mode"] = mode
        event["scope_statement"] = f"Exclude only the synthetic {mode} route."
        event["created_utc"] = f"2026-09-01T12:0{index}:00Z"
        event["event_id"] = exclusion_event_id(event)
        discovered.append(_discovered(event, path=f"history/{mode}.json"))
    return tuple(discovered)


def _structural_event(reason: str, *, hard_contract: bool = False) -> dict[str, object]:
    proof = hard_contract_proof() if hard_contract else proof_for(reason)
    return signed_event(
        reason=reason,
        reason_proof=proof,
        attempted_architectures=proof.get("architecture_results", []),
        fixed_acceptance_gates=proof.get("fixed_gates", {}),
    )


def _add_extra(mapping: dict[str, object]) -> None:
    mapping["unexpected"] = "forbidden"


def _set(mapping: dict[str, object], key: str, value: object) -> None:
    mapping[key] = value


def test_configuration_refuses_an_exclusion_directory_outside_the_local_boundary(tmp_path, monkeypatch):
    from workstreams.release_master_ledger import configuration

    root = tmp_path / "release_master_ledger"
    local = root / "local"
    local.mkdir(parents=True)
    evidence = local / "evidence.json"
    digest = _write_json(evidence, {"records": []})
    (local / "config.json").write_text(json.dumps({
        "inputs": [{"input_id": "fixture", "kind": "COVERAGE", "path": "evidence.json", "expected_sha256": digest}],
        "output_path": "generated/ledger.json",
        "exclusion_events_dir": "../outside",
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "WORKSTREAM_ROOT", root)

    with pytest.raises(ConfigurationError, match="EXCLUSION_EVENTS_OUTSIDE_LOCAL"):
        load_local_configuration()


def test_configuration_requires_the_exact_canonical_exclusion_events_directory(
    tmp_path, monkeypatch,
):
    from workstreams.release_master_ledger import configuration

    root = tmp_path / "release_master_ledger"
    local = root / "local"
    local.mkdir(parents=True)
    evidence = local / "evidence.json"
    digest = _write_json(evidence, {"records": []})
    (local / "config.json").write_text(json.dumps({
        "inputs": [{
            "input_id": "fixture", "kind": "COVERAGE", "path": "evidence.json",
            "expected_sha256": digest,
        }],
        "output_path": "generated/ledger.json",
        "exclusion_events_dir": "nested/exclusion_events",
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "WORKSTREAM_ROOT", root)

    with pytest.raises(ConfigurationError, match="EXCLUSION_EVENTS_NOT_CANONICAL"):
        load_local_configuration()


def test_configuration_defaults_to_the_exact_canonical_exclusion_events_directory(
    tmp_path, monkeypatch,
):
    from workstreams.release_master_ledger import configuration

    root = tmp_path / "release_master_ledger"
    local = root / "local"
    local.mkdir(parents=True)
    evidence = local / "evidence.json"
    digest = _write_json(evidence, {"records": []})
    (local / "config.json").write_text(json.dumps({
        "inputs": [{
            "input_id": "fixture", "kind": "COVERAGE", "path": "evidence.json",
            "expected_sha256": digest,
        }],
        "output_path": "generated/ledger.json",
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "WORKSTREAM_ROOT", root)

    config = load_local_configuration()

    assert config.exclusion_events_dir == local / "exclusion_events"


def test_discovery_hashes_files_before_parsing_and_uses_normalized_path_order(tmp_path):
    events = tmp_path / "local" / "exclusion_events"
    _write_json(events / "z.json", _event())
    _write_json(events / "nested" / "a.json", _event())
    expected_hashes = {
        "nested/a.json": hashlib.sha256((events / "nested" / "a.json").read_bytes()).hexdigest().upper(),
        "z.json": hashlib.sha256((events / "z.json").read_bytes()).hexdigest().upper(),
    }
    discovered = discover_exclusion_events(events)

    assert [item.relative_path for item in discovered] == ["nested/a.json", "z.json"]
    assert {item.relative_path: item.sha256 for item in discovered} == expected_hashes


def test_discovery_parses_the_same_immutable_bytes_that_it_hashes(tmp_path, monkeypatch):
    events = tmp_path / "local" / "exclusion_events"
    _write_json(events / "event.json", _event())

    def forbidden_second_read(*args, **kwargs):
        raise AssertionError("event discovery must not read text after hashing bytes")

    monkeypatch.setattr(Path, "read_text", forbidden_second_read)

    discovered = discover_exclusion_events(events)

    assert discovered[0].event["event_id"] == _event()["event_id"]


def test_invalid_event_is_not_attached_or_allowed_to_change_blocking_state():
    invalid = _event()
    invalid["reason_proof"] = {}
    invalid["event_id"] = exclusion_event_id(invalid)

    attached = _attach_terminal_exclusions(
        (_record(),), (_discovered(invalid),), {"evidence/source-audit.json": "D" * 64},
    )

    assert attached[0].terminal_exclusion == _terminal_exclusions()
    assert attached[0].release_blocking is True
    assert attached[0].disposition == "DEFERRED_WITH_CAUSE"


def test_one_of_four_valid_events_attaches_only_that_mode_and_record_stays_blocking():
    event = _event()
    discovered = _discovered(event)

    attached = _attach_terminal_exclusions(
        (_record(),), (discovered,), {"evidence/source-audit.json": "D" * 64},
    )

    record = attached[0]
    assert record.release_blocking is True
    assert record.disposition == "DEFERRED_WITH_CAUSE"
    assert record.blocker_codes == ("SOURCE_ROUTE_UNRESOLVED",)
    assert record.mode_scope["sbbf"] == {
        "advertised": False,
        "terminal_state": "OUT_OF_SCOPE_WITH_PROOF",
    }
    assert all(
        record.mode_scope[mode] == {
            "advertised": True,
            "terminal_state": "NONTERMINAL",
        }
        for mode in ("vanilla", "bcb", "external")
    )
    assert record.terminal_exclusion["sbbf"]["event"] == event
    assert record.terminal_exclusion["sbbf"]["event_file"]["relative_path"] == "history/synthetic.json"
    assert record.terminal_exclusion["sbbf"]["event_file"]["sha256"] == discovered.sha256
    assert record.mode_routes["sbbf"] == {
        "behavior": "OUT_OF_SCOPE_WITH_PROOF",
        "target_vrs": [],
        "target_paths": [],
        "payload_hashes": [],
        "provider_id": "NO_PROVIDER_FOR_EXCLUDED_MODE",
        "provenance": "NO_PROVENANCE_FOR_EXCLUDED_MODE",
        "static_status": "NOT_APPLICABLE_OUT_OF_SCOPE",
        "gameplay_status": "NOT_APPLICABLE_OUT_OF_SCOPE",
        "save_reload_status": "NOT_APPLICABLE_OUT_OF_SCOPE",
    }
    manifest = _manifest_payload(
        [], discovered_events=(discovered,),
        independent_provider_claims={}, independent_package_claims={},
    )
    assert manifest["exclusion_event_files"] == [{
        "relative_path": "history/synthetic.json", "sha256": discovered.sha256,
    }]
    assert manifest["terminal_exclusion_validation_trace"][
        "verified_zero_claim_modes"
    ] == [f"{RECORD_ID}:sbbf"]


@pytest.mark.parametrize(
    ("mutation", "expected_state"),
    [
        (
            lambda record: record.mode_routes["sbbf"].update(
                {"provider_id": "CLAIMED_PROVIDER"}
            ),
            "provider-claim",
        ),
        (
            lambda record: replace(
                record, shipped_package_id="PACKAGE_SHA256:" + "7" * 64
            ),
            "package-claim",
        ),
    ],
)
def test_attachment_refuses_an_excluded_mode_with_any_provider_or_package_claim(
    mutation, expected_state,
):
    record = _record()
    mutated = mutation(record)
    if mutated is not None:
        record = mutated
    claims = {(RECORD_ID, "sbbf"): (expected_state,)}

    attached = _attach_terminal_exclusions(
        (record,), (_discovered(_event()),),
        {"evidence/source-audit.json": "D" * 64},
        independent_provider_claims=(
            claims if expected_state == "provider-claim" else {}
        ),
        independent_package_claims=(
            claims if expected_state == "package-claim" else {}
        ),
    )

    assert attached[0].terminal_exclusion == _terminal_exclusions(), expected_state
    assert attached[0].release_blocking is True


@pytest.mark.parametrize(
    "claim_kind", ["provider", "package"],
)
def test_attachment_requires_independent_zero_claim_registries(claim_kind):
    claims = {(RECORD_ID, "sbbf"): ("CLAIM",)}
    kwargs = {
        "independent_provider_claims": (
            claims if claim_kind == "provider" else {}
        ),
        "independent_package_claims": (
            claims if claim_kind == "package" else {}
        ),
    }

    attached = _attach_terminal_exclusions(
        (_record(),), (_discovered(_event()),),
        {"evidence/source-audit.json": "D" * 64}, **kwargs,
    )

    assert attached[0].terminal_exclusion == _terminal_exclusions()
    assert attached[0].release_blocking is True


def test_all_four_modes_must_be_independently_terminal_before_record_closes():
    events = tuple(
        _discovered(_event(mode), path=f"{mode}.json") for mode in RELEASE_MODES
    )

    attached = _attach_terminal_exclusions(
        (_record(),), events, {"evidence/source-audit.json": "D" * 64},
        independent_provider_claims={}, independent_package_claims={},
    )

    record = attached[0]
    assert record.release_blocking is False
    assert record.disposition == "OUT_OF_SCOPE_WITH_PROOF"
    assert record.blocker_codes == ()
    assert all(
        record.mode_scope[mode]["terminal_state"] == "OUT_OF_SCOPE_WITH_PROOF"
        and record.terminal_exclusion[mode]["event"]["mode"] == mode
        for mode in RELEASE_MODES
    )


def test_production_lifecycle_reconciles_attaches_each_mode_and_only_fourth_closes():
    """Breaks if pre-attachment validation demands the attached route shape."""
    reconciliation = reconcile_observations([_production_observation()])
    original = reconciliation.records[0]
    events = _production_events(original)
    evidence = {"evidence/source-audit.json": "D" * 64}

    assert all(
        original.mode_routes[mode]["target_vrs"] == ["UNKNOWN_TARGET_VR"]
        and original.mode_scope[mode] == {
            "advertised": True,
            "terminal_state": "NONTERMINAL",
        }
        for mode in RELEASE_MODES
    )

    for event_count in range(1, len(RELEASE_MODES) + 1):
        history = events[:event_count]
        attached = _attach_terminal_exclusions(
            reconciliation.records,
            history,
            evidence,
            independent_provider_claims={},
            independent_package_claims={},
        )
        record = attached[0]
        audit = build_completeness_audit(
            replace(reconciliation, records=attached),
            InventorySets(source_observations=frozenset({
                "production-lifecycle-observation"
            })),
            exclusion_events=tuple(item.event for item in history),
            verified_evidence=evidence,
            discovered_event_files={
                item.relative_path: item.sha256 for item in history
            },
            independent_provider_claims={},
            independent_package_claims={},
        )

        selected_modes = RELEASE_MODES[:event_count]
        assert all(
            record.mode_routes[mode] == _zero_claim_route()
            and record.mode_scope[mode] == {
                "advertised": False,
                "terminal_state": "OUT_OF_SCOPE_WITH_PROOF",
            }
            for mode in selected_modes
        )
        assert audit["exclusion_validation_failures"] == []
        assert audit["excluded_modes_with_proof"] == sorted(
            f"{record.record_id}:{mode}" for mode in selected_modes
        )
        if event_count < len(RELEASE_MODES):
            assert record.disposition == "DEFERRED_WITH_CAUSE"
            assert record.release_blocking is True
            assert audit["excluded_with_proof"] == []
            assert audit["in_scope_nonterminal"] == [record.record_id]
        else:
            assert record.disposition == "OUT_OF_SCOPE_WITH_PROOF"
            assert record.release_blocking is False
            assert audit["excluded_with_proof"] == [record.record_id]
            assert audit["in_scope_nonterminal"] == []


def test_source_mode_event_does_not_attach_to_a_four_mode_record():
    event = _event("source")

    attached = _attach_terminal_exclusions(
        (_record(),), (_discovered(event),),
        {"evidence/source-audit.json": "D" * 64},
    )

    assert attached[0].terminal_exclusion == _terminal_exclusions()
    assert attached[0].release_blocking is True


def test_malformed_mode_sibling_preflights_the_whole_claimed_record_history():
    valid = _event()
    malformed = deepcopy(valid)
    malformed["mode"] = None

    attached = _attach_terminal_exclusions(
        (_record(),), (_discovered(valid), _discovered(malformed, path="history/malformed.json")), {"evidence/source-audit.json": "D" * 64},
    )

    assert attached[0].terminal_exclusion == _terminal_exclusions()
    assert attached[0].release_blocking is True


def test_valid_exclusion_with_unresolved_markers_attaches_and_validates_end_to_end():
    full_record = _full_record()
    event = _event_for_record(full_record)
    discovered = _discovered(event)
    attached = _attach_terminal_exclusions(
        (full_record,), (discovered,),
        {"evidence/source-audit.json": "D" * 64},
    )

    document = {
        "schema_version": 1,
        "summary": {"record_count": 1},
        "blockers": [],
        "records": [attached[0].to_dict()],
    }

    assert attached[0].blocker_codes == ["SYNTHETIC_BLOCKER"]
    assert "RECORD[0]:MISSING_TERMINAL_EXCLUSION_VALIDATION_CONTEXT" in validate_generated_ledger(document)
    assert validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
        independent_provider_claims={},
        independent_package_claims={},
    ) == []


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        pytest.param(
            "mode-map",
            "RECORD[0]:TERMINAL_EXCLUSION_SCHEMA:terminal_exclusion:UNEXPECTED:unexpected",
            id="terminal-exclusion-mode-map",
        ),
        pytest.param(
            "summary",
            "RECORD[0]:TERMINAL_EXCLUSION_SCHEMA:terminal_exclusion.sbbf:UNEXPECTED:unexpected",
            id="terminal-exclusion-summary",
        ),
        pytest.param(
            "event_file",
            "RECORD[0]:TERMINAL_EXCLUSION_SCHEMA:terminal_exclusion.sbbf.event_file:UNEXPECTED:unexpected",
            id="event-file-provenance",
        ),
    ],
)
def test_generated_validation_rejects_unexpected_enclosing_exclusion_keys(
    target, expected,
):
    full_record = _full_record()
    event = _event_for_record(full_record)
    discovered = _discovered(event)
    attached = _attach_terminal_exclusions(
        (full_record,), (discovered,), {"evidence/source-audit.json": "D" * 64},
    )
    document = {
        "schema_version": 1,
        "summary": {"record_count": 1},
        "blockers": [],
        "records": [attached[0].to_dict()],
    }
    terminal_map = document["records"][0]["terminal_exclusion"]
    terminal_exclusion = terminal_map["sbbf"]
    if target == "mode-map":
        terminal_map["unexpected"] = "forbidden"
    elif target == "summary":
        terminal_exclusion["unexpected"] = "forbidden"
    else:
        terminal_exclusion["event_file"]["unexpected"] = "forbidden"

    errors = validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
        independent_provider_claims={},
        independent_package_claims={},
    )

    assert expected in errors


def test_coordinated_event_or_file_provenance_forgery_fails_against_independent_context():
    full_record = _full_record()
    event = _event_for_record(full_record)
    discovered = _discovered(event)
    attached = _attach_terminal_exclusions(
        (full_record,), (discovered,), {"evidence/source-audit.json": "D" * 64},
    )
    document = {"schema_version": 1, "summary": {"record_count": 1}, "blockers": [], "records": [attached[0].to_dict()]}
    context = {
        "verified_evidence": {"evidence/source-audit.json": "D" * 64},
        "discovered_event_files": {discovered.relative_path: discovered.sha256},
        "independent_provider_claims": {},
        "independent_package_claims": {},
    }
    event_forgery = deepcopy(document)
    forged_event = event_forgery["records"][0]["terminal_exclusion"]["sbbf"]["event"]
    forged_event["evidence"][0]["sha256"] = "E" * 64
    forged_event["reason_proof"]["complete_source_inventory"]["evidence_sha256"] = "E" * 64
    forged_event["reason_proof"]["zero_route_result"]["evidence_sha256"] = "E" * 64
    forged_event["reason_proof"]["anti_omission"]["evidence_sha256"] = "E" * 64
    forged_event["event_id"] = exclusion_event_id(forged_event)
    event_forgery["records"][0]["terminal_exclusion"]["sbbf"]["event_file"]["canonical_event_sha256"] = sha256_text(canonical_json(forged_event))
    file_forgery = deepcopy(document)
    file_forgery["records"][0]["terminal_exclusion"]["sbbf"]["event_file"]["sha256"] = "E" * 64

    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION") for error in validate_generated_ledger(event_forgery, **context))
    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION") for error in validate_generated_ledger(file_forgery, **context))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record["mode_routes"]["sbbf"].update(
            {"target_paths": ["Public/Synthetic/Forged.GR2"]}
        ),
        lambda record: record.update(
            {"shipped_package_id": "PACKAGE_SHA256:" + "7" * 64}
        ),
    ],
)
def test_generated_validation_rechecks_zero_claims_for_each_attached_mode(mutate):
    full_record = _full_record()
    event = _event_for_record(full_record)
    discovered = _discovered(event)
    attached = _attach_terminal_exclusions(
        (full_record,), (discovered,), {"evidence/source-audit.json": "D" * 64},
    )
    record = attached[0].to_dict()
    mutate(record)
    document = {
        "schema_version": 1, "summary": {"record_count": 1},
        "blockers": [], "records": [record],
    }

    errors = validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
        independent_provider_claims={},
        independent_package_claims={},
    )

    assert any(
        "TERMINAL_EXCLUSION_EVENT_INVALID:EXCLUDED_MODE_" in error
        for error in errors
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda event: event.update({"unexpected": "forbidden"}),
        lambda event: event.pop("reason_proof"),
        lambda event: event["evidence"][0].update({"unexpected": "forbidden"}),
        lambda event: event["protected_impact"].update({"registry_ids": [1]}),
        lambda event: event["reason_proof"].update({"unexpected": "forbidden"}),
        lambda event: event.update({"attempted_architectures": [{"anything": "goes"}]}),
        lambda event: event.update({"fixed_acceptance_gates": {"anything": "goes"}}),
    ],
)
def test_terminal_schema_contract_rejects_unconstrained_nested_values(mutate):
    full_record = _full_record()
    event = _event_for_record(full_record)
    discovered = _discovered(event)
    attached = _attach_terminal_exclusions(
        (full_record,), (discovered,), {"evidence/source-audit.json": "D" * 64},
    )
    document = {"schema_version": 1, "summary": {"record_count": 1}, "blockers": [], "records": [attached[0].to_dict()]}
    terminal_event = document["records"][0]["terminal_exclusion"]["sbbf"]["event"]
    mutate(terminal_event)
    terminal_event["event_id"] = exclusion_event_id(terminal_event)
    document["records"][0]["terminal_exclusion"]["sbbf"]["event_file"]["canonical_event_sha256"] = sha256_text(canonical_json(terminal_event))

    errors = validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
        independent_provider_claims={},
        independent_package_claims={},
    )

    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION_SCHEMA:") for error in errors)


@pytest.mark.parametrize(
    "reason",
    [
        "SOURCE_ABSENT_EXACT_PROFILE",
        "NO_RELEASE_PERMISSION",
        "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE",
        "PROTECTED_NATIVE_ONLY",
        "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT",
        "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE",
        "NO_SAFE_GEOMETRY_AVAILABLE",
    ],
)
def test_structural_contract_accepts_the_complete_schema_shape_for_every_reason(reason):
    assert _terminal_schema_contract_errors(_structural_event(reason)) == []


def test_structural_contract_accepts_the_hard_contract_geometry_shape():
    assert _terminal_schema_contract_errors(
        _structural_event("NO_SAFE_GEOMETRY_AVAILABLE", hard_contract=True)
    ) == []


@pytest.mark.parametrize(
    ("reason", "mutate", "expected_path"),
    [
        pytest.param(
            "SOURCE_ABSENT_EXACT_PROFILE",
            lambda event: _set(event["reason_proof"]["exact_profile"], "version", 1),
            "reason_proof.exact_profile.version",
            id="source-profile-field-type",
        ),
        pytest.param(
            "NO_RELEASE_PERMISSION",
            lambda event: _add_extra(event["reason_proof"]["permission_text"]),
            "reason_proof.permission_text:UNEXPECTED:unexpected",
            id="permission-text-closed",
        ),
        pytest.param(
            "NO_RELEASE_PERMISSION",
            lambda event: _set(event["reason_proof"]["permission_text"], "path", 7),
            "reason_proof.permission_text.path",
            id="permission-text-field-type",
        ),
        pytest.param(
            "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE",
            lambda event: event["reason_proof"]["exact_body_tuple"].append(7),
            "reason_proof.exact_body_tuple[3]",
            id="unsupported-tuple-member-type",
        ),
        pytest.param(
            "PROTECTED_NATIVE_ONLY",
            lambda event: _set(event["reason_proof"], "protected_sha256", 7),
            "reason_proof.protected_sha256",
            id="protected-native-hash-type",
        ),
        pytest.param(
            "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT",
            lambda event: _set(
                event["reason_proof"]["searched_contracts"]["root_templates"],
                "result",
                7,
            ),
            "reason_proof.searched_contracts.root_templates.result",
            id="source-search-record-field-type",
        ),
        pytest.param(
            "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT",
            lambda event: _set(event["reason_proof"], "anti_omission_pass", 1),
            "reason_proof.anti_omission_pass",
            id="source-search-boolean-type",
        ),
        pytest.param(
            "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE",
            lambda event: _add_extra(event["reason_proof"]["alternate_artifact"]),
            "reason_proof.alternate_artifact:UNEXPECTED:unexpected",
            id="alternate-artifact-closed",
        ),
        pytest.param(
            "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE",
            lambda event: _set(event["reason_proof"]["alternate_artifact"], "sha256", 7),
            "reason_proof.alternate_artifact.sha256",
            id="alternate-artifact-field-type",
        ),
    ],
)
def test_reason_specific_structural_contract_rejects_nested_extra_or_wrong_type(
    reason, mutate, expected_path,
):
    event = _structural_event(reason)
    mutate(event)

    assert any(
        expected_path in error for error in _terminal_schema_contract_errors(event)
    )


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        pytest.param(
            lambda event: _add_extra(event["reason_proof"]["architecture_results"][0]),
            "reason_proof.architecture_results[0]:UNEXPECTED:unexpected",
            id="architecture-closed",
        ),
        pytest.param(
            lambda event: _set(
                event["reason_proof"]["architecture_results"][0],
                "candidate_count",
                True,
            ),
            "reason_proof.architecture_results[0].candidate_count",
            id="architecture-candidate-count-type",
        ),
        pytest.param(
            lambda event: _add_extra(
                event["reason_proof"]["architecture_results"][0]["components"][0]
            ),
            "reason_proof.architecture_results[0].components[0]:UNEXPECTED:unexpected",
            id="component-closed",
        ),
        pytest.param(
            lambda event: _set(
                event["reason_proof"]["architecture_results"][0]["components"][0],
                "evidence_path",
                7,
            ),
            "reason_proof.architecture_results[0].components[0].evidence_path",
            id="component-field-type",
        ),
        pytest.param(
            lambda event: _set(
                event["reason_proof"]["fixed_gates"]["topology"], "result", 7
            ),
            "reason_proof.fixed_gates.topology.result",
            id="fixed-gate-field-type",
        ),
        pytest.param(
            lambda event: _add_extra(
                event["reason_proof"]["final_available_safe_tooling_failure"]
            ),
            "reason_proof.final_available_safe_tooling_failure:UNEXPECTED:unexpected",
            id="final-tooling-link-closed",
        ),
        pytest.param(
            lambda event: _set(
                event["reason_proof"]["final_available_safe_tooling_failure"],
                "evidence_sha256",
                7,
            ),
            "reason_proof.final_available_safe_tooling_failure.evidence_sha256",
            id="final-tooling-link-field-type",
        ),
        pytest.param(
            lambda event: _add_extra(event["attempted_architectures"][0]),
            "event.attempted_architectures[0]:UNEXPECTED:unexpected",
            id="top-level-architecture-closed",
        ),
        pytest.param(
            lambda event: _set(
                event["fixed_acceptance_gates"]["topology"], "evidence_path", 7
            ),
            "event.fixed_acceptance_gates.topology.evidence_path",
            id="top-level-fixed-gate-field-type",
        ),
    ],
)
def test_bounded_geometry_structural_contract_recurses_through_every_summary(
    mutate, expected_path,
):
    event = _structural_event("NO_SAFE_GEOMETRY_AVAILABLE")
    event["attempted_architectures"] = deepcopy(event["attempted_architectures"])
    event["fixed_acceptance_gates"] = deepcopy(event["fixed_acceptance_gates"])
    mutate(event)

    assert any(
        expected_path in error for error in _terminal_schema_contract_errors(event)
    )


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        pytest.param(
            lambda event: _add_extra(event["reason_proof"]["hard_contract_impossibility"]),
            "reason_proof.hard_contract_impossibility:UNEXPECTED:unexpected",
            id="hard-contract-closed",
        ),
        pytest.param(
            lambda event: _set(
                event["reason_proof"]["hard_contract_impossibility"],
                "protected_object_sha256",
                7,
            ),
            "reason_proof.hard_contract_impossibility.protected_object_sha256",
            id="hard-contract-field-type",
        ),
        pytest.param(
            lambda event: _add_extra(
                event["reason_proof"]["hard_contract_impossibility"]["boundary_contract"]
            ),
            "reason_proof.hard_contract_impossibility.boundary_contract:UNEXPECTED:unexpected",
            id="boundary-contract-closed",
        ),
        pytest.param(
            lambda event: _set(
                event["reason_proof"]["hard_contract_impossibility"]["boundary_contract"],
                "record_value",
                7,
            ),
            "reason_proof.hard_contract_impossibility.boundary_contract.record_value",
            id="boundary-contract-field-type",
        ),
    ],
)
def test_hard_contract_geometry_structural_contract_closes_the_boundary(
    mutate, expected_path,
):
    event = _structural_event("NO_SAFE_GEOMETRY_AVAILABLE", hard_contract=True)
    mutate(event)

    assert any(
        expected_path in error for error in _terminal_schema_contract_errors(event)
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("event", "reason"), "NOT_A_REASON"),
        (("event", "mode"), "not-a-mode"),
        (("event", "source_profile_id"), "FORGED_PROFILE"),
        (("event", "created_utc"), "not-a-timestamp"),
        (("event_file", "canonical_event_sha256"), "E" * 64),
        (("event", "evidence", 0, "sha256"), "E" * 64),
    ],
)
def test_forged_attached_event_data_fails_generated_validation(path, value):
    full_record = _full_record()
    event = _event_for_record(full_record)
    discovered = _discovered(event)
    attached = _attach_terminal_exclusions(
        (full_record,), (discovered,),
        {"evidence/source-audit.json": "D" * 64},
    )
    record = attached[0].to_dict()
    cursor = record["terminal_exclusion"]["sbbf"]
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    document = {"schema_version": 1, "summary": {"record_count": 1}, "blockers": [], "records": [record]}

    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION") for error in validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
        independent_provider_claims={},
        independent_package_claims={},
    ))
