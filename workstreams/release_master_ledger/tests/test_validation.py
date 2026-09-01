import json
from pathlib import Path

from workstreams.release_master_ledger.identity import build_identity
from workstreams.release_master_ledger.models import CanonicalIdentityFields
from workstreams.release_master_ledger.validation import validate_record


ROOT = Path(__file__).resolve().parents[1]
DISPOSITIONS = [
    "ACCEPTED_PROTECTED",
    "SOURCE_NATIVE_PROTECTED",
    "PACKAGE_ONLY_PROTECTED",
    "READY_FOR_OFFLINE_CORRECTION",
    "OFFLINE_CANDIDATE_PASS",
    "PACKAGE_READY_GAMEPLAY_UNASSESSED",
    "CLASS_GAMEPLAY_ACCEPTED",
    "ITEM_GAMEPLAY_ACCEPTED",
    "SHIPPED_NATIVE_PASSTHROUGH",
    "SHIPPED_REFIT",
    "OUT_OF_SCOPE_WITH_PROOF",
    "BLOCKED_WITH_CAUSE",
    "DEFERRED_WITH_CAUSE",
]
MODE_FIELDS = [
    "behavior",
    "target_vrs",
    "target_paths",
    "payload_hashes",
    "provider_id",
    "provenance",
    "static_status",
    "gameplay_status",
    "save_reload_status",
]


