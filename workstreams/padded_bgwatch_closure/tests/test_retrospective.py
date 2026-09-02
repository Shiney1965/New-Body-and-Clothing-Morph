"""Portable frozen-byte readback tests; these receipts make no garment claims."""

from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import json

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure.geometry import parse_collada_geometry, serialize_collada_positions
from workstreams.padded_bgwatch_closure.tests.test_local_integration import _prepared_fixture, _verified


def api():
    try:
        return importlib.import_module("workstreams.padded_bgwatch_closure.retrospective")
    except ModuleNotFoundError:
        pytest.fail("The frozen-artifact retrospective evaluator is not implemented")


def digest(content):
    return hashlib.sha256(content).hexdigest().upper()


def receipt(content, name):
    module = api()
    manifest = json.dumps({"schema_version": 1, "record_count": 1, "records": [
        {"relative_path": name, "bytes": len(content), "sha256": digest(content)},
    ]}, sort_keys=True).encode()
    return module.FrozenArtifact(content, (module.ManifestLink(manifest, digest(manifest), name),))


def fixture(candidate_transform=None, *, name="transfer", geometry_id="lod0"):
    module = api()
    prepared = _prepared_fixture()
    positions = prepared.source.positions.copy()
    if candidate_transform:
        positions = candidate_transform(positions)
    content = serialize_collada_positions(prepared.verified_source, prepared.source, positions)
    return module.ReadbackInputs(
        receipt(prepared.verified_source.content, "source.dae"),
        receipt(prepared.verified_body.content, "body.glb"),
        receipt(content, "candidate.dae"), name, geometry_id, "SYNTHETIC_FIXTURE",
    )


def evaluate(inputs=None, profile=None):
    module = api()
    return module.evaluate_frozen(inputs or fixture(), profile or module.load_profile())


def test_unchanged_frozen_bytes_report_literal_active_failure_ids_not_generator_failure():
    """Catches omitted failure identities or promotion of parse equality to generation proof."""
    report = evaluate()
    assert report["measurements"]["active_vertices_below_clearance"]["ids"] == [0, 1, 2]
    assert report["measurements"]["active_vertices_below_clearance"]["count"] == 3
    assert report["identities"]["original_active_ids"] == [0, 1, 2]
    assert report["identities"]["fixed_cohort_body_vertex_ids"] == [0, 1, 2]
    assert report["readback"]["same_frozen_bytes_repeated_equal"] is True
    assert report["readback"]["generator_rerun_performed"] is False
    assert report["readback"]["generator_determinism"] == "UNASSESSED"
    assert report["construction"]["gates_governed_by_this_profile"] is False
    assert report["geometry_policy_eligibility"] == "UNASSESSED_OR_BLOCKED"
    assert report["event_ready"] is False
    assert report["evidence_scope"] == "SYNTHETIC_FIXTURE"
    assert not {"event_id", "record_id", "source_profile_id"}.intersection(report)


@pytest.mark.parametrize("field", ["source", "body", "candidate"])
def test_changed_artifact_bytes_are_rejected_even_with_old_receipt(field):
    inputs = fixture()
    artifact = getattr(inputs, field)
    with pytest.raises(ValueError, match="ARTIFACT.*MISMATCH"):
        evaluate(replace(inputs, **{field: replace(artifact, content=artifact.content + b" ")}))


@pytest.mark.parametrize("field", ["source", "body", "candidate"])
def test_missing_manifest_provenance_is_not_replaced_by_a_self_hash(field):
    inputs = fixture()
    with pytest.raises(ValueError, match="PROVENANCE_REQUIRED"):
        evaluate(replace(inputs, **{field: replace(getattr(inputs, field), provenance=())}))


def test_manifest_member_rebinding_and_changed_manifest_fail_closed():
    inputs = fixture()
    link = inputs.candidate.provenance[0]
    for changed in [replace(link, member_path="nearby.dae"), replace(link, content=link.content + b" ")]:
        with pytest.raises(ValueError, match="MANIFEST"):
            evaluate(replace(inputs, candidate=replace(inputs.candidate, provenance=(changed,))))


def test_input_and_receipt_are_deeply_immutable():
    inputs = fixture()
    with pytest.raises(FrozenInstanceError):
        inputs.candidate.content = b"different"
    with pytest.raises((TypeError, ValueError), match="IMMUTABLE"):
        api().FrozenArtifact(bytearray(inputs.candidate.content), inputs.candidate.provenance)
    with pytest.raises((TypeError, ValueError), match="IMMUTABLE"):
        api().FrozenArtifact(inputs.candidate.content, list(inputs.candidate.provenance))


