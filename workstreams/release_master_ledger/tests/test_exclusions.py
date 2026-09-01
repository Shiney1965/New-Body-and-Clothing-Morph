"""Fail-closed tests for terminal-exclusion event contracts."""

from copy import deepcopy
import json

import pytest

from workstreams.release_master_ledger.exclusions import (
    ExclusionSelection,
    canonical_exclusion_payload,
    exclusion_event_id,
    select_current_exclusion,
    validate_exclusion_event,
)


RECORD_ID = "LEDGER_" + "A" * 64
IDENTITY_SHA256 = "B" * 64
PROFILE_ID = "SYNTHETIC_PROFILE"
PROFILE_SHA256 = "C" * 64
SOURCE_SHA256 = "D" * 64
PERMISSION_SHA256 = "E" * 64
GEOMETRY_SHA256 = "F" * 64
TIEFLING_PAK_SHA256 = "01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141"
VERIFIED_EVIDENCE = {
    "evidence/alternate-artifact.json": SOURCE_SHA256,
    "evidence/geometry.json": GEOMETRY_SHA256,
    "evidence/permission.txt": PERMISSION_SHA256,
    "evidence/source-audit.json": SOURCE_SHA256,
    "Public/Synthetic/Protected.GR2": SOURCE_SHA256,
}


def ledger_record(**overrides):
    record = {
        "record_id": RECORD_ID,
        "identity_sha256": IDENTITY_SHA256,
        "source_module": {
            "folder": PROFILE_ID, "pak": "Synthetic.pak",
            "uuid": "11111111-1111-1111-1111-111111111111",
            "pak_sha256": SOURCE_SHA256, "profile_digest": PROFILE_SHA256, "version64": "1",
        },
        "classification": {"effective_slot": "Underwear"},
        "body_tuple": {"race": "Human", "sex": "Female", "body_type": "BT1"},
        "source_route": {
            "ordered_paths": ["Public/Synthetic/Protected.GR2"],
            "ordered_file_hashes": [SOURCE_SHA256],
        },
        "protected_relations": {"registry_ids": [], "protected_consumers": [], "forbidden_targets": []},
        "disposition": "DEFERRED_WITH_CAUSE", "acceptance_event_id": "UNKNOWN_ACCEPTANCE_EVENT",
    }
    record.update(overrides)
    return record


def evidence(path):
    return [{"path": path, "sha256": VERIFIED_EVIDENCE[path], "claim": "bounded artifact"}]


def profile_proof():
    return {"id": PROFILE_ID, "version": "1", "sha256": PROFILE_SHA256}


def evidence_link(path):
    return {"evidence_path": path, "evidence_sha256": VERIFIED_EVIDENCE[path]}


def protected_relationship():
    return {
        "object_id": "PROTECTED_OBJECT", "registry_id": "REGISTRY_PROTECTED", "consumer": "PROTECTED_CONSUMER",
        "route": "native-route", "path": "Public/Synthetic/Protected.GR2",
        "sha256": SOURCE_SHA256, "forbidden_target": "protected-target",
        "new_target": "new-unaccepted-target",
    }


def protected_consumer_record(**overrides):
    record = ledger_record(protected_relations={"relationships": [protected_relationship()]})
    record.update(overrides)
    return record


