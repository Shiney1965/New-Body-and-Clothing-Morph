from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from workstreams.bard_authority_closure.bard_landmark_cage import (
    BASE_STREAMS,
    COMPLETE_PAIR_PASS,
    SEARCH_ALPHAS,
    THONG_STREAM,
    UNFIXABLE,
    CageStreamInput,
    CompletePairResult,
    LandmarkContractError,
    StreamCageResult,
    _complete_mode_candidate,
    build_complete_mode_candidate,
    parse_component_landmark_contract,
    solve_harmonic_cage_displacement,
    solve_stream_landmark_cage,
    validate_common_frame_landmarks,
    write_offline_result,
)
from workstreams.bard_authority_closure.bard_sbbf_repair import (
    StreamIdentity,
    index_topology_digest,
    topology_metrics,
)
from workstreams.bard_authority_closure.contracts import load_bard_contract


SHA_A = "A" * 64
SHA_B = "B" * 64
SHA_C = "C" * 64
SHA_D = "D" * 64
BASE_STREAM = BASE_STREAMS[0]


def _boundary_indices(shape=(3, 3, 3)):
    return [
        [i, j, k]
        for i in range(shape[0])
        for j in range(shape[1])
        for k in range(shape[2])
        if i in {0, shape[0] - 1}
        or j in {0, shape[1] - 1}
        or k in {0, shape[2] - 1}
    ]


def _stream_payload(
    *,
    component="base",
    stream_id=BASE_STREAM,
    displacement=lambda i, j, k: [0.1 + 0.01 * i, 0.02 * j, -0.01 * k],
):
    anchors = []
    for anchor_id, (i, j, k) in enumerate(_boundary_indices()):
        source_point = [float(i), float(j), float(k)]
        delta = displacement(i, j, k)
        anchors.append(
            {
                "anchor_id": f"{stream_id}:{i}:{j}:{k}",
                "component": component,
                "stream_id": stream_id,
                "cage_index": [i, j, k],
                "source_body_vertex": anchor_id,
                "target_body_vertex": 1000 + anchor_id,
                "source_point": source_point,
                "target_point": [source_point[n] + float(delta[n]) for n in range(3)],
            }
        )
    return {
        "stream_id": stream_id,
        "vertex_count": 4,
        "position_shape": [4, 3],
        "index_topology_sha256": SHA_C,
        "non_position_semantic_sha256": SHA_D,
        "cage_shape": [3, 3, 3],
        "cage_min": [0.0, 0.0, 0.0],
        "cage_max": [2.0, 2.0, 2.0],
        "anchors": anchors,
    }


def _payload(*, component="base", streams=None):
    if streams is None:
        streams = [_stream_payload(component=component)]
    return {
        "schema": "bard_component_landmark_cage_v1",
        "schema_version": 1,
        "mode": "vanilla",
        "component": component,
        "common_frame_report_sha256": SHA_A,
        "source_body_sha256": SHA_B,
        "target_body_sha256": SHA_C,
        "source_component_sha256": SHA_D,
        "search_alphas": list(SEARCH_ALPHAS),
        "streams": streams,
    }


def _contract(*, displacement=lambda i, j, k: [0.1, 0.0, 0.0], component="base", stream_id=BASE_STREAM):
    return parse_component_landmark_contract(
        _payload(
            component=component,
            streams=[
                _stream_payload(
                    component=component,
                    stream_id=stream_id,
                    displacement=displacement,
                )
            ],
        ),
        component,
        "vanilla",
    ).streams[0]


def _identity(stream_id=BASE_STREAM, shape=(4, 3), topology=SHA_C):
    return StreamIdentity(
        stream_id=stream_id,
        verified_source_path=str(Path("C:/evidence/source.glb")),
        verified_source_sha256=SHA_D,
        position_shape=shape,
        index_topology_sha256=topology,
        non_position_semantic_sha256=SHA_D,
    )


