"""Prospective common-gate / eligibility / event_ready criteria tests."""

from dataclasses import replace
import hashlib
import importlib
import json

import pytest


def api():
    try:
        return importlib.import_module("workstreams.padded_bgwatch_closure.prospective_common_gate")
    except ModuleNotFoundError:
        pytest.fail("Prospective common-gate adjudicator is not implemented")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


POLICY_GATES = {
    "topology": {
        "maximum_flipped_faces": 0,
        "maximum_new_zero_area_faces": 0,
        "published_area_ratio": [0.5, 2.0],
        "internal_area_ratio": [0.51, 1.99],
        "minimum_orientation_cosine": 0.05,
    },
    "clearance": {
        "target_clearance_m": 0.001,
        "reject_surface_ambiguity": True,
    },
    "coverage": {
        "outward_projection": "strictly_positive",
        "maximum_distance_m": 0.05,
        "fixed_cohort_coverage_loss_max": 0,
    },
}


def qualifying_architecture(name: str) -> dict:
    return {
        "name": name,
        "qualifying_status": "QUALIFYING",
        "used_common_gates": True,
        "gates_identical_to_policy": True,
        "component_failures_recorded": True,
        "generator_repeatability": "PROVEN_REAL_RECONSTRUCTIONS",
        "result": "FAILED_ALL_CASES",
    }


def complete_gates(**overrides) -> dict:
    base = {
        "nontriviality": "PREDECLARED_NUMERICAL",
        "silhouette": "PREDECLARED_NUMERICAL",
        "topology": dict(POLICY_GATES["topology"]),
        "clearance": dict(POLICY_GATES["clearance"]),
        "coverage": dict(POLICY_GATES["coverage"]),
        "component": "RESOLVED",
        "material_skin_lod": "RESOLVED",
        "deterministic_readback": "PROVEN_REAL_RECONSTRUCTIONS",
    }
    base.update(overrides)
    return base


def eligible_evidence(**overrides) -> dict:
    evidence = {
        "common_gates_predeclared": complete_gates(),
        "architectures": [
            qualifying_architecture("smooth_nearest_vertex_body_transfer"),
            qualifying_architecture("global_nearest_target_vertex_normal_clipping"),
            qualifying_architecture("strict_global_alpha_interpolation"),
            qualifying_architecture("current_connected_roi_field"),
        ],
        "atomic_component_membership": "RESOLVED",
        "complete_route_skin_lod_material_contract": "RESOLVED",
        "retrospective_readback_only": False,
        "canonical_source_profile_record_mode": "UNRESOLVED",
        "protected_registry_shared_consumers": "UNRESOLVED",
        "independent_review_approved": False,
        "proposals": {
            "reason": {"value": "NO_SAFE_GEOMETRY_AVAILABLE", "approved": False},
            "reopening": {
                "value": "separately reviewed remesh or source replacement",
                "approved": False,
            },
        },
    }
    evidence.update(overrides)
    return evidence


def test_default_evidence_is_nonterminal_and_release_blocking():
    report = api().adjudicate({})
    assert report["policy_kind"] == "PROSPECTIVE_COMMON_GATE_POLICY"
    assert report["policy_sha256"] == api().POLICY_SHA256
    assert report["historical_predeclaration_rewritten"] is False
    assert report["geometry_policy_eligibility"] == "UNASSESSED_OR_BLOCKED"
    assert report["event_ready"] is False
    assert report["release_blocking"] is True
    assert report["terminal_exclusion_attached"] is False
    assert report["measurement_wave_performed"] is False
    assert report["architecture_exhaustion"] == "NOT_MET"
    assert "PREDECLARED_NONTRIVIALITY_UNASSESSED" in report["blockers"]
    assert "PREDECLARED_SILHOUETTE_UNASSESSED" in report["blockers"]
    assert not {"event_id", "record_id", "source_profile_id"}.intersection(
        {k for k, v in report["identifiers"].items() if v is not None}
    )