def test_synthetic_source_cannot_be_promoted_by_changing_scope():
    with pytest.raises(ValueError, match="CANONICAL.*IDENTITY"):
        evaluate(replace(fixture(), evidence_scope="CANONICAL_PADDED"))


def test_explicit_actual_mesh_selection_rejects_wrong_or_missing_selector():
    for selector in ("lod1", "HUM_F_ARM_BG_Watch_Leather_A_Body.dae", ""):
        with pytest.raises(ValueError, match="GEOMETRY_SELECTION"):
            evaluate(fixture(geometry_id=selector))


def test_profile_mutation_cannot_relax_gate_and_returned_document_is_detached():
    module = api()
    profile = module.load_profile()
    doc = json.loads(profile.content)
    doc["gates"]["target_clearance_m"] = -1
    with pytest.raises(ValueError, match="PROFILE.*MISMATCH"):
        evaluate(profile=replace(profile, content=json.dumps(doc).encode()))
    detached = profile.document
    detached["gates"]["target_clearance_m"] = -1
    assert evaluate(profile=profile)["measurements"]["active_vertices_below_clearance"]["ids"] == [0, 1, 2]


def test_missing_component_criteria_do_not_become_pass_when_body_gates_pass():
    def lift(points):
        points[:3, 2] = 0.002
        return points
    report = evaluate(fixture(lift))
    assert report["measurements"]["active_vertices_below_clearance"]["ids"] == []
    assert report["unavailable_checks"]["predeclared_silhouette"] == "UNASSESSED"
    assert report["unavailable_checks"]["predeclared_nontriviality"] == "UNASSESSED"
    assert report["unavailable_checks"]["pants_component_result"] == "UNASSESSED"
    assert report["unavailable_checks"]["complete_route_skin_lod_material_contract"] == "UNASSESSED"
    assert "ATOMIC_COMPONENT_MEMBERSHIP_UNRESOLVED" in report["blockers"]
    assert report["proposals"]["reason"]["approved"] is False
    assert report["proposals"]["reopening"]["approved"] is False
    assert report["geometry_policy_eligibility"] == "UNASSESSED_OR_BLOCKED"


def test_global_movement_outside_current_roi_is_not_a_historical_contract_failure():
    def move_fixed(points):
        points[3:, 0] += 0.0001
        return points
    report = evaluate(fixture(move_fixed))
    comparison = report["current_roi_comparison"]
    assert comparison["fixed_vertex_moves"]["ids"] == [3, 4, 5]
    assert comparison["moved_position_deltas"][0] == {"vertex_id": 3, "delta_xyz": [0.0001, 0.0, 0.0]}
    assert comparison["historical_domain_applicability"] == "NOT_ESTABLISHED"
    assert report["construction"]["original_movement_domain"] == "GLOBAL"
    assert "FIXED_VERTEX_MOVES" not in report["current_necessary_gate_failures"]


def test_old_local_readback_cannot_relabel_target_feasibility():
    report = evaluate(fixture(name="local"))
    assert report["construction"]["target_status"] == "TARGET_NOT_CERTIFIED"
    assert report["construction"]["valid_target_exhausted_architecture"] is False
    assert "HISTORICAL_LOCAL_TARGET_NOT_CERTIFIED" in report["blockers"]
    assert report["construction"]["generator_rerun"] is False


def test_flipped_and_zero_area_faces_retain_exact_failure_ids_and_json_safe_metrics():
    def flip(points):
        points[[1, 2]] = points[[2, 1]]
        return points
    report = evaluate(fixture(flip))
    assert report["measurements"]["flipped_faces"]["ids"] == [0]
    assert "FLIPPED_FACES" in report["current_necessary_gate_failures"]
    def collapse(points):
        points[1] = points[0]
        return points
    report = evaluate(fixture(collapse))
    assert report["measurements"]["new_zero_area_faces"]["ids"] == [0]
    assert report["extrema"]["minimum_orientation_cosine"] is None
    json.dumps(report, allow_nan=False)