def _triangle_input(*, stream_id=BASE_STREAM, displacement=lambda i, j, k: [0.1, 0.0, 0.0]):
    component = "thong" if stream_id == THONG_STREAM else "base"
    positions = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.5, 0.5, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    identity = _identity(stream_id, topology=index_topology_digest(faces))
    stream = _contract(
        displacement=displacement,
        component=component,
        stream_id=stream_id,
    )
    stream = replace(
        stream,
        index_topology_sha256=identity.index_topology_sha256,
        non_position_semantic_sha256=identity.non_position_semantic_sha256,
    )
    return CageStreamInput(
        component=component,
        stream_identity=identity,
        source_positions=positions,
        faces=faces,
        landmark_stream=stream,
    )


def test_current_vanilla_failure_counts_are_pinned_to_retained_evidence():
    contract = load_bard_contract()
    actual = {
        name: (
            contract.failure("vanilla", name).flips,
            contract.failure("vanilla", name).new_zero_area,
            contract.failure("vanilla", name).below_area_floor,
            contract.failure("vanilla", name).minimum_area_ratio,
        )
        for name in ("BodyTop", "Footwear", "Pants", "Sleeves", "Thong")
    }
    assert actual == {
        "BodyTop": (0, 0, 4, 0.20319298429926863),
        "Footwear": (39, 0, 4, 0.1655718748294266),
        "Pants": (1, 0, 1, 0.22793790846010978),
        "Sleeves": (179, 0, 59, 0.03589030264608348),
        "Thong": (181, 0, 20, 0.05640343759001028),
    }


def test_landmark_contract_requires_exact_boundary_anchor_set_and_hash_locks():
    contract = parse_component_landmark_contract(_payload(), "base", "vanilla")

    assert contract.component == "base"
    assert contract.mode == "vanilla"
    assert contract.common_frame_report_sha256 == SHA_A
    assert contract.search_alphas == SEARCH_ALPHAS
    assert len(contract.streams) == 1
    assert len(contract.streams[0].anchors) == 26
    assert tuple(anchor.cage_index for anchor in contract.streams[0].anchors) == tuple(
        tuple(value) for value in _boundary_indices()
    )


def test_compact_explicit_anchor_columns_expand_to_the_same_contract():
    payload = _payload()
    stream = payload["streams"][0]
    anchors = stream["anchors"]
    stream["anchors"] = {
        "cage_indices": [value["cage_index"] for value in anchors],
        "source_body_vertices": [value["source_body_vertex"] for value in anchors],
        "target_body_vertices": [value["target_body_vertex"] for value in anchors],
        "source_points": [value["source_point"] for value in anchors],
        "target_points": [value["target_point"] for value in anchors],
    }

    contract = parse_component_landmark_contract(payload, "base", "vanilla")

    assert len(contract.streams[0].anchors) == 26
    assert contract.streams[0].anchors[0].anchor_id == f"{BASE_STREAM}:0:0:0"
    assert contract.streams[0].anchors[-1].cage_index == (2, 2, 2)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "LANDMARK_BOUNDARY_ANCHOR_MISSING"),
        ("duplicate", "LANDMARK_CAGE_INDEX_DUPLICATE"),
        ("out_of_component", "LANDMARK_ANCHOR_OUT_OF_COMPONENT"),
    ],
)
def test_landmark_contract_rejects_missing_duplicate_and_out_of_component_anchors(
    mutation: str,
    message: str,
):
    payload = _payload()
    anchors = payload["streams"][0]["anchors"]
    if mutation == "missing":
        anchors.pop()
    elif mutation == "duplicate":
        anchors[-1]["cage_index"] = list(anchors[0]["cage_index"])
    else:
        anchors[-1]["component"] = "thong"

    with pytest.raises(LandmarkContractError, match=message):
        parse_component_landmark_contract(payload, "base", "vanilla")


def test_landmark_contract_rejects_duplicate_body_landmarks():
    payload = _payload()
    anchors = payload["streams"][0]["anchors"]
    anchors[-1]["source_body_vertex"] = anchors[0]["source_body_vertex"]

    with pytest.raises(LandmarkContractError, match="LANDMARK_SOURCE_BODY_VERTEX_DUPLICATE"):
        parse_component_landmark_contract(payload, "base", "vanilla")


