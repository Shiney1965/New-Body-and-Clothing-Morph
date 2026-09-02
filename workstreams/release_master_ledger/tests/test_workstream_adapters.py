import hashlib
import json
from pathlib import Path

from workstreams.release_master_ledger.identity import build_identity
from workstreams.release_master_ledger.models import CanonicalIdentityFields

from workstreams.release_master_ledger.adapters import (
    adapt_bcbscantily,
    adapt_coverage,
    adapt_named_target,
    adapt_package_evidence,
    adapt_true_underwear,
    adapt_vanitybody,
)
from workstreams.release_master_ledger.configuration import VerifiedInput


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def verified_fixture(name, kind):
    path = FIXTURES / name
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(
        input_id=f"fixture-{kind.lower()}", kind=kind, path=path, bytes=len(content),
        expected_sha256=digest, actual_sha256=digest,
    )


VERIFIED_COVERAGE = verified_fixture("coverage_records.json", "COVERAGE")
VERIFIED_UNDERWEAR = verified_fixture("underwear_records.json", "TRUE_UNDERWEAR")
VERIFIED_VANITY = verified_fixture("vanity_records.json", "VANITYBODY")


def underwear_fixture(**overrides):
    record = load_fixture("underwear_records.json")[0]
    record.update(overrides)
    return record


def complete_section_9_contract():
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
    canonical_identity, identity_sha256 = build_identity(fields)
    mode = {
        "behavior": "SOURCE_NATIVE", "target_vrs": [fields.ordered_source_vrs[0]],
        "target_paths": ["fixture.gr2"], "payload_hashes": ["D" * 64],
        "provider_id": "FIXTURE", "provenance": "FIXTURE", "static_status": "STATIC_UNASSESSED",
        "gameplay_status": "GAMEPLAY_UNASSESSED", "save_reload_status": "SAVE_RELOAD_UNASSESSED",
    }
    return {
        "record_id": "fixture-contract", "canonical_identity": canonical_identity,
        "identity_sha256": identity_sha256,
        "source_module": {"pak": "fixture.pak", "folder": "fixture", "name": "fixture", "uuid": fields.source_module_uuid, "version64": "1", "pak_sha256": "E" * 64, "profile_digest": fields.source_profile_digest},
        "permission": {"state": "UNASSESSED", "evidence_path": "fixture.json", "evidence_sha256": "F" * 64, "credit": "fixture", "distribution_limits": "fixture"},
        "creation_path": {"kind": fields.creation_path_kind, "root_uuid": fields.root_template_uuid, "stats_entry": fields.stats_entry, "inheritance_chain": ["ARM_Base", fields.stats_entry], "chain_digest": fields.inheritance_digest},
        "classification": {"effective_slot": fields.effective_slot, "body_content": "CLOTHING", "garment_family": "fixture", "class_id": "fixture", "class_contract_digest": "B" * 64},
        "body_tuple": {"race": "Human", "sex": "Female", "body_type": "BT1", "body_shape": "Regular", "equipment_race": "HUM_F"},
        "source_route": {"ordered_vrs": list(fields.ordered_source_vrs), "ordered_paths": ["fixture.gr2"], "ordered_file_hashes": ["D" * 64], "component_contract_digest": fields.component_contract_digest},
        "mode_routes": {name: dict(mode) for name in ("vanilla", "sbbf", "bcb", "external")},
        "mode_scope": {
            name: {"advertised": True, "terminal_state": "NONTERMINAL"}
            for name in ("vanilla", "sbbf", "bcb", "external")
        },
        "protected_relations": {"registry_ids": ["fixture"], "protected_consumers": ["fixture"], "shared_assets": ["fixture"], "forbidden_targets": ["fixture"]},
        "transformation": {"eligibility": "UNASSESSED", "strategy": "UNASSESSED", "allowed_components": ["UNKNOWN_ALLOWED_COMPONENTS"], "allowed_channels": ["UNKNOWN_ALLOWED_CHANNELS"], "exception_id": "NO_EXCEPTION"},
        "gates": {name: "UNASSESSED" for name in ("topology", "component", "material", "skin", "clearance", "package", "fresh_extract", "route", "gameplay")},
        "evidence_paths": ["fixture.json"], "evidence_hashes": ["E" * 64],
        "disposition": "DEFERRED_WITH_CAUSE", "blocker_codes": ["SYNTHETIC_BLOCKER"], "release_blocking": True,
        "next_admissible_action": "Obtain bounded evidence.", "acceptance_event_id": "UNKNOWN_ACCEPTANCE_EVENT", "shipped_package_id": "UNKNOWN_SHIPPED_PACKAGE",
        "terminal_exclusion": {
            name: None for name in ("vanilla", "sbbf", "bcb", "external")
        },
    }


