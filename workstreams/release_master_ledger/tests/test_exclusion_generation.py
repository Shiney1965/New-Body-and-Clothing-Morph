import hashlib
import json
from pathlib import Path

import pytest

from workstreams.release_master_ledger.configuration import (
    ConfigurationError,
    EvidenceInput,
    LocalConfiguration,
    load_local_configuration,
)
from workstreams.release_master_ledger.exclusions import exclusion_event_id
from workstreams.release_master_ledger.generate import (
    _attach_terminal_exclusions,
    discover_exclusion_events,
)
from workstreams.release_master_ledger.models import LedgerRecord


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


def test_discovery_hashes_files_before_parsing_and_uses_normalized_path_order(tmp_path, monkeypatch):
    events = tmp_path / "local" / "exclusion_events"
    _write_json(events / "z.json", _event())
    _write_json(events / "nested" / "a.json", _event())
    expected_hashes = {
        "nested/a.json": hashlib.sha256((events / "nested" / "a.json").read_bytes()).hexdigest().upper(),
        "z.json": hashlib.sha256((events / "z.json").read_bytes()).hexdigest().upper(),
    }
    hashed: list[Path] = []

    from workstreams.release_master_ledger import generate as generation
    original_hash = generation._hash_event_file

    def observing_hash(path: Path) -> str:
        hashed.append(path)
        return original_hash(path)

    monkeypatch.setattr(generation, "_hash_event_file", observing_hash)

    discovered = discover_exclusion_events(events)

    assert [item.relative_path for item in discovered] == ["nested/a.json", "z.json"]
    assert {item.relative_path: item.sha256 for item in discovered} == expected_hashes
    assert hashed == [events / "nested" / "a.json", events / "z.json"]


def test_invalid_event_is_not_attached_or_allowed_to_change_blocking_state():
    invalid = _event()
    invalid["reason_proof"] = {}
    invalid["event_id"] = exclusion_event_id(invalid)

    attached = _attach_terminal_exclusions(
        (_record(),), (invalid,), {"evidence/source-audit.json": "D" * 64},
    )

    assert attached[0].terminal_exclusion is None
    assert attached[0].release_blocking is True
    assert attached[0].disposition == "DEFERRED_WITH_CAUSE"


def test_selected_valid_event_attaches_a_summary_and_makes_only_that_route_nonblocking():
    event = _event()

    attached = _attach_terminal_exclusions(
        (_record(),), (event,), {"evidence/source-audit.json": "D" * 64},
    )

    record = attached[0]
    assert record.release_blocking is False
    assert record.disposition == "OUT_OF_SCOPE_WITH_PROOF"
    assert record.blocker_codes == ()
    assert record.terminal_exclusion == {
        "event_id": event["event_id"], "record_id": RECORD_ID,
        "identity_sha256": IDENTITY_SHA256, "source_profile_id": "SYNTHETIC_PROFILE",
        "mode": "sbbf", "reason": "SOURCE_ABSENT_EXACT_PROFILE",
        "scope_statement": "Exclude only the synthetic SBBF route.",
        "evidence": event["evidence"],
        "protected_impact": {"result": "NO_PROTECTED_MUTATION"},
        "next_project_if_reopened": "Recover the exact source profile.",
        "approved_by": "Alan",
        "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
        "created_utc": "2026-09-01T12:00:00Z",
    }