def test_harmonic_cage_reproduces_affine_boundary_field_without_mesh_smoothing():
    stream = _contract(displacement=lambda i, j, k: [0.5 * i, -0.25 * j, 0.125 * k])
    positions = np.array(
        [[0.0, 0.0, 0.0], [2.0, 2.0, 2.0], [1.0, 1.0, 1.0], [0.5, 1.5, 1.0]],
        dtype=np.float64,
    )

    displacement = solve_harmonic_cage_displacement(positions, stream)

    np.testing.assert_allclose(
        displacement,
        np.array(
            [[0.0, 0.0, 0.0], [1.0, -0.5, 0.25], [0.5, -0.25, 0.125], [0.25, -0.375, 0.125]],
            dtype=np.float64,
        ),
        rtol=0.0,
        atol=1e-12,
    )


def test_harmonic_cage_rejects_nonfinite_and_outside_positions():
    stream = _contract()
    with pytest.raises(ValueError, match="CAGE_POSITION_NONFINITE"):
        solve_harmonic_cage_displacement(np.array([[np.nan, 0.0, 0.0]]), stream)
    with pytest.raises(ValueError, match="CAGE_POSITION_OUTSIDE_DECLARED_BOUNDS"):
        solve_harmonic_cage_displacement(np.array([[2.1, 0.0, 0.0]]), stream)


def test_landmark_points_are_bound_to_exact_common_frame_rows():
    stream = _contract()
    source_body = np.zeros((26, 3), dtype=np.float64)
    target_body = np.zeros((1026, 3), dtype=np.float64)
    for anchor in stream.anchors:
        source_body[anchor.source_body_vertex] = anchor.source_point
        target_body[anchor.target_body_vertex] = anchor.target_point

    validate_common_frame_landmarks(stream, source_body, target_body)

    source_body[stream.anchors[0].source_body_vertex, 0] += 1e-12
    with pytest.raises(ValueError, match="LANDMARK_SOURCE_POINT_MISMATCH"):
        validate_common_frame_landmarks(stream, source_body, target_body)


def test_stream_solver_uses_only_fixed_schedule_and_can_pass_at_exact_half_floor():
    stream_input = _triangle_input(displacement=lambda i, j, k: [-1.5 * i, 0.0, 0.0])

    result = solve_stream_landmark_cage(stream_input)

    assert result.status == "PASS_STREAM_CAGE"
    assert result.selected_alpha == 0.5
    assert result.attempted_alphas == SEARCH_ALPHAS
    assert result.post_metrics is not None and result.post_metrics.passed
    assert result.post_metrics.minimum_area_ratio == 0.25
    assert result.positions is not None and result.positions.dtype == np.dtype("<f4")


def test_stream_solver_rejects_topology_or_semantic_identity_mismatch():
    valid = _triangle_input()
    bad_topology = replace(
        valid,
        stream_identity=replace(valid.stream_identity, index_topology_sha256=SHA_A),
    )
    bad_semantics = replace(
        valid,
        stream_identity=replace(valid.stream_identity, non_position_semantic_sha256=SHA_A),
    )

    with pytest.raises(ValueError, match="CAGE_INDEX_TOPOLOGY_MISMATCH"):
        solve_stream_landmark_cage(bad_topology)
    with pytest.raises(ValueError, match="CAGE_NON_POSITION_SEMANTIC_MISMATCH"):
        solve_stream_landmark_cage(bad_semantics)


def _passing_result(stream_id: str) -> tuple[CageStreamInput, StreamCageResult]:
    stream_input = _triangle_input(stream_id=stream_id)
    return stream_input, solve_stream_landmark_cage(stream_input)


def _passing_pair():
    base_inputs = {}
    base_results = {}
    for stream_id in BASE_STREAMS:
        stream_input, result = _passing_result(stream_id)
        base_inputs[stream_id] = stream_input
        base_results[stream_id] = result
    thong_input, thong_result = _passing_result(THONG_STREAM)
    thong_input = replace(thong_input, component="thong")
    return base_inputs, base_results, thong_input, thong_result