def test_topology_corruption_is_not_evaluated_on_assumed_original_indices():
    inputs = fixture()
    data = inputs.candidate.content.replace(b"0 0 1 0 2 0", b"0 0 2 0 1 0")
    assert data != inputs.candidate.content
    report = evaluate(replace(inputs, candidate=receipt(data, "candidate.dae")))
    assert report["source_invariants"]["face_indices_equal"] is False
    assert report["measurements"] == {}
    assert "CANDIDATE_TOPOLOGY_OR_SHAPE_CHANGED" in report["blockers"]


def test_whole_document_difference_does_not_hide_behind_selected_body_positions():
    inputs = fixture()
    data = inputs.candidate.content.replace(b"material=\"cloth\"", b"material=\"altered\"")
    assert data != inputs.candidate.content
    report = evaluate(replace(inputs, candidate=receipt(data, "candidate.dae")))
    assert report["source_invariants"]["whole_document_except_selected_position_bytes_equal"] is False
    assert "NON_POSITION_SEMANTICS_MISMATCH" in report["current_necessary_gate_failures"]
    assert report["unavailable_checks"]["complete_route_skin_lod_material_contract"] == "UNASSESSED"


def test_nested_manifest_receipt_binds_each_parent_child_byte_link():
    module = api()
    leaf = receipt(b"candidate", "candidate.dae")
    child = leaf.provenance[0]
    root = json.dumps({"records": [{"relative_path": "child.json", "bytes": len(child.content),
                                   "sha256": digest(child.content)}]}).encode()
    artifact = module.FrozenArtifact(leaf.content, (
        module.ManifestLink(root, digest(root), "child.json"), child,
    ))
    assert module.verify_artifact(artifact) == digest(b"candidate")
    bad = replace(child, content=child.content + b" ", expected_sha256=digest(child.content + b" "))
    with pytest.raises(ValueError, match="MANIFEST_CHAIN_MISMATCH"):
        module.verify_artifact(replace(artifact, provenance=(artifact.provenance[0], bad)))


def test_report_mutation_cannot_change_next_readback_and_bytes_repeat_exactly():
    inputs = fixture()
    report = evaluate(inputs)
    pristine = json.dumps(report, sort_keys=True, allow_nan=False)
    report["measurements"]["active_vertices_below_clearance"]["ids"].clear()
    assert json.dumps(evaluate(inputs), sort_keys=True, allow_nan=False) == pristine


def write_corpus(tmp_path, *, nested=False, path="candidate.dae"):
    content = b"the retained candidate"
    (tmp_path / "candidate.dae").write_bytes(content)
    records = [{"relative_path": path, "bytes": len(content), "sha256": digest(content)}]
    if nested:
        child = json.dumps({"records": [{"path": str(tmp_path / "candidate.dae"),
                                         "role": "failed_position_candidate_dae",
                                         "bytes": len(content), "sha256": digest(content)}]}).encode()
        (tmp_path / "evidence").mkdir()
        (tmp_path / "evidence/source_and_control_manifest.json").write_bytes(child)
        records = [{"relative_path": "evidence/source_and_control_manifest.json",
                    "bytes": len(child), "sha256": digest(child)}]
    else:
        (tmp_path / "evidence").mkdir()
    root = json.dumps({"records": records, "record_count": len(records)}).encode()
    (tmp_path / "evidence/ARTIFACT_MANIFEST.json").write_bytes(root)
    return digest(root), digest(content)


@pytest.mark.parametrize("nested", [False, True])
def test_reader_uses_exact_parent_member_not_filename_guesses(tmp_path, nested):
    root_sha, wanted_sha = write_corpus(tmp_path, nested=nested)
    (tmp_path / "candidate-nearby.dae").write_bytes(b"wrong")
    artifact = api().read_manifest_artifact(tmp_path, wanted_sha, expected_manifest_sha256=root_sha)
    assert artifact.content == b"the retained candidate"
    assert len(artifact.provenance) == (2 if nested else 1)
    assert api().verify_artifact(artifact) == wanted_sha


def test_reader_refuses_changed_root_and_changed_leaf_and_unregistered_digest(tmp_path):
    root_sha, wanted_sha = write_corpus(tmp_path)
    with pytest.raises(ValueError, match="MANIFEST_DIGEST_MISMATCH"):
        api().read_manifest_artifact(tmp_path, wanted_sha)
    with pytest.raises(ValueError, match="MANIFEST.*NOT_UNIQUE"):
        api().read_manifest_artifact(tmp_path, "F" * 64, expected_manifest_sha256=root_sha)
    (tmp_path / "candidate.dae").write_bytes(b"changed")
    with pytest.raises(ValueError, match="ARTIFACT_DIGEST_MISMATCH"):
        api().read_manifest_artifact(tmp_path, wanted_sha, expected_manifest_sha256=root_sha)