def test_coverage_maps_offline_and_package_states_without_gameplay_promotion():
    observations = adapt_coverage(load_fixture("coverage_records.json"), VERIFIED_COVERAGE)

    assert observations[0].disposition == "OFFLINE_CANDIDATE_PASS"
    assert observations[0].evidence_status == "GAMEPLAY_UNASSESSED"
    assert observations[1].disposition == "PACKAGE_READY_GAMEPLAY_UNASSESSED"
    assert observations[1].release_blocking is True
    assert observations[1].evidence_status == "GAMEPLAY_UNASSESSED_PACKAGE_ONLY"


def test_coverage_preserves_explicit_resolved_protected_relations():
    relations = {
        "registry_ids": ["REGISTRY_REVIEWED"],
        "protected_consumers": ["UNACCEPTED_CONSUMER"],
        "shared_assets": ["Public/Synthetic/Shared.GR2"],
        "forbidden_targets": ["EMBEDDED_BODY_DATA"],
    }
    record = load_fixture("coverage_records.json")[0]
    record["protected_relations"] = relations

    observation = adapt_coverage([record], VERIFIED_COVERAGE)[0]

    assert observation.protected_relations == relations


def test_underwear_missing_route_remains_blocking():
    observation = adapt_true_underwear(
        [underwear_fixture(disposition="MISSING ROUTE / BUILD")], VERIFIED_UNDERWEAR
    )[0]

    assert observation.disposition == "BLOCKED_WITH_CAUSE"
    assert "TARGET_ROUTE_UNRESOLVED" in observation.blocker_codes


def test_underwear_with_validated_section_9_contract_advances_only_to_offline_ready():
    observation = adapt_true_underwear(
        [underwear_fixture(section_9_contract=complete_section_9_contract())], VERIFIED_UNDERWEAR
    )[0]

    assert observation.disposition == "READY_FOR_OFFLINE_CORRECTION"
    assert observation.evidence_status == "GAMEPLAY_UNASSESSED"
    assert observation.release_blocking is True
    assert "TARGET_ROUTE_UNRESOLVED" not in observation.blocker_codes


def test_vanity_ready_for_test_is_deferred_without_section_9_contract():
    observation = adapt_vanitybody(load_fixture("vanity_records.json")[:1], VERIFIED_VANITY)[0]

    assert observation.disposition == "DEFERRED_WITH_CAUSE"
    assert "SECTION_9_CONTRACT_UNRESOLVED" in observation.blocker_codes


def test_vanity_key_complete_but_invalid_section_9_contract_remains_deferred():
    contract = complete_section_9_contract()
    contract["permission"] = None
    observation = adapt_vanitybody(
        [{"disposition": "READY FOR TEST", "section_9_contract": contract}], VERIFIED_VANITY
    )[0]

    assert observation.disposition == "DEFERRED_WITH_CAUSE"
    assert "SECTION_9_CONTRACT_UNRESOLVED" in observation.blocker_codes


def test_bcbscantily_without_visual_resource_or_component_contract_remains_blocking():
    observation = adapt_bcbscantily(load_fixture("vanity_records.json")[1:], VERIFIED_VANITY)[0]

    assert observation.disposition == "BLOCKED_WITH_CAUSE"
    assert "SOURCE_VR_UNRESOLVED" in observation.blocker_codes
    assert "COMPONENT_CONTRACT_UNRESOLVED" in observation.blocker_codes


def test_package_evidence_never_reports_gameplay_acceptance():
    observation = adapt_package_evidence(
        [{"observation_id": "fixture-package-1", "package_status": "PACKAGE_PASS"}],
        VERIFIED_COVERAGE,
    )[0]

    assert observation.disposition == "PACKAGE_READY_GAMEPLAY_UNASSESSED"
    assert observation.evidence_status == "GAMEPLAY_UNASSESSED_PACKAGE_ONLY"
    assert observation.release_blocking is True


def test_named_target_display_name_is_not_an_identity_or_route():
    observation = adapt_named_target(
        [{"display_name": "A very convincing garment name"}], VERIFIED_COVERAGE
    )[0]

    assert observation.classification["effective_slot"] == "AMBIGUOUS_SLOT"
    assert "NAMED_TARGET_UNRESOLVED" in observation.blocker_codes