def test_retrospective_readback_alone_cannot_become_eligible_or_event_ready():
    report = api().adjudicate(
        {
            "retrospective_readback_only": True,
            "common_gates_predeclared": complete_gates(),
            "architectures": [
                qualifying_architecture("smooth_nearest_vertex_body_transfer"),
                qualifying_architecture("global_nearest_target_vertex_normal_clipping"),
                qualifying_architecture("current_connected_roi_field"),
            ],
            "atomic_component_membership": "RESOLVED",
            "complete_route_skin_lod_material_contract": "RESOLVED",
        }
    )
    assert report["geometry_policy_eligibility"] == "UNASSESSED_OR_BLOCKED"
    assert report["event_ready"] is False
    assert "RETROSPECTIVE_READBACK_ONLY_NOT_COMMON_GATE_PROOF" in report["blockers"]


def test_local_target_not_certified_does_not_count_toward_exhaustion():
    report = api().adjudicate(
        {
            "common_gates_predeclared": complete_gates(),
            "architectures": [
                qualifying_architecture("smooth_nearest_vertex_body_transfer"),
                qualifying_architecture("global_nearest_target_vertex_normal_clipping"),
                {
                    "name": "confidence_gated_local_clearance_repair",
                    "qualifying_status": "EXCLUDED_TARGET_NOT_CERTIFIED",
                    "used_common_gates": False,
                    "gates_identical_to_policy": False,
                    "component_failures_recorded": True,
                    "generator_repeatability": "UNASSESSED",
                    "result": "FAILED_ALL_CASES",
                },
            ],
            "atomic_component_membership": "RESOLVED",
            "complete_route_skin_lod_material_contract": "RESOLVED",
        }
    )
    assert report["qualifying_architecture_count"] == 2
    assert report["architecture_exhaustion"] == "NOT_MET"
    assert "HISTORICAL_LOCAL_TARGET_NOT_CERTIFIED" in report["blockers"]
    assert "ARCHITECTURE_EXHAUSTION_COUNT_NOT_MET" in report["blockers"]


def test_parameter_retune_is_not_a_distinct_architecture():
    report = api().adjudicate(
        {
            "common_gates_predeclared": complete_gates(),
            "architectures": [
                qualifying_architecture("smooth_nearest_vertex_body_transfer"),
                qualifying_architecture("global_nearest_target_vertex_normal_clipping"),
                {
                    "name": "smooth_nearest_vertex_body_transfer_retune",
                    "qualifying_status": "PARAMETER_RETUNE_OF_EXISTING",
                    "used_common_gates": True,
                    "gates_identical_to_policy": True,
                    "component_failures_recorded": True,
                    "generator_repeatability": "PROVEN_REAL_RECONSTRUCTIONS",
                    "result": "FAILED_ALL_CASES",
                },
            ],
            "atomic_component_membership": "RESOLVED",
            "complete_route_skin_lod_material_contract": "RESOLVED",
        }
    )
    assert "PARAMETER_TUNING_NOT_DISTINCT_ARCHITECTURE" in report["blockers"]
    assert report["architecture_exhaustion"] == "NOT_MET"


def test_mismatched_clearance_gate_blocks_common_gate_predeclaration():
    gates = complete_gates()
    gates["clearance"] = {"target_clearance_m": 0.0, "reject_surface_ambiguity": False}
    report = api().adjudicate(
        eligible_evidence(common_gates_predeclared=gates)
    )
    assert report["geometry_policy_eligibility"] == "UNASSESSED_OR_BLOCKED"
    assert "COMMON_GATE_CLEARANCE_MISMATCH" in report["blockers"]


def test_eligible_still_keeps_event_ready_false_without_bindings_and_review():
    report = api().adjudicate(eligible_evidence())
    assert report["geometry_policy_eligibility"] == "ELIGIBLE"
    assert report["architecture_exhaustion"] == "MET"
    assert report["qualifying_architecture_count"] == 4
    assert report["event_ready"] is False
    assert report["release_blocking"] is True
    assert report["terminal_exclusion_attached"] is False
    assert "CANONICAL_PROFILE_RECORD_MODE_UNRESOLVED" in report["blockers"]
    assert "PROTECTED_REGISTRY_SHARED_CONSUMERS_UNRESOLVED" in report["blockers"]
    assert "INDEPENDENT_REVIEW_NOT_APPROVED" in report["blockers"]
    assert "PROPOSALS_NOT_APPROVED" in report["blockers"]