def proof_for(reason):
    if reason == "SOURCE_ABSENT_EXACT_PROFILE":
        return {
            "exact_profile": profile_proof(),
            "complete_source_inventory": {"result": "COMPLETE", **evidence_link("evidence/source-audit.json")},
            "zero_route_result": {"result": "ZERO_ROUTE", **evidence_link("evidence/source-audit.json")},
            "anti_omission": {"result": "PASS", **evidence_link("evidence/source-audit.json")},
        }
    if reason == "NO_RELEASE_PERMISSION":
        return {
            "permission_text": {"path": "evidence/permission.txt", "sha256": PERMISSION_SHA256},
            "permission_result": "PROHIBITED",
            "date": "2026-09-01", "credit": "Synthetic Author", "derivative_scope": "NO_DERIVATIVES",
            "redistribution_scope": "NO_REDISTRIBUTION", "exact_source_version": "1",
        }
    if reason == "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE":
        return {
            "exact_slot": "Underwear", "exact_body_tuple": ["Human", "Female", "BT1"],
            "source_contract": "synthetic-source-contract", "release_scope_mismatch": "not advertised",
        }
    if reason == "PROTECTED_NATIVE_ONLY":
        return {
            "protected_registry_id": "REGISTRY_PROTECTED", "protected_consumer": "PROTECTED_CONSUMER",
            "protected_route": "native-route", "protected_path": "Public/Synthetic/Protected.GR2",
            "protected_sha256": SOURCE_SHA256, "forbidden_target": "protected-target",
            "new_target": "new-unaccepted-target",
        }
    if reason == "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT":
        return {
            "exact_profile": profile_proof(),
            "searched_contracts": {
                category: {"result": "COMPLETE", **evidence_link("evidence/source-audit.json")}
                for category in ("root_templates", "named_stats", "inheritance", "visual_banks", "ordered_components", "provider_maps", "uuid_path_hash_aliases")
            },
            "search_result": "ZERO_ROUTE",
            "anti_omission": {"result": "PASS", **evidence_link("evidence/source-audit.json")},
            "anti_omission_pass": True,
        }
    if reason == "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE":
        return {
            "selected_profile_id": PROFILE_ID, "alternate_profile_id": "ALTERNATE_PROFILE",
            "forbidden_module_relationship": "MUTUALLY_EXCLUSIVE",
            "alternate_artifact": {"path": "evidence/alternate-artifact.json", "sha256": SOURCE_SHA256},
        }
    if reason == "NO_SAFE_GEOMETRY_AVAILABLE":
        component = [{"component_id": "garment-a", "status": "FAIL", **evidence_link("evidence/geometry.json")}]
        architectures = [
            {"method_id": "projection-v1", "method_family": "surface-projection", "implementation_sha256": "1" * 64, "candidate_count": 1, "status": "FAILED_FIXED_GATES", "components": component},
            {"method_id": "cage-v1", "method_family": "cage-deformation", "implementation_sha256": "2" * 64, "candidate_count": 1, "status": "FAILED_FIXED_GATES", "components": component},
            {"method_id": "skinning-v1", "method_family": "skinning-transfer", "implementation_sha256": "3" * 64, "candidate_count": 1, "status": "FAILED_FIXED_GATES", "components": component},
        ]
        gates = {
            gate: {"result": "FAIL", **evidence_link("evidence/geometry.json")}
            for gate in ("topology", "component", "material", "skin", "clearance", "silhouette", "deterministic_readback", "nontriviality")
        }
        return {
            "architecture_results": architectures, "fixed_gates": gates,
            "final_available_safe_tooling_failure": {
                "result": "UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING", **evidence_link("evidence/geometry.json")
            },
        }
    raise ValueError(reason)


def exclusion_fixture(**overrides):
    event = {
        "schema": "clothmorph.terminal-exclusion", "schema_version": 1,
        "record_id": RECORD_ID, "identity_sha256": IDENTITY_SHA256,
        "source_profile_id": PROFILE_ID, "mode": "sbbf", "reason": "SOURCE_ABSENT_EXACT_PROFILE",
        "reason_proof": proof_for("SOURCE_ABSENT_EXACT_PROFILE"),
        "scope_statement": "Exclude only the exact synthetic SBBF route.",
        "attempted_architectures": [], "fixed_acceptance_gates": {},
        "evidence": evidence("evidence/source-audit.json"),
        "protected_impact": {"registry_ids": [], "shared_consumers": [], "forbidden_targets": [], "result": "NO_PROTECTED_MUTATION"},
        "next_project_if_reopened": "Recover an exact source profile.",
        "approved_by": "Alan", "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
        "created_utc": "2026-09-01T12:00:00Z",
    }
    event.update(overrides)
    return event


def signed_event(**overrides):
    event = exclusion_fixture(**overrides)
    event["event_id"] = exclusion_event_id(event)
    return event


def geometry_event(proof=None, **overrides):
    proof = proof or proof_for("NO_SAFE_GEOMETRY_AVAILABLE")
    values = {
        "reason": "NO_SAFE_GEOMETRY_AVAILABLE", "reason_proof": proof,
        "attempted_architectures": proof.get("architecture_results", []),
        "fixed_acceptance_gates": proof.get("fixed_gates", {}),
        "evidence": evidence("evidence/geometry.json"),
    }
    values.update(overrides)
    return signed_event(**values)


