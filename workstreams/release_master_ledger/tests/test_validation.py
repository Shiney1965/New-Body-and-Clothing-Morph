import json
from pathlib import Path

from workstreams.release_master_ledger.validation import validate_record


ROOT = Path(__file__).resolve().parents[1]


def complete_record_fixture():
    return {
        "identity": "D" * 64,
        "identity_fields": {
            "source_module_uuid": "11111111-1111-1111-1111-111111111111",
            "source_profile_digest": "A" * 64,
            "creation_path_kind": "root_template",
            "root_template_uuid": "22222222-2222-2222-2222-222222222222",
            "stats_entry": "ARM_Test",
            "inheritance_digest": "B" * 64,
            "effective_slot": "Underwear",
            "body_tuple": ["Human", "Female", "BT1", "Regular", "HUM_F"],
            "ordered_source_vrs": ["33333333-3333-3333-3333-333333333333"],
            "component_contract_digest": "C" * 64,
        },
        "source_module": {
            "uuid": "11111111-1111-1111-1111-111111111111",
            "profile_digest": "A" * 64,
        },
        "creation_path": {
            "kind": "root_template",
            "root_template_uuid": "22222222-2222-2222-2222-222222222222",
            "stats_entry": "ARM_Test",
            "inheritance_digest": "B" * 64,
        },
        "classification": {
            "effective_slot": "Underwear",
            "body_tuple": ["Human", "Female", "BT1", "Regular", "HUM_F"],
        },
        "source_visual_resources": [],
        "component_contract": {"digest": "C" * 64},
        "mode_routes": {
            "vanilla": {},
            "sbbf": {},
            "bcb": {},
            "external": {},
        },
        "disposition": "DEFERRED WITH CAUSE",
        "next_action": "Obtain a bounded synthetic result.",
        "evidence_files": ["fixture.json"],
    }


def test_complete_synthetic_record_is_valid():
    assert validate_record(complete_record_fixture()) == []


def test_binding_blank_is_rejected():
    record = complete_record_fixture()
    record["source_module"]["uuid"] = ""

    assert "BLANK:source_module.uuid" in validate_record(record)


def test_lowercase_and_short_hashes_are_rejected():
    record = complete_record_fixture()
    record["source_module"]["profile_digest"] = "a" * 64
    record["component_contract"]["digest"] = "C" * 63

    errors = validate_record(record)

    assert "INVALID_SHA256:source_module.profile_digest" in errors
    assert "INVALID_SHA256:component_contract.digest" in errors


def test_emitted_record_requires_all_four_mode_routes():
    record = complete_record_fixture()
    del record["mode_routes"]["external"]

    assert "MISSING:mode_routes.external" in validate_record(record)


def test_unclassified_cannot_be_emitted():
    record = complete_record_fixture()
    record["disposition"] = "UNCLASSIFIED"

    assert "FORBIDDEN_DISPOSITION:UNCLASSIFIED" in validate_record(record)


def test_schema_binds_the_same_modes_and_dispositions():
    schema = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))

    assert schema["$defs"]["ledger_record"]["properties"]["mode_routes"]["required"] == [
        "vanilla",
        "sbbf",
        "bcb",
        "external",
    ]
    assert "UNCLASSIFIED" not in schema["$defs"]["disposition"]["enum"]