def test_event_ready_requires_all_bindings_review_and_approved_proposals():
    report = api().adjudicate(
        eligible_evidence(
            canonical_source_profile_record_mode="BOUND",
            protected_registry_shared_consumers="PROVEN",
            independent_review_approved=True,
            identifier_authority="INDEPENDENTLY_BOUND",
            record_id="LEDGER_" + ("A" * 64),
            identity_sha256="B" * 64,
            source_profile_id="bg3-base-padded-profile",
            proposals={
                "reason": {"value": "NO_SAFE_GEOMETRY_AVAILABLE", "approved": True},
                "reopening": {
                    "value": "separately approved manual-remesh project",
                    "approved": True,
                },
            },
        )
    )
    assert report["geometry_policy_eligibility"] == "ELIGIBLE"
    assert report["event_ready"] is True
    assert report["release_blocking"] is True  # still true until an exclusion is attached elsewhere
    assert report["terminal_exclusion_attached"] is False
    assert report["measurement_wave_performed"] is False


def test_unbound_identifiers_block_even_when_strings_are_supplied():
    report = api().adjudicate(
        eligible_evidence(
            record_id="LEDGER_" + ("C" * 64),
            identity_sha256="D" * 64,
            source_profile_id="some-profile",
            identifier_authority="UNRESOLVED",
        )
    )
    assert report["geometry_policy_eligibility"] == "BLOCKED"
    assert report["event_ready"] is False
    assert "INVENTED_OR_UNBOUND_IDENTIFIERS" in report["blockers"]


def test_invented_identifier_prefix_is_rejected():
    with pytest.raises(ValueError, match="INVENTED_IDENTIFIER"):
        api().adjudicate(eligible_evidence(record_id="INVENTED_LEDGER_X"))


def test_measurement_wave_and_terminal_attach_flags_are_hard_refused():
    with pytest.raises(ValueError, match="MEASUREMENT_WAVE_FORBIDDEN"):
        api().adjudicate({"measurement_wave_performed": True})
    with pytest.raises(ValueError, match="AUTO_ATTACH_TERMINAL_EXCLUSION_FORBIDDEN"):
        api().adjudicate({"terminal_exclusion_attached": True})


def test_policy_mutation_fails_closed_and_document_is_detached():
    module = api()
    policy = module.load_policy()
    doc = json.loads(policy.content)
    doc["architecture_qualification"]["minimum_qualifying_architectures"] = 1
    with pytest.raises(ValueError, match="POLICY_DIGEST_MISMATCH"):
        module.adjudicate({}, policy=replace(policy, content=json.dumps(doc).encode()))
    detached = policy.document
    detached["architecture_qualification"]["minimum_qualifying_architectures"] = 1
    report = module.adjudicate({})
    assert report["architecture_exhaustion"] == "NOT_MET"


def test_report_mutation_does_not_affect_next_adjudication():
    report = api().adjudicate({})
    pristine = json.dumps(report, sort_keys=True)
    report["event_ready"] = True
    report["blockers"].clear()
    assert json.dumps(api().adjudicate({}), sort_keys=True) == pristine


def test_current_accepted_search_pin_is_exposed_but_insufficient_alone():
    report = api().adjudicate({})
    pins = report["accepted_bounded_evidence_pins"]
    assert pins["current_repeated_search_sha256"] == (
        "5DAD7E910EB0E09E9E53EC9EE9444F916A9669AF885C6F7AD182432C98B9CA0A"
    )
    assert pins["frozen_readback_crosswalk_commit"].startswith("6731cbf")
    assert report["event_ready"] is False