def validate(event, record=None, verified_evidence=None):
    return validate_exclusion_event(
        event, ledger_record=record or ledger_record(),
        evidence_hashes=VERIFIED_EVIDENCE if verified_evidence is None else verified_evidence,
    )


def select(events, record=None, verified_evidence=None):
    return select_current_exclusion(
        events, RECORD_ID, "sbbf", ledger_record=record or ledger_record(),
        evidence_hashes=VERIFIED_EVIDENCE if verified_evidence is None else verified_evidence,
    )


def test_canonical_payload_is_sorted_json_without_the_event_id():
    payload = json.loads(canonical_exclusion_payload(exclusion_fixture(event_id="EXCLUSION_" + "F" * 64)))

    assert "event_id" not in payload
    assert list(payload) == sorted(payload)


def test_event_id_changes_when_a_bound_payload_field_changes():
    assert exclusion_event_id(exclusion_fixture()) != exclusion_event_id(
        exclusion_fixture(scope_statement="Exclude a different exact route.")
    )


@pytest.mark.parametrize("reason", [
    "SOURCE_ABSENT_EXACT_PROFILE", "NO_RELEASE_PERMISSION", "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE",
    "PROTECTED_NATIVE_ONLY", "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT",
    "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE",
])
def test_each_non_geometry_reason_requires_a_complete_structured_proof(reason):
    path = "evidence/permission.txt" if reason == "NO_RELEASE_PERMISSION" else "evidence/alternate-artifact.json" if reason == "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE" else "Public/Synthetic/Protected.GR2" if reason == "PROTECTED_NATIVE_ONLY" else "evidence/source-audit.json"
    record = protected_consumer_record() if reason == "PROTECTED_NATIVE_ONLY" else None

    assert validate(signed_event(reason=reason, reason_proof=proof_for(reason), evidence=evidence(path)), record) == []


def test_reason_token_in_an_arbitrary_claim_cannot_replace_a_structured_proof():
    event = signed_event(reason_proof={}, evidence=[{
        "path": "evidence/source-audit.json", "sha256": SOURCE_SHA256,
        "claim": "SOURCE_ABSENT_EXACT_PROFILE",
    }])

    assert "MISSING_REASON_PROOF:exact_profile" in validate(event)


def test_permission_and_unsupported_tuple_proofs_bind_the_exact_record_values():
    permission = proof_for("NO_RELEASE_PERMISSION")
    permission["exact_source_version"] = "2"
    tuple_proof = proof_for("NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE")
    tuple_proof["exact_body_tuple"] = ["Human", "Female", "BT2"]

    permission_event = signed_event(
        reason="NO_RELEASE_PERMISSION", reason_proof=permission,
        evidence=evidence("evidence/permission.txt"),
    )
    tuple_event = signed_event(
        reason="NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE", reason_proof=tuple_proof,
        evidence=evidence("evidence/source-audit.json"),
    )

    assert "EXACT_SOURCE_VERSION_MISMATCH" in validate(permission_event)
    assert "EXACT_BODY_TUPLE_MISMATCH" in validate(tuple_event)


def test_geometry_requires_distinct_architecture_component_results_all_fixed_gates_and_final_failure():
    event = geometry_event()

    assert validate(event) == []


@pytest.mark.parametrize("mutation,expected", [
    (lambda proof: proof.update({"architecture_results": []}), "INSUFFICIENT_ARCHITECTURE_RESULTS"),
    (lambda proof: proof["architecture_results"][1].update({"method_family": "surface-projection"}), "NON_DISTINCT_ARCHITECTURE_FAMILIES"),
    (lambda proof: proof["architecture_results"][0].update({"components": [{"component_id": "garment-a", "status": "FAIL"}]}), "INVALID_ARCHITECTURE_COMPONENT_EVIDENCE"),
    (lambda proof: proof["fixed_gates"].pop("silhouette"), "MISSING_FIXED_GATE:silhouette"),
    (lambda proof: proof.update({"final_available_safe_tooling_failure": {}}), "MISSING_FINAL_SAFE_TOOLING_FAILURE"),
])
def test_geometry_rejects_generic_or_incomplete_structured_proof(mutation, expected):
    proof = proof_for("NO_SAFE_GEOMETRY_AVAILABLE")
    mutation(proof)
    event = geometry_event(proof)

    assert expected in validate(event)