def identity_fixture():
    return CanonicalIdentityFields(
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


def mode_fixture():
    return {
        "behavior": "SOURCE_NATIVE",
        "target_vrs": ["33333333-3333-3333-3333-333333333333"],
        "target_paths": ["Public/Test/Assets/Test.GR2"],
        "payload_hashes": ["D" * 64],
        "provider_id": "TEST_PROVIDER",
        "provenance": "SYNTHETIC_FIXTURE",
        "static_status": "STATIC_UNASSESSED",
        "gameplay_status": "GAMEPLAY_UNASSESSED",
        "save_reload_status": "SAVE_RELOAD_UNASSESSED",
    }


def complete_record_fixture():
    fields = identity_fixture()
    canonical_identity, identity_sha256 = build_identity(fields)
    return {
        "record_id": "SYNTHETIC_RECORD_001",
        "canonical_identity": canonical_identity,
        "identity_sha256": identity_sha256,
        "source_module": {
            "pak": "Synthetic.pak",
            "folder": "Synthetic",
            "name": "Synthetic Module",
            "uuid": fields.source_module_uuid,
            "version64": "1",
            "pak_sha256": "E" * 64,
            "profile_digest": fields.source_profile_digest,
        },
        "permission": {
            "state": "PERMISSION_UNASSESSED",
            "evidence_path": "permission.json",
            "evidence_sha256": "F" * 64,
            "credit": "SYNTHETIC_CREDIT",
            "distribution_limits": "SYNTHETIC_LIMITS",
        },
        "creation_path": {
            "kind": fields.creation_path_kind,
            "root_uuid": fields.root_template_uuid,
            "stats_entry": fields.stats_entry,
            "inheritance_chain": ["ARM_Base", fields.stats_entry],
            "chain_digest": fields.inheritance_digest,
        },
        "classification": {
            "effective_slot": fields.effective_slot,
            "body_content": "CLOTHING",
            "garment_family": "SYNTHETIC_GARMENT",
            "class_id": "SYNTHETIC_CLASS",
            "class_contract_digest": "B" * 64,
        },
        "body_tuple": {
            "race": "Human",
            "sex": "Female",
            "body_type": "BT1",
            "body_shape": "Regular",
            "equipment_race": "HUM_F",
        },
        "source_route": {
            "ordered_vrs": list(fields.ordered_source_vrs),
            "ordered_paths": ["Public/Test/Assets/Source.GR2"],
            "ordered_file_hashes": ["D" * 64],
            "component_contract_digest": fields.component_contract_digest,
        },
        "mode_routes": {mode: mode_fixture() for mode in ("vanilla", "sbbf", "bcb", "external")},
        "protected_relations": {
            "registry_ids": ["SYNTHETIC_REGISTRY"],
            "protected_consumers": ["SYNTHETIC_CONSUMER"],
            "shared_assets": ["SYNTHETIC_ASSET"],
            "forbidden_targets": ["SYNTHETIC_FORBIDDEN_TARGET"],
        },
        "transformation": {
            "eligibility": "ELIGIBILITY_UNASSESSED",
            "strategy": "STRATEGY_UNASSESSED",
            "allowed_components": ["UNKNOWN_ALLOWED_COMPONENTS"],
            "allowed_channels": ["UNKNOWN_ALLOWED_CHANNELS"],
            "exception_id": "NO_EXCEPTION",
        },
        "gates": {
            "topology": "TOPOLOGY_UNASSESSED",
            "component": "COMPONENT_UNASSESSED",
            "material": "MATERIAL_UNASSESSED",
            "skin": "SKIN_UNASSESSED",
            "clearance": "CLEARANCE_UNASSESSED",
            "package": "PACKAGE_UNASSESSED",
            "fresh_extract": "FRESH_EXTRACT_UNASSESSED",
            "route": "ROUTE_UNASSESSED",
            "gameplay": "GAMEPLAY_UNASSESSED",
        },
        "evidence_paths": ["fixture.json"],
        "evidence_hashes": ["E" * 64],
        "disposition": "DEFERRED_WITH_CAUSE",
        "blocker_codes": ["SYNTHETIC_BLOCKER"],
        "release_blocking": True,
        "next_admissible_action": "Obtain bounded synthetic evidence.",
        "acceptance_event_id": "UNKNOWN_ACCEPTANCE_EVENT",
        "shipped_package_id": "UNKNOWN_SHIPPED_PACKAGE",
    }


def test_complete_synthetic_record_is_valid():
    assert validate_record(complete_record_fixture()) == []


def test_identity_sha256_must_match_recomputed_identity_fields():
    record = complete_record_fixture()
    record["identity_sha256"] = "D" * 64

    assert "IDENTITY_MISMATCH" in validate_record(record)


def test_body_tuple_rejects_blank_and_nonstring_members():
    record = complete_record_fixture()
    record["body_tuple"]["sex"] = ""
    record["body_tuple"]["body_type"] = 1

    errors = validate_record(record)

    assert "BLANK:body_tuple.sex" in errors
    assert "INVALID_TYPE:body_tuple.body_type" in errors


def test_ordered_source_vrs_reject_blank_and_nonstring_members():
    record = complete_record_fixture()
    record["source_route"]["ordered_vrs"] = ["", 1]

    errors = validate_record(record)

    assert "BLANK:source_route.ordered_vrs[0]" in errors
    assert "INVALID_TYPE:source_route.ordered_vrs[1]" in errors


def test_binding_blank_is_rejected():
    record = complete_record_fixture()
    record["source_module"]["uuid"] = ""

    assert "BLANK:source_module.uuid" in validate_record(record)


def test_lowercase_and_short_hashes_are_rejected():
    record = complete_record_fixture()
    record["source_module"]["profile_digest"] = "a" * 64
    record["source_route"]["component_contract_digest"] = "C" * 63

    errors = validate_record(record)

    assert "INVALID_SHA256:source_module.profile_digest" in errors
    assert "INVALID_SHA256:source_route.component_contract_digest" in errors


def test_representative_required_field_families_are_rejected_when_missing():
    record = complete_record_fixture()
    del record["permission"]
    del record["protected_relations"]
    del record["gates"]

    errors = validate_record(record)

    assert "MISSING:permission" in errors
    assert "MISSING:protected_relations" in errors
    assert "MISSING:gates" in errors


def test_required_nested_family_members_are_rejected_when_missing():
    record = complete_record_fixture()
    del record["permission"]["credit"]
    del record["protected_relations"]["shared_assets"]
    del record["transformation"]["strategy"]

    errors = validate_record(record)

    assert "MISSING:permission.credit" in errors
    assert "MISSING:protected_relations.shared_assets" in errors
    assert "MISSING:transformation.strategy" in errors


def test_emitted_record_requires_all_four_mode_routes():
    record = complete_record_fixture()
    del record["mode_routes"]["external"]

    assert "MISSING:mode_routes.external" in validate_record(record)


def test_mode_route_requires_a_complete_nonblank_object():
    record = complete_record_fixture()
    record["mode_routes"]["vanilla"] = None
    del record["mode_routes"]["sbbf"]["target_vrs"]
    record["mode_routes"]["bcb"]["target_paths"] = []

    errors = validate_record(record)

    assert "INVALID:mode_routes.vanilla" in errors
    assert "MISSING:mode_routes.sbbf.target_vrs" in errors
    assert "BLANK:mode_routes.bcb.target_paths" in errors


def test_blocker_codes_require_stable_uppercase_codes_and_cover_unknowns():
    record = complete_record_fixture()
    record["blocker_codes"] = ["not a code"]

    assert "INVALID_BLOCKER_CODE:blocker_codes[0]" in validate_record(record)

    record = complete_record_fixture()
    record["blocker_codes"] = []

    assert "BLOCKER_CODES_REQUIRED" in validate_record(record)


def test_unclassified_cannot_be_emitted():
    record = complete_record_fixture()
    record["disposition"] = "UNCLASSIFIED"

    assert "FORBIDDEN_DISPOSITION:UNCLASSIFIED" in validate_record(record)


def test_missing_disposition_is_rejected():
    record = complete_record_fixture()
    del record["disposition"]

    assert "MISSING:disposition" in validate_record(record)


def test_blank_disposition_is_rejected():
    record = complete_record_fixture()
    record["disposition"] = ""

    assert "BLANK:disposition" in validate_record(record)


def test_none_disposition_is_rejected():
    record = complete_record_fixture()
    record["disposition"] = None

    assert "BLANK:disposition" in validate_record(record)


def test_nonstring_disposition_is_rejected():
    record = complete_record_fixture()
    record["disposition"] = 1

    assert "INVALID_TYPE:disposition" in validate_record(record)


def test_nonempty_unknown_disposition_is_rejected_with_its_value():
    record = complete_record_fixture()
    record["disposition"] = "NOT_ALLOWED"

    assert "INVALID_DISPOSITION:NOT_ALLOWED" in validate_record(record)


def test_schema_binds_every_section_9_2_family_and_exact_dispositions():
    schema = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
    properties = schema["$defs"]["ledger_record"]["properties"]
    required = schema["$defs"]["ledger_record"]["required"]

    assert set(required) == {
        "record_id", "canonical_identity", "identity_sha256", "source_module", "permission",
        "creation_path", "classification", "body_tuple", "source_route", "mode_routes",
        "protected_relations", "transformation", "gates", "evidence_paths", "evidence_hashes",
        "disposition", "blocker_codes", "release_blocking", "next_admissible_action",
        "acceptance_event_id", "shipped_package_id",
    }
    assert properties["mode_routes"]["additionalProperties"]["required"] == MODE_FIELDS
    assert schema["$defs"]["disposition"]["enum"] == DISPOSITIONS
    assert "UNCLASSIFIED" not in schema["$defs"]["disposition"]["enum"]
