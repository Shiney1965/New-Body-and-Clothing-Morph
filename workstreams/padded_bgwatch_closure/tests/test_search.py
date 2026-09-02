"""Deterministic exhaustive-search tests for the Padded position-only closure."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure.geometry import (
    ParsedColladaGeometry,
    ParsedGlbSurface,
    build_surface_constraints,
    derive_minimal_roi,
)
from workstreams.padded_bgwatch_closure.search import (
    SearchParameters,
    build_parameter_grid,
    run_position_only_search,
)
from workstreams.padded_bgwatch_closure.solver import (
    CandidateContract,
    CoverageContract,
    SyntheticCandidateContract,
)


EXPECTED_GATE_KEYS = {
    "passed",
    "production_passed",
    "status",
    "topology_identity_equal",
    "non_position_semantics_equal",
    "position_count_equal",
    "fixed_vertex_moves",
    "active_vertices_below_clearance",
    "active_surface_ambiguities",
    "moved_roi_vertices_below_clearance",
    "moved_roi_surface_ambiguities",
    "fixed_cohort_coverage_loss",
    "flipped_faces",
    "new_zero_area_faces",
    "faces_below_published_area",
    "faces_above_published_area",
    "faces_below_internal_area",
    "faces_above_internal_area",
    "faces_below_orientation_cosine",
    "minimum_area_ratio",
    "maximum_area_ratio",
    "minimum_orientation_cosine",
}


def _production_fixture(*, maximum_coverage_distance: float = 0.2):
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    source = ParsedColladaGeometry(
        positions=base,
        faces=faces,
        geometry_id="synthetic-production-contract",
        content_sha256="A" * 64,
        non_position_sha256="B" * 64,
        face_indices_sha256=hashlib.sha256(
            np.asarray(faces, dtype="<i8").tobytes(order="C")
        ).hexdigest().upper(),
    )
    body = ParsedGlbSurface(
        positions=np.array([[-2, -2, 0.1], [2, -2, 0.1], [0, 2, 0.1]], dtype=float),
        faces=np.array([[0, 1, 2]], dtype=int),
        vertex_normals=np.array([[0.0, 0.0, 1.0]] * 3),
    )
    roi = derive_minimal_roi(base, faces, active_ids=[0, 1, 2])
    constraints = build_surface_constraints(base, body, active_ids=[0, 1, 2])
    contract = CandidateContract(
        roi=roi,
        constraints=constraints,
        fixed_cohort=CoverageContract(
            points=np.array([[0.2, 0.2, 0.0]], dtype=float),
            normals=np.array([[0.0, 0.0, 1.0]], dtype=float),
            maximum_distance=maximum_coverage_distance,
        ),
    )
    return source, contract


def test_parameter_grid_is_the_exact_160_unique_cases_in_declared_order():
    """Catches adaptive expansion, omission, duplication, or parameter reordering."""
    grid = build_parameter_grid()

    expected = (
        SearchParameters(0.10, 0.0, 1),
        SearchParameters(0.10, 0.0, 2),
        SearchParameters(0.10, 0.0, 4),
        SearchParameters(0.10, 0.0, 8),
        SearchParameters(0.10, 0.1, 1),
        SearchParameters(0.10, 0.1, 2),
        SearchParameters(0.10, 0.1, 4),
        SearchParameters(0.10, 0.1, 8),
        SearchParameters(0.10, 0.25, 1),
        SearchParameters(0.10, 0.25, 2),
        SearchParameters(0.10, 0.25, 4),
        SearchParameters(0.10, 0.25, 8),
        SearchParameters(0.10, 0.5, 1),
        SearchParameters(0.10, 0.5, 2),
        SearchParameters(0.10, 0.5, 4),
        SearchParameters(0.10, 0.5, 8),
        SearchParameters(0.20, 0.0, 1),
        SearchParameters(0.20, 0.0, 2),
        SearchParameters(0.20, 0.0, 4),
        SearchParameters(0.20, 0.0, 8),
        SearchParameters(0.20, 0.1, 1),
        SearchParameters(0.20, 0.1, 2),
        SearchParameters(0.20, 0.1, 4),
        SearchParameters(0.20, 0.1, 8),
        SearchParameters(0.20, 0.25, 1),
        SearchParameters(0.20, 0.25, 2),
        SearchParameters(0.20, 0.25, 4),
        SearchParameters(0.20, 0.25, 8),
        SearchParameters(0.20, 0.5, 1),
        SearchParameters(0.20, 0.5, 2),
        SearchParameters(0.20, 0.5, 4),
        SearchParameters(0.20, 0.5, 8),
        SearchParameters(0.30, 0.0, 1),
        SearchParameters(0.30, 0.0, 2),
        SearchParameters(0.30, 0.0, 4),
        SearchParameters(0.30, 0.0, 8),
        SearchParameters(0.30, 0.1, 1),
        SearchParameters(0.30, 0.1, 2),
        SearchParameters(0.30, 0.1, 4),
        SearchParameters(0.30, 0.1, 8),
        SearchParameters(0.30, 0.25, 1),
        SearchParameters(0.30, 0.25, 2),
        SearchParameters(0.30, 0.25, 4),
        SearchParameters(0.30, 0.25, 8),
        SearchParameters(0.30, 0.5, 1),
        SearchParameters(0.30, 0.5, 2),
        SearchParameters(0.30, 0.5, 4),
        SearchParameters(0.30, 0.5, 8),
        SearchParameters(0.40, 0.0, 1),
        SearchParameters(0.40, 0.0, 2),
        SearchParameters(0.40, 0.0, 4),
        SearchParameters(0.40, 0.0, 8),
        SearchParameters(0.40, 0.1, 1),
        SearchParameters(0.40, 0.1, 2),
        SearchParameters(0.40, 0.1, 4),
        SearchParameters(0.40, 0.1, 8),
        SearchParameters(0.40, 0.25, 1),
        SearchParameters(0.40, 0.25, 2),
        SearchParameters(0.40, 0.25, 4),
        SearchParameters(0.40, 0.25, 8),
        SearchParameters(0.40, 0.5, 1),
        SearchParameters(0.40, 0.5, 2),
        SearchParameters(0.40, 0.5, 4),
        SearchParameters(0.40, 0.5, 8),
        SearchParameters(0.50, 0.0, 1),
        SearchParameters(0.50, 0.0, 2),
        SearchParameters(0.50, 0.0, 4),
        SearchParameters(0.50, 0.0, 8),
        SearchParameters(0.50, 0.1, 1),
        SearchParameters(0.50, 0.1, 2),
        SearchParameters(0.50, 0.1, 4),
        SearchParameters(0.50, 0.1, 8),
        SearchParameters(0.50, 0.25, 1),
        SearchParameters(0.50, 0.25, 2),
        SearchParameters(0.50, 0.25, 4),
        SearchParameters(0.50, 0.25, 8),
        SearchParameters(0.50, 0.5, 1),
        SearchParameters(0.50, 0.5, 2),
        SearchParameters(0.50, 0.5, 4),
        SearchParameters(0.50, 0.5, 8),
        SearchParameters(0.60, 0.0, 1),
        SearchParameters(0.60, 0.0, 2),
        SearchParameters(0.60, 0.0, 4),
        SearchParameters(0.60, 0.0, 8),
        SearchParameters(0.60, 0.1, 1),
        SearchParameters(0.60, 0.1, 2),
        SearchParameters(0.60, 0.1, 4),
        SearchParameters(0.60, 0.1, 8),
        SearchParameters(0.60, 0.25, 1),
        SearchParameters(0.60, 0.25, 2),
        SearchParameters(0.60, 0.25, 4),
        SearchParameters(0.60, 0.25, 8),
        SearchParameters(0.60, 0.5, 1),
        SearchParameters(0.60, 0.5, 2),
        SearchParameters(0.60, 0.5, 4),
        SearchParameters(0.60, 0.5, 8),
        SearchParameters(0.70, 0.0, 1),
        SearchParameters(0.70, 0.0, 2),
        SearchParameters(0.70, 0.0, 4),
        SearchParameters(0.70, 0.0, 8),
        SearchParameters(0.70, 0.1, 1),
        SearchParameters(0.70, 0.1, 2),
        SearchParameters(0.70, 0.1, 4),
        SearchParameters(0.70, 0.1, 8),
        SearchParameters(0.70, 0.25, 1),
        SearchParameters(0.70, 0.25, 2),
        SearchParameters(0.70, 0.25, 4),
        SearchParameters(0.70, 0.25, 8),
        SearchParameters(0.70, 0.5, 1),
        SearchParameters(0.70, 0.5, 2),
        SearchParameters(0.70, 0.5, 4),
        SearchParameters(0.70, 0.5, 8),
        SearchParameters(0.80, 0.0, 1),
        SearchParameters(0.80, 0.0, 2),
        SearchParameters(0.80, 0.0, 4),
        SearchParameters(0.80, 0.0, 8),
        SearchParameters(0.80, 0.1, 1),
        SearchParameters(0.80, 0.1, 2),
        SearchParameters(0.80, 0.1, 4),
        SearchParameters(0.80, 0.1, 8),
        SearchParameters(0.80, 0.25, 1),
        SearchParameters(0.80, 0.25, 2),
        SearchParameters(0.80, 0.25, 4),
        SearchParameters(0.80, 0.25, 8),
        SearchParameters(0.80, 0.5, 1),
        SearchParameters(0.80, 0.5, 2),
        SearchParameters(0.80, 0.5, 4),
        SearchParameters(0.80, 0.5, 8),
        SearchParameters(0.90, 0.0, 1),
        SearchParameters(0.90, 0.0, 2),
        SearchParameters(0.90, 0.0, 4),
        SearchParameters(0.90, 0.0, 8),
        SearchParameters(0.90, 0.1, 1),
        SearchParameters(0.90, 0.1, 2),
        SearchParameters(0.90, 0.1, 4),
        SearchParameters(0.90, 0.1, 8),
        SearchParameters(0.90, 0.25, 1),
        SearchParameters(0.90, 0.25, 2),
        SearchParameters(0.90, 0.25, 4),
        SearchParameters(0.90, 0.25, 8),
        SearchParameters(0.90, 0.5, 1),
        SearchParameters(0.90, 0.5, 2),
        SearchParameters(0.90, 0.5, 4),
        SearchParameters(0.90, 0.5, 8),
        SearchParameters(1.00, 0.0, 1),
        SearchParameters(1.00, 0.0, 2),
        SearchParameters(1.00, 0.0, 4),
        SearchParameters(1.00, 0.0, 8),
        SearchParameters(1.00, 0.1, 1),
        SearchParameters(1.00, 0.1, 2),
        SearchParameters(1.00, 0.1, 4),
        SearchParameters(1.00, 0.1, 8),
        SearchParameters(1.00, 0.25, 1),
        SearchParameters(1.00, 0.25, 2),
        SearchParameters(1.00, 0.25, 4),
        SearchParameters(1.00, 0.25, 8),
        SearchParameters(1.00, 0.5, 1),
        SearchParameters(1.00, 0.5, 2),
        SearchParameters(1.00, 0.5, 4),
        SearchParameters(1.00, 0.5, 8),
    )
    assert grid == expected
    assert len(grid) == 160
    assert len(set(grid)) == 160


def test_search_serializes_all_160_records_and_every_failure_has_complete_gates_and_reasons():
    """Catches failed cases being omitted or serialized without their gate evidence."""
    source, contract = _production_fixture()

    result = run_position_only_search(source, contract)
    payload = json.loads(result.json_bytes)

    assert payload["schema_version"] == 1
    assert payload["record_count"] == 160
    assert len(payload["records"]) == 160
    assert [record["index"] for record in payload["records"]] == list(range(160))
    assert len({
        (
            record["parameters"]["scale"],
            record["parameters"]["fairness"],
            record["parameters"]["iterations"],
        )
        for record in payload["records"]
    }) == 160
    failures = [record for record in payload["records"] if not record["gates"]["production_passed"]]
    assert failures
    assert all(set(record["gates"]) == EXPECTED_GATE_KEYS for record in failures)
    assert all(record["failure_reasons"] for record in failures)
    assert "ACTIVE_CLEARANCE_NOT_MET" in failures[0]["failure_reasons"]
    assert all(len(record["candidate"]["position_sha256"]) == 64 for record in payload["records"])


def test_identical_runs_have_byte_identical_json_and_selected_position_hash():
    """Catches nondeterministic record, selection, float, or hashing order."""
    source, contract = _production_fixture()

    first = run_position_only_search(source, contract)
    second = run_position_only_search(source, contract)

    assert first.status == "OFFLINE_POSITION_ONLY_CANDIDATE"
    assert first.selected_record_index == 144
    assert first.selected_candidate is not None
    assert first.json_bytes == second.json_bytes
    assert first.selected_position_sha256 == second.selected_position_sha256
    assert first.selected_position_sha256 == hashlib.sha256(
        np.asarray(first.selected_candidate.positions, dtype="<f8").tobytes(order="C")
    ).hexdigest().upper()


def test_zero_passing_cases_emit_terminal_status_without_weakening_or_omitting_cases():
    """Catches a zero-pass run forcing a candidate or stopping before all cases finish."""
    source, contract = _production_fixture(maximum_coverage_distance=0.0001)

    result = run_position_only_search(source, contract)
    payload = json.loads(result.json_bytes)

    assert result.status == "POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY"
    assert result.selected_candidate is None
    assert result.selected_record_index is None
    assert result.selected_position_sha256 is None
    assert payload["passing_count"] == 0
    assert payload["record_count"] == 160
    assert len(payload["records"]) == 160
    assert all(record["failure_reasons"] for record in payload["records"])


def test_search_rejects_synthetic_contract_before_any_case_can_be_selected():
    """Catches synthetic gate success being promoted to a production candidate."""
    source, production_contract = _production_fixture()
    synthetic_contract = SyntheticCandidateContract(
        roi=production_contract.roi,
        constraints=production_contract.constraints,
        fixed_cohort=production_contract.fixed_cohort,
    )

    with pytest.raises(TypeError, match="PRODUCTION_CANDIDATE_CONTRACT_REQUIRED"):
        run_position_only_search(source, synthetic_contract)


def test_search_evaluates_every_case_only_after_caller_roundtrip_normalization():
    """Catches real integration evaluating in-memory coordinates before DAE readback."""
    source, contract = _production_fixture(maximum_coverage_distance=0.0001)
    calls = []

    def roundtrip(candidate):
        calls.append(candidate.accepted_step_scales)
        return candidate

    result = run_position_only_search(source, contract, candidate_roundtrip=roundtrip)

    assert len(calls) == 160
    assert result.status == "POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY"