def test_reader_refuses_relative_manifest_escape(tmp_path):
    root_sha, wanted_sha = write_corpus(tmp_path, path="../candidate.dae")
    with pytest.raises(ValueError, match="MANIFEST_PATH_OUTSIDE_ROOT"):
        api().read_manifest_artifact(tmp_path, wanted_sha, expected_manifest_sha256=root_sha)


def test_existing_gate_mutation_cannot_silently_change_profile(monkeypatch):
    from workstreams.padded_bgwatch_closure import solver
    monkeypatch.setattr(solver, "INTERNAL_MIN_AREA_RATIO", 0.1)
    with pytest.raises(ValueError, match="PROFILE_IMPLEMENTATION_GATE_MISMATCH"):
        evaluate()


def test_duplicate_member_paths_and_invalid_record_sizes_are_rejected():
    module = api()
    content = b"candidate"
    row = {"relative_path": "candidate.dae", "bytes": len(content), "sha256": digest(content)}
    for records in ([row, row], [{**row, "bytes": True}]):
        manifest = json.dumps({"records": records}).encode()
        artifact = module.FrozenArtifact(content, (module.ManifestLink(manifest, digest(manifest), "candidate.dae"),))
        with pytest.raises(ValueError, match="MANIFEST_RECORD_INVALID"):
            module.verify_artifact(artifact)


def test_unrounded_retained_candidate_is_measured_without_silently_rewriting_it():
    inputs = fixture()
    content = inputs.candidate.content.replace(b"-0.010000", b"-0.0100001", 1)
    assert content != inputs.candidate.content
    report = evaluate(replace(inputs, candidate=receipt(content, "candidate.dae")))
    assert report["identities"]["candidate_sha256"] == digest(content)
    assert report["serialization_observation"]["candidate_rewritten"] is False
    assert "CURRENT_SERIALIZATION_PRECISION_NOT_MET" in report["blockers"]


def test_changed_retained_lod_and_controller_are_not_claimed_preserved():
    inputs = fixture()
    for change in (
        lambda data: data.replace(b"<library_geometries>", b"<library_controllers><controller id=\"changed\"/></library_controllers><library_geometries>"),
        lambda data: data.replace(b"<geometry id=\"lod1\"", b"<geometry id=\"changed-lod\""),
    ):
        content = change(inputs.candidate.content)
        assert content != inputs.candidate.content
        report = evaluate(replace(inputs, candidate=receipt(content, "candidate.dae")))
        assert report["source_invariants"]["whole_document_except_selected_position_bytes_equal"] is False
        assert "NON_POSITION_SEMANTICS_MISMATCH" in report["current_necessary_gate_failures"]


def test_synthetic_construction_section_does_not_publish_canonical_candidate_digest_as_its_own():
    report = evaluate()
    assert "sha256" not in report["construction"]
    assert report["construction"]["historical_reference_sha256"] is None


def test_duplicate_geometry_identifier_cannot_confuse_masked_position_identity():
    inputs = fixture()
    content = inputs.candidate.content.replace(b"id=\"lod1\"", b"id=\"lod0\"")
    assert content != inputs.candidate.content
    with pytest.raises(ValueError, match="GEOMETRY_SELECTION_NONUNIQUE_IDS"):
        evaluate(replace(inputs, candidate=receipt(content, "candidate.dae")))


def test_effective_coverage_distance_cannot_drift_from_frozen_profile(monkeypatch):
    """Catches the helper silently weakening coverage while preserving cohort IDs."""
    module = api()
    def lift(points):
        points[:, 2] += 0.1
        return points
    inputs = fixture(lift)
    baseline = evaluate(inputs)
    assert baseline["measurements"]["fixed_cohort_coverage_loss"]["ids"] == [0, 1, 2]
    original = module.derive_fixed_coverage_contract
    def weakened(*args, **kwargs):
        fixed = original(*args, **kwargs)
        return replace(fixed, contract=replace(fixed.contract, maximum_distance=0.5))
    monkeypatch.setattr(module, "derive_fixed_coverage_contract", weakened)
    with pytest.raises(ValueError, match="PROFILE_EFFECTIVE_COVERAGE_DISTANCE_MISMATCH"):
        evaluate(inputs)
