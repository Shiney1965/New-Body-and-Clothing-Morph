from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from workstreams.bard_authority_closure.bard_sbbf_repair import (
    BASE_STREAMS,
    PASS_REPAIRED,
    PASS_UNCHANGED,
    CompletePairResult,
    complete_sbbf_pair,
    failing_face_neighborhood,
    solve_local_area_constrained_positions,
    topology_metrics,
    verify_outside_region_exact,
    write_offline_result,
)
from workstreams.bard_authority_closure.configuration import (
    ConfigurationError,
    load_local_configuration,
    verify_evidence_inputs,
)


LEGACY_INPUT_IDS = {
    "legacy_bard_contracts_py",
    "legacy_glb_contract_py",
    "legacy_reconstruct_positions_py",
    "body_bcb_glb",
    "body_sbbf_glb",
    "base_source_glb",
    "thong_source_glb",
    "legacy_offline_search_report",
}
SLEEVE_STREAM = "HUM_F_ARM_Bard_Sleeves_Mesh"
THONG_STREAM = "HUM_F_ARM_Gortash_Body_Jacket_Mesh"


def _synthetic_low_area_mesh() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
            [2.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
        ],
        dtype="<f4",
    )
    candidate = source.copy()
    candidate[2] = [0.0, 0.1, 0.0]
    faces = np.asarray(
        [
            [0, 1, 2],
            [1, 3, 2],
            [1, 4, 3],
            [5, 6, 7],
        ],
        dtype="<u4",
    )
    return source, candidate, faces


def _passing_result(offset: float = 0.0):
    source = np.asarray(
        [[offset, 0.0, 0.0], [offset + 1.0, 0.0, 0.0], [offset, 1.0, 0.0]],
        dtype="<f4",
    )
    return solve_local_area_constrained_positions(
        source,
        source.copy(),
        np.asarray([[0, 1, 2]], dtype="<u4"),
    )


def _passing_pair() -> tuple[dict[str, object], object]:
    base = {
        name: _passing_result(float(index) * 10.0)
        for index, name in enumerate(BASE_STREAMS)
    }
    return base, _passing_result(100.0)


def test_failing_face_neighborhood_is_only_the_seed_face_one_ring():
    source, candidate, faces = _synthetic_low_area_mesh()

    region = failing_face_neighborhood(source, candidate, faces)

    assert region.failing_face_indices == (0,)
    assert region.seed_vertex_indices == (0, 1, 2)
    assert region.one_ring_face_indices == (0, 1, 2)
    assert region.movable_vertex_indices == (0, 1, 2, 3, 4)
    assert region.affected_face_indices == (0, 1, 2)


def test_solver_repairs_the_full_mesh_without_moving_any_outside_float32_row():
    source, candidate, faces = _synthetic_low_area_mesh()

    result = solve_local_area_constrained_positions(source, candidate, faces)

    assert result.status == PASS_REPAIRED
    assert result.positions is not None
    assert result.positions.dtype == np.dtype("<f4")
    assert result.pre_metrics.below_area_floor == 1
    assert result.post_metrics is not None
    assert result.post_metrics.flipped_faces == 0
    assert result.post_metrics.new_zero_area_faces == 0
    assert result.post_metrics.below_area_floor == 0
    assert result.post_metrics.minimum_area_ratio >= 0.25
    assert result.outside_gate is not None
    assert result.outside_gate.passed
    np.testing.assert_array_equal(result.positions[5:], candidate[5:])


def test_outside_region_gate_rejects_one_changed_float32_row():
    source, candidate, faces = _synthetic_low_area_mesh()
    region = failing_face_neighborhood(source, candidate, faces)
    escaped = candidate.copy()
    escaped[7, 2] = np.float32(0.5)

    report = verify_outside_region_exact(candidate, escaped, region.movable_vertex_indices)

    assert not report.passed
    assert report.changed_outside_rows == (7,)


def test_complete_pair_fails_closed_for_partial_or_contract_changed_output(tmp_path: Path):
    base, thong = _passing_pair()
    missing = dict(base)
    missing.pop(BASE_STREAMS[-1])

    partial = complete_sbbf_pair(missing, thong)
    semantic_change = complete_sbbf_pair(base, thong, semantic_contract_exact=False)
    index_change = complete_sbbf_pair(base, thong, index_contract_exact=False)
    topology_change = complete_sbbf_pair(base, thong, topology_contract_exact=False)

    for result in (partial, semantic_change, index_change, topology_change):
        assert result.status == "METHOD_SPECIFIC_EXHAUSTION"
        assert result.replacement_routes == 0
        assert result.candidate_positions is None
        report_path, candidate_path = write_offline_result(tmp_path, result)
        assert report_path.is_file()
        assert candidate_path is None
        assert not (tmp_path / "bard_sbbf_candidate_positions.npz").exists()


def test_complete_pair_emits_only_all_four_base_streams_plus_passing_thong(tmp_path: Path):
    base, thong = _passing_pair()

    result = complete_sbbf_pair(base, thong)
    report_path, candidate_path = write_offline_result(tmp_path, result)

    assert result.status == "PASS_OFFLINE_SBBF_PAIR"
    assert result.replacement_routes == 2
    assert result.position_digest is not None
    assert candidate_path is not None and candidate_path.is_file()
    assert report_path.is_file()
    with np.load(candidate_path, allow_pickle=False) as payload:
        assert set(payload.files) == {
            *(f"base::{name}" for name in BASE_STREAMS),
            f"thong::{THONG_STREAM}",
        }