def test_complete_mode_is_atomic_and_emits_zero_routes_on_one_failed_stream():
    base_inputs, base_results, thong_input, thong_result = _passing_pair()
    failed = replace(
        base_results[BASE_STREAMS[-1]],
        status="CAGE_SEARCH_EXHAUSTED",
        positions=None,
        selected_alpha=None,
        post_metrics=None,
        position_sha256=None,
        exhaustion_reason="NO_FIXED_ALPHA_PASSED",
    )
    base_results[BASE_STREAMS[-1]] = failed

    result = _complete_mode_candidate(
        "vanilla",
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={"common_frame_report": SHA_A},
        landmark_contract_sha256=SHA_B,
    )

    assert result.status == UNFIXABLE
    assert result.replacement_routes == 0
    assert result.candidate_positions is None
    assert result.position_digest is None
    assert "HUM_F_ARM_Bard_Sleeves_Mesh" in result.exhaustion_reason


def test_complete_mode_requires_exact_four_base_streams_plus_thong():
    base_inputs, base_results, thong_input, thong_result = _passing_pair()

    result = _complete_mode_candidate(
        "vanilla",
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={"common_frame_report": SHA_A},
        landmark_contract_sha256=SHA_B,
    )

    assert result.status == COMPLETE_PAIR_PASS
    assert result.replacement_routes == 2
    assert result.candidate_positions is not None
    assert tuple(result.candidate_positions["base"]) == BASE_STREAMS
    assert tuple(result.candidate_positions["thong"]) == (THONG_STREAM,)
    assert result.position_digest is not None
    assert result.protected_bcb_replacement_routes == 0


def test_writer_emits_candidate_only_for_revalidated_atomic_pass(tmp_path: Path):
    base_inputs, base_results, thong_input, thong_result = _passing_pair()
    passing = _complete_mode_candidate(
        "vanilla",
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={"common_frame_report": SHA_A},
        landmark_contract_sha256=SHA_B,
    )

    report_path, candidate_path = write_offline_result(tmp_path / "pass", passing)

    assert report_path.is_file()
    assert candidate_path is not None and candidate_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == COMPLETE_PAIR_PASS
    assert report["protected_bcb_replacement_routes"] == 0
    assert report["search_alphas"] == list(SEARCH_ALPHAS)
    with np.load(candidate_path, allow_pickle=False) as archive:
        assert set(archive.files) == {
            *(f"base::{stream}" for stream in BASE_STREAMS),
            f"thong::{THONG_STREAM}",
        }


def test_writer_never_serializes_partial_positions_for_exhaustion(tmp_path: Path):
    base_inputs, base_results, thong_input, thong_result = _passing_pair()
    base_results.pop(BASE_STREAMS[-1])
    exhausted = _complete_mode_candidate(
        "vanilla",
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={"common_frame_report": SHA_A},
        landmark_contract_sha256=SHA_B,
    )

    report_path, candidate_path = write_offline_result(tmp_path / "exhausted", exhausted)

    assert report_path.is_file()
    assert candidate_path is None
    assert not (report_path.parent / "bard_vanilla_landmark_cage_positions.npz").exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == UNFIXABLE
    assert report["replacement_routes"] == 0


def test_writer_revalidates_result_and_refuses_prior_artifacts(tmp_path: Path):
    base_inputs, base_results, thong_input, thong_result = _passing_pair()
    passing = _complete_mode_candidate(
        "vanilla",
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={"common_frame_report": SHA_A},
        landmark_contract_sha256=SHA_B,
    )
    forged = replace(passing, protected_bcb_replacement_routes=1)

    with pytest.raises(ValueError, match="OFFLINE_RESULT_NOT_EMITTABLE"):
        write_offline_result(tmp_path / "forged", forged)

    write_offline_result(tmp_path / "once", passing)
    with pytest.raises(FileExistsError, match="OFFLINE_OUTPUT_ALREADY_EXISTS"):
        write_offline_result(tmp_path / "once", passing)