def test_geometry_accepts_only_a_structured_hard_contract_impossibility_alternative():
    proof = {"hard_contract_impossibility": {
        "result": "HARD_CONTRACT_IMPOSSIBILITY", "protected_object_id": "PROTECTED_OBJECT",
        "protected_object_path": "Public/Synthetic/Protected.GR2", "protected_object_sha256": SOURCE_SHA256,
        "forbidden_boundary": "GARMENT_ONLY", **evidence_link("Public/Synthetic/Protected.GR2"),
    }}

    assert validate(
        signed_event(reason="NO_SAFE_GEOMETRY_AVAILABLE", reason_proof=proof, evidence=evidence("Public/Synthetic/Protected.GR2")),
        protected_consumer_record(),
    ) == []


@pytest.mark.parametrize("disposition", [
    "ACCEPTED_PROTECTED", "SOURCE_NATIVE_PROTECTED", "PACKAGE_ONLY_PROTECTED", "SHIPPED_NATIVE_PASSTHROUGH",
])
def test_protected_or_accepted_dispositions_cannot_receive_exclusions(disposition):
    assert "EXCLUSION_FORBIDDEN_PROTECTED_OR_ACCEPTED_RECORD" in validate(signed_event(), ledger_record(disposition=disposition))


def test_accepted_relation_or_acceptance_event_cannot_receive_exclusions():
    protected = ledger_record(protected_relations={"accepted_route_ids": ["R"]})

    assert "EXCLUSION_FORBIDDEN_PROTECTED_OR_ACCEPTED_RECORD" in validate(signed_event(), protected)
    assert "EXCLUSION_FORBIDDEN_PROTECTED_OR_ACCEPTED_RECORD" in validate(signed_event(), ledger_record(acceptance_event_id="ACCEPTANCE_EVENT"))


def test_protected_native_only_requires_an_unaccepted_consumer_record():
    event = signed_event(reason="PROTECTED_NATIVE_ONLY", reason_proof=proof_for("PROTECTED_NATIVE_ONLY"), evidence=evidence("Public/Synthetic/Protected.GR2"))

    assert validate(event, protected_consumer_record()) == []
    assert "EXCLUSION_FORBIDDEN_PROTECTED_OR_ACCEPTED_RECORD" in validate(event, protected_consumer_record(disposition="SOURCE_NATIVE_PROTECTED"))


def test_permission_proof_must_prohibit_the_requested_release_operation():
    proof = proof_for("NO_RELEASE_PERMISSION")
    proof["permission_result"] = "PERMITTED"
    proof["derivative_scope"] = "ALLOWED"
    event = signed_event(reason="NO_RELEASE_PERMISSION", reason_proof=proof, evidence=evidence("evidence/permission.txt"))

    assert "PERMISSION_NOT_PROHIBITED" in validate(event)
    assert "DERIVATIVE_SCOPE_NOT_PROHIBITED" in validate(event)


def test_protected_native_proof_must_match_the_record_relationship_and_verified_pair():
    proof = proof_for("PROTECTED_NATIVE_ONLY")
    proof["protected_registry_id"] = "UNRELATED"
    event = signed_event(reason="PROTECTED_NATIVE_ONLY", reason_proof=proof, evidence=evidence("Public/Synthetic/Protected.GR2"))

    assert "PROTECTED_RELATION_MISMATCH" in validate(event, protected_consumer_record())


def test_hard_contract_geometry_rejects_an_unrelated_object_pair():
    proof = {"hard_contract_impossibility": {
        "result": "HARD_CONTRACT_IMPOSSIBILITY", "protected_object_id": "PROTECTED_OBJECT",
        "protected_object_path": "evidence/source-audit.json", "protected_object_sha256": SOURCE_SHA256,
        "forbidden_boundary": "GARMENT_ONLY", **evidence_link("evidence/source-audit.json"),
    }}
    event = signed_event(reason="NO_SAFE_GEOMETRY_AVAILABLE", reason_proof=proof, evidence=evidence("evidence/source-audit.json"))

    assert "HARD_CONTRACT_OBJECT_MISMATCH" in validate(event, protected_consumer_record())


def test_source_exhaustion_requires_every_enumerated_contract_category_and_anti_omission_true():
    proof = proof_for("UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT")
    del proof["searched_contracts"]["named_stats"]
    proof["anti_omission_pass"] = False
    event = signed_event(reason="UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT", reason_proof=proof, evidence=evidence("evidence/source-audit.json"))

    errors = validate(event)

    assert "MISSING_SEARCHED_CONTRACT:named_stats" in errors
    assert "ANTI_OMISSION_NOT_TRUE" in errors