def _load_hash_locked_legacy_reconstruction():
    try:
        verified = verify_evidence_inputs(load_local_configuration())
    except ConfigurationError as error:
        pytest.skip(f"hash-locked local Bard evidence unavailable: {error}")
    by_id = {item.input_id: item for item in verified}
    missing = LEGACY_INPUT_IDS - set(by_id)
    if missing:
        pytest.fail(f"missing hash-locked input IDs: {sorted(missing)}")
    package_root = by_id["legacy_bard_contracts_py"].path.parents[1]
    sys.path.insert(0, str(package_root))
    try:
        legacy = importlib.import_module("src.reconstruct_positions")
        contracts = importlib.import_module("src.bard_contracts")
    finally:
        sys.path.remove(str(package_root))
    return legacy, contracts, {
        input_id: item.actual_sha256
        for input_id, item in sorted(by_id.items())
    }


def _real_sbbf_inputs():
    legacy, contracts, input_hashes = _load_hash_locked_legacy_reconstruction()
    base_path = contracts.BARD_GLB_ROOT / "HUM_F_CLT_Bard_Dress_Base_KEL.source.glb"
    thong_path = contracts.BARD_GLB_ROOT / "HUM_F_CLT_Bard_Dress_Thong_KEL.source.glb"
    source_body = legacy.pose_body_to_rig(contracts.BODY_ROOT / "Body_BCB.glb", base_path)
    target_body = legacy.pose_body_to_rig(contracts.BODY_ROOT / "Body_SBBF.glb", base_path)
    base_inputs = {}
    for stream in legacy.mesh_streams(base_path):
        delta = legacy.smooth_delta_on_topology(
            legacy.cross_section_delta(source_body, target_body, stream["positions"]),
            stream["triangles"],
        )
        candidate = stream["positions"] + 0.5 * delta
        base_inputs[stream["mesh"]] = (stream["positions"], candidate, stream["triangles"])

    thong_source_body = legacy.pose_body_to_rig(contracts.BODY_ROOT / "Body_BCB.glb", thong_path)
    thong_target_body = legacy.pose_body_to_rig(contracts.BODY_ROOT / "Body_SBBF.glb", thong_path)
    thong_stream = legacy.mesh_streams(thong_path)[0]
    thong_delta = legacy.smooth_delta_on_topology(
        legacy.cross_section_delta(thong_source_body, thong_target_body, thong_stream["positions"]),
        thong_stream["triangles"],
    )
    thong_input = (
        thong_stream["positions"],
        thong_stream["positions"] + thong_delta,
        thong_stream["triangles"],
    )
    return base_inputs, thong_input, input_hashes


def test_real_hash_locked_alpha_floor_is_repaired_deterministically(tmp_path: Path):
    base_inputs, thong_input, input_hashes = _real_sbbf_inputs()
    sleeve_source, sleeve_candidate, sleeve_faces = base_inputs[SLEEVE_STREAM]
    retained = topology_metrics(sleeve_source, sleeve_candidate, sleeve_faces)

    assert retained.flipped_faces == 0
    assert retained.new_zero_area_faces == 0
    assert retained.below_area_floor == 1
    assert retained.minimum_area_ratio == 0.159049789992582

    run_results: list[CompletePairResult] = []
    for run_number in (1, 2):
        base_results = {
            name: solve_local_area_constrained_positions(*base_inputs[name])
            for name in BASE_STREAMS
        }
        thong_result = solve_local_area_constrained_positions(*thong_input)
        complete = complete_sbbf_pair(base_results, thong_result)
        run_results.append(complete)
        report_path, candidate_path = write_offline_result(
            tmp_path / f"run-{run_number}",
            complete,
            input_hashes=input_hashes,
        )
        assert report_path.is_file()
        assert candidate_path is not None and candidate_path.is_file()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["verified_input_sha256"] == input_hashes

    first, second = run_results
    assert first.status == second.status == "PASS_OFFLINE_SBBF_PAIR"
    assert first.position_digest == second.position_digest
    assert first.candidate_positions is not None
    assert second.candidate_positions is not None
    first_sleeve = first.candidate_positions["base"][SLEEVE_STREAM]
    second_sleeve = second.candidate_positions["base"][SLEEVE_STREAM]
    np.testing.assert_array_equal(first_sleeve, second_sleeve)
    sleeve_result = solve_local_area_constrained_positions(
        sleeve_source,
        sleeve_candidate,
        sleeve_faces,
    )
    assert sleeve_result.region.failing_face_indices == (10792,)
    assert sleeve_result.region.seed_vertex_indices == (6896, 6902, 6904)
    assert len(sleeve_result.region.movable_vertex_indices) == 11
    assert len(sleeve_result.region.affected_face_indices) == 21
    assert sleeve_result.post_metrics is not None
    assert sleeve_result.post_metrics.flipped_faces == 0
    assert sleeve_result.post_metrics.new_zero_area_faces == 0
    assert sleeve_result.post_metrics.below_area_floor == 0
    assert sleeve_result.outside_gate is not None and sleeve_result.outside_gate.passed