def test_bcb_mode_is_not_a_candidate_route():
    with pytest.raises(ValueError, match="BARD_BCB_PROTECTED_NO_REPLACEMENT"):
        _complete_mode_candidate(
            "bcb",
            {},
            {},
            None,
            None,
            verified_input_sha256={},
            landmark_contract_sha256=SHA_A,
        )


def test_real_hash_locked_vanilla_build_is_terminal_and_byte_deterministic(tmp_path: Path):
    first = build_complete_mode_candidate("vanilla")
    second = build_complete_mode_candidate("vanilla")

    assert first.status == second.status
    assert first.status in {COMPLETE_PAIR_PASS, UNFIXABLE}
    assert first.protected_bcb_replacement_routes == second.protected_bcb_replacement_routes == 0
    assert first.landmark_contract_sha256 == second.landmark_contract_sha256 == (
        "422B074B930393E3572EE6D6165A94775BD9054F94823A32C52D548F4A3311E5"
    )
    assert first.verified_input_sha256["legacy_common_frame_report"] == (
        "DCA5CAC09F401B44DBAB3437B961FE4F0FFADF1A432C6E7D11722F9F400C41AB"
    )
    assert first.verified_input_sha256["body_vanilla_glb"] == (
        "F5922A82C60033E9D37725DE605B919A05E782E1250AC3398A519E46CC894704"
    )
    assert tuple(first.base_results) == tuple(second.base_results) == BASE_STREAMS
    for stream_id in BASE_STREAMS:
        assert first.base_results[stream_id].attempt_metrics == second.base_results[stream_id].attempt_metrics
        assert first.base_results[stream_id].cage_displacement_sha256 == (
            second.base_results[stream_id].cage_displacement_sha256
        )
    assert first.thong_result is not None and second.thong_result is not None
    assert first.thong_result.attempt_metrics == second.thong_result.attempt_metrics

    first_report, first_candidate = write_offline_result(tmp_path / "run-1", first)
    second_report, second_candidate = write_offline_result(tmp_path / "run-2", second)
    assert first_report.read_bytes() == second_report.read_bytes()
    assert (first_candidate is None) == (second_candidate is None)
    if first_candidate is not None:
        assert second_candidate is not None
        assert first_candidate.read_bytes() == second_candidate.read_bytes()

    forged_hashes = dict(first.verified_input_sha256)
    forged_hashes["legacy_common_frame_report"] = SHA_A
    with pytest.raises(ValueError, match="OFFLINE_RESULT_INPUT_HASH_MISMATCH"):
        write_offline_result(
            tmp_path / "forged-real-hash",
            replace(first, verified_input_sha256=forged_hashes),
        )


def test_production_writer_rejects_deleted_required_input_id(tmp_path: Path):
    result = build_complete_mode_candidate("vanilla")
    forged_hashes = dict(result.verified_input_sha256)
    forged_hashes.pop("legacy_common_frame_report")
    forged = replace(result, verified_input_sha256=forged_hashes)
    output = tmp_path / "deleted-production-id"

    with pytest.raises(ValueError, match="OFFLINE_RESULT_INPUT_ID_SET_MISMATCH"):
        write_offline_result(output, forged)

    assert not output.exists()


def test_production_writer_revalidates_canonical_landmark_digest(tmp_path: Path):
    result = build_complete_mode_candidate("vanilla")
    output = tmp_path / "forged-production-landmark-digest"

    with pytest.raises(ValueError, match="OFFLINE_RESULT_LANDMARK_HASH_MISMATCH"):
        write_offline_result(
            output,
            replace(result, landmark_contract_sha256=SHA_A),
        )

    assert not output.exists()


def test_synthetic_writer_rejects_production_input_id(tmp_path: Path):
    base_inputs, base_results, thong_input, thong_result = _passing_pair()
    synthetic = _complete_mode_candidate(
        "vanilla",
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={"legacy_common_frame_report": SHA_A},
        landmark_contract_sha256=SHA_B,
    )
    output = tmp_path / "synthetic-with-production-input"

    with pytest.raises(ValueError, match="OFFLINE_RESULT_PROVENANCE_MISMATCH"):
        write_offline_result(output, synthetic)

    assert not output.exists()
