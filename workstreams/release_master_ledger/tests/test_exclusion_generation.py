import hashlib
import json
from pathlib import Path
from copy import deepcopy

import pytest

from workstreams.release_master_ledger.configuration import (
    ConfigurationError,
    EvidenceInput,
    LocalConfiguration,
    load_local_configuration,
)
from workstreams.release_master_ledger.exclusions import exclusion_event_id
from workstreams.release_master_ledger.identity import canonical_json, sha256_text
from workstreams.release_master_ledger.generate import (
    _attach_terminal_exclusions,
    _manifest_payload,
    DiscoveredExclusionEvent,
    discover_exclusion_events,
)
from workstreams.release_master_ledger.models import LedgerRecord
from workstreams.release_master_ledger.validation import validate_generated_ledger
from workstreams.release_master_ledger.tests.test_validation import complete_record_fixture


RECORD_ID = "LEDGER_" + "A" * 64
IDENTITY_SHA256 = "B" * 64
PROFILE_SHA256 = "C" * 64


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
        source_route={}, mode_routes={}, protected_relations={}, transformation={}, gates={},
        evidence_paths=(), evidence_hashes=(), disposition="DEFERRED_WITH_CAUSE",
        blocker_codes=("SOURCE_ROUTE_UNRESOLVED",), release_blocking=True,
        next_admissible_action="Recover source.",
        acceptance_event_id="UNKNOWN_ACCEPTANCE_EVENT",
        shipped_package_id="UNKNOWN_SHIPPED_PACKAGE",
    )


def _event() -> dict[str, object]:
    event: dict[str, object] = {
        "schema": "clothmorph.terminal-exclusion", "schema_version": 1,
        "record_id": RECORD_ID, "identity_sha256": IDENTITY_SHA256,
        "source_profile_id": "SYNTHETIC_PROFILE", "mode": "sbbf",
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
        "protected_impact": {"registry_ids": [], "shared_consumers": [], "forbidden_targets": [], "result": "NO_PROTECTED_MUTATION"},
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
    data["terminal_exclusion"] = None
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
    event["event_id"] = exclusion_event_id(event)
    return event


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

    assert attached[0].terminal_exclusion is None
    assert attached[0].release_blocking is True
    assert attached[0].disposition == "DEFERRED_WITH_CAUSE"


def test_selected_valid_event_attaches_a_summary_and_makes_only_that_route_nonblocking():
    event = _event()
    discovered = _discovered(event)

    attached = _attach_terminal_exclusions(
        (_record(),), (discovered,), {"evidence/source-audit.json": "D" * 64},
    )

    record = attached[0]
    assert record.release_blocking is False
    assert record.disposition == "OUT_OF_SCOPE_WITH_PROOF"
    assert record.blocker_codes == ()
    assert record.terminal_exclusion["event"] == event
    assert record.terminal_exclusion["event_file"]["relative_path"] == "history/synthetic.json"
    assert record.terminal_exclusion["event_file"]["sha256"] == discovered.sha256
    assert _manifest_payload([], discovered_events=(discovered,))["exclusion_event_files"] == [{
        "relative_path": "history/synthetic.json", "sha256": discovered.sha256,
    }]


def test_malformed_mode_sibling_preflights_the_whole_claimed_record_history():
    valid = _event()
    malformed = deepcopy(valid)
    malformed["mode"] = None

    attached = _attach_terminal_exclusions(
        (_record(),), (_discovered(valid), _discovered(malformed, path="history/malformed.json")), {"evidence/source-audit.json": "D" * 64},
    )

    assert attached[0].terminal_exclusion is None
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

    assert attached[0].blocker_codes == ()
    assert "RECORD[0]:MISSING_TERMINAL_EXCLUSION_VALIDATION_CONTEXT" in validate_generated_ledger(document)
    assert validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
    ) == []


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
    }
    event_forgery = deepcopy(document)
    forged_event = event_forgery["records"][0]["terminal_exclusion"]["event"]
    forged_event["evidence"][0]["sha256"] = "E" * 64
    forged_event["reason_proof"]["complete_source_inventory"]["evidence_sha256"] = "E" * 64
    forged_event["reason_proof"]["zero_route_result"]["evidence_sha256"] = "E" * 64
    forged_event["reason_proof"]["anti_omission"]["evidence_sha256"] = "E" * 64
    forged_event["event_id"] = exclusion_event_id(forged_event)
    event_forgery["records"][0]["terminal_exclusion"]["event_file"]["canonical_event_sha256"] = sha256_text(canonical_json(forged_event))
    file_forgery = deepcopy(document)
    file_forgery["records"][0]["terminal_exclusion"]["event_file"]["sha256"] = "E" * 64

    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION") for error in validate_generated_ledger(event_forgery, **context))
    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION") for error in validate_generated_ledger(file_forgery, **context))


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
    cursor = record["terminal_exclusion"]
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    document = {"schema_version": 1, "summary": {"record_count": 1}, "blockers": [], "records": [record]}

    assert any(error.startswith("RECORD[0]:TERMINAL_EXCLUSION") for error in validate_generated_ledger(
        document,
        verified_evidence={"evidence/source-audit.json": "D" * 64},
        discovered_event_files={discovered.relative_path: discovered.sha256},
    ))