def test_geometry_summary_must_exactly_match_the_structured_architectures_and_gates():
    proof = proof_for("NO_SAFE_GEOMETRY_AVAILABLE")
    event = geometry_event(proof, attempted_architectures=[], fixed_acceptance_gates={})

    errors = validate(event)

    assert "ATTEMPTED_ARCHITECTURES_MISMATCH" in errors
    assert "FIXED_ACCEPTANCE_GATES_MISMATCH" in errors


def test_evidence_path_and_hash_must_match_the_same_verified_registry_entry():
    event = signed_event(evidence=[{
        "path": "evidence/source-audit.json", "sha256": PERMISSION_SHA256, "claim": "bounded artifact",
    }])

    assert "EVIDENCE_PATH_HASH_MISMATCH:0" in validate(event)


def test_rejects_unknown_reason_blank_binding_tampered_id_and_tiefling():
    malformed = signed_event(reason="TIME_RAN_OUT", reason_proof={}, record_id="", identity_sha256="b" * 64, source_profile_id="", mode="")
    malformed["event_id"] = "EXCLUSION_" + "F" * 64
    tiefling = ledger_record(source_module={"folder": "ClothMorphTieflingBT1_TEST", "pak": "ClothMorphTieflingBT1_TEST.pak", "uuid": "b57bab2c-5679-5445-8fee-ca8c282990a5", "pak_sha256": TIEFLING_PAK_SHA256})

    errors = validate(malformed)

    assert "INVALID_EXCLUSION_REASON:TIME_RAN_OUT" in errors
    assert "BLANK:record_id" in errors
    assert "INVALID_SHA256:identity_sha256" in errors
    assert "EVENT_ID_MISMATCH" in errors
    assert "EXCLUSION_FORBIDDEN_ACCEPTED_TIEFLING" in validate(signed_event(), tiefling)


def test_selector_uses_newest_valid_non_revoked_event_only():
    older = signed_event(created_utc="2026-09-01T12:00:00Z")
    newer = signed_event(created_utc="2026-09-01T12:01:00Z")

    selection = select([older, newer])

    assert isinstance(selection, ExclusionSelection)
    assert selection.event == newer
    assert selection.errors == ()


def test_selector_rejects_an_invalid_newest_or_historical_normal_event():
    valid = signed_event()
    invalid_newest = signed_event(created_utc="2026-09-01T12:01:00Z", reason_proof={})
    invalid_historical = signed_event(reason_proof={})

    newest = select([valid, invalid_newest])
    historical = select([invalid_historical, signed_event(created_utc="2026-09-01T12:01:00Z")])

    assert newest.event is None
    assert "INVALID_EVENT:1:MISSING_REASON_PROOF:exact_profile" in newest.errors
    assert historical.event is None
    assert "INVALID_EVENT:0:MISSING_REASON_PROOF:exact_profile" in historical.errors


def test_selector_rejects_duplicates_and_same_time_conflicts_even_if_later_revoked():
    event = signed_event()
    conflict = signed_event(reason="NO_RELEASE_PERMISSION", reason_proof=proof_for("NO_RELEASE_PERMISSION"), evidence=evidence("evidence/permission.txt"))
    revocation = {"event_type": "REVOCATION", "record_id": RECORD_ID, "mode": "sbbf", "revokes_event_id": event["event_id"], "created_utc": "2026-09-01T12:01:00Z"}

    duplicate = select([event, deepcopy(event)])
    hidden_conflict = select([event, conflict, revocation])

    assert duplicate.errors == ("DUPLICATE_EXCLUSION_EVENT_ID",)
    assert hidden_conflict.errors == ("CONFLICTING_EXCLUSION_EVENTS",)


def test_selector_honors_a_later_valid_revocation_and_refuses_orphan_revocation():
    event = signed_event()
    revocation = {"event_type": "REVOCATION", "record_id": RECORD_ID, "mode": "sbbf", "revokes_event_id": event["event_id"], "created_utc": "2026-09-01T12:01:00Z"}
    orphan = dict(revocation, revokes_event_id="EXCLUSION_" + "F" * 64)

    assert select([event, revocation]).event is None
    assert select([orphan]).errors == ("REVOCATION_WITHOUT_PRIOR_EVENT",)
