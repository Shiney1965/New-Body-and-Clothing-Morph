"""Deterministic exhaustive search over the fixed position-only parameter grid."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np

from .geometry import ParsedColladaGeometry
from .solver import (
    Candidate,
    CandidateContract,
    GateReport,
    evaluate_candidate,
    solve_coherent_field,
)


OFFLINE_CANDIDATE = "OFFLINE_POSITION_ONLY_CANDIDATE"
POSITION_ONLY_UNFIXABLE = "POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY"

SCALES = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
FAIRNESS_WEIGHTS = (0.0, 0.1, 0.25, 0.5)
ITERATION_COUNTS = (1, 2, 4, 8)


@dataclass(frozen=True, order=True)
class SearchParameters:
    """One exact case in the declared 10 x 4 x 4 grid."""

    scale: float
    fairness: float
    iterations: int


def build_parameter_grid() -> tuple[SearchParameters, ...]:
    """Return all 160 cases in fixed scale/fairness/iteration order."""
    grid = tuple(
        SearchParameters(scale, fairness, iterations)
        for scale in SCALES
        for fairness in FAIRNESS_WEIGHTS
        for iterations in ITERATION_COUNTS
    )
    if len(grid) != 160 or len(set(grid)) != 160:
        raise RuntimeError("POSITION_ONLY_PARAMETER_GRID_INVALID")
    return grid


@dataclass(frozen=True)
class SearchRecord:
    """Complete evidence for one evaluated grid case."""

    index: int
    parameters: SearchParameters
    candidate_status: str
    candidate_position_sha256: str
    moved_vertex_count: int
    source_position_count: int
    source_face_indices_sha256: str
    source_non_position_sha256: str | None
    accepted_step_scales: tuple[float, ...]
    rejected_iteration_count: int
    gates: GateReport
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "parameters": asdict(self.parameters),
            "candidate": {
                "status": self.candidate_status,
                "position_sha256": self.candidate_position_sha256,
                "moved_vertex_count": self.moved_vertex_count,
                "source_position_count": self.source_position_count,
                "source_face_indices_sha256": self.source_face_indices_sha256,
                "source_non_position_sha256": self.source_non_position_sha256,
                "accepted_step_scales": list(self.accepted_step_scales),
                "rejected_iteration_count": self.rejected_iteration_count,
            },
            "gates": asdict(self.gates),
            "failure_reasons": list(self.failure_reasons),
        }


@dataclass(frozen=True)
class SearchResult:
    """Exhaustive evidence plus the first production pass in stable grid order."""

    status: str
    records: tuple[SearchRecord, ...]
    passing_count: int
    selected_record_index: int | None
    selected_position_sha256: str | None
    selected_candidate: Candidate | None
    json_bytes: bytes


def _position_sha256(candidate: Candidate) -> str:
    canonical = np.asarray(candidate.positions, dtype="<f8")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest().upper()


def _failure_reasons(candidate: Candidate, report: GateReport) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.status != "CANDIDATE":
        reasons.append(f"CANDIDATE_STATUS_{candidate.status}")
    if not report.topology_identity_equal:
        reasons.append("TOPOLOGY_IDENTITY_MISMATCH")
    if not report.non_position_semantics_equal:
        reasons.append("NON_POSITION_SEMANTICS_MISMATCH")
    if not report.position_count_equal:
        reasons.append("POSITION_COUNT_MISMATCH")
    if report.fixed_vertex_moves:
        reasons.append("FIXED_VERTEX_MOVES")
    if report.active_surface_ambiguities:
        reasons.append("ACTIVE_SURFACE_AMBIGUITY")
    if report.active_vertices_below_clearance:
        reasons.append("ACTIVE_CLEARANCE_NOT_MET")
    if report.fixed_cohort_coverage_loss:
        reasons.append("FIXED_COHORT_COVERAGE_LOSS")
    if report.flipped_faces:
        reasons.append("FLIPPED_FACES")
    if report.new_zero_area_faces:
        reasons.append("NEW_ZERO_AREA_FACES")
    if report.faces_below_published_area:
        reasons.append("PUBLISHED_MINIMUM_AREA_RATIO_FAILED")
    if report.faces_above_published_area:
        reasons.append("PUBLISHED_MAXIMUM_AREA_RATIO_FAILED")
    if report.faces_below_internal_area:
        reasons.append("INTERNAL_MINIMUM_AREA_RATIO_FAILED")
    if report.faces_above_internal_area:
        reasons.append("INTERNAL_MAXIMUM_AREA_RATIO_FAILED")
    if report.faces_below_orientation_cosine:
        reasons.append("INTERNAL_ORIENTATION_COSINE_FAILED")
    if not report.production_passed and not reasons:
        reasons.append("PRODUCTION_PASS_NOT_ESTABLISHED")
    return tuple(reasons)


def _serialize_result(
    status: str,
    records: tuple[SearchRecord, ...],
    passing_count: int,
    selected_record_index: int | None,
    selected_position_sha256: str | None,
) -> bytes:
    payload = {
        "schema_version": 1,
        "status": status,
        "record_count": len(records),
        "passing_count": passing_count,
        "selected_record_index": selected_record_index,
        "selected_position_sha256": selected_position_sha256,
        "records": [record.to_dict() for record in records],
    }
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def run_position_only_search(
    source: ParsedColladaGeometry,
    contract: CandidateContract,
) -> SearchResult:
    """Evaluate every fixed case and select the first production pass by grid order."""
    if not isinstance(source, ParsedColladaGeometry):
        raise TypeError("PRODUCTION_PARSED_COLLADA_SOURCE_REQUIRED")
    if type(contract) is not CandidateContract:
        raise TypeError("PRODUCTION_CANDIDATE_CONTRACT_REQUIRED")

    records: list[SearchRecord] = []
    selected_candidate: Candidate | None = None
    selected_record_index: int | None = None
    selected_position_sha256: str | None = None
    passing_count = 0

    for index, parameters in enumerate(build_parameter_grid()):
        candidate = solve_coherent_field(
            source,
            source.faces,
            contract.roi,
            contract.constraints,
            scale=parameters.scale,
            fairness=parameters.fairness,
            iterations=parameters.iterations,
        )
        gates = evaluate_candidate(source, candidate, contract)
        position_sha256 = _position_sha256(candidate)
        reasons = _failure_reasons(candidate, gates)
        records.append(SearchRecord(
            index=index,
            parameters=parameters,
            candidate_status=candidate.status,
            candidate_position_sha256=position_sha256,
            moved_vertex_count=candidate.moved_vertex_count,
            source_position_count=candidate.source_position_count,
            source_face_indices_sha256=candidate.source_face_indices_sha256,
            source_non_position_sha256=candidate.source_non_position_sha256,
            accepted_step_scales=candidate.accepted_step_scales,
            rejected_iteration_count=candidate.rejected_iteration_count,
            gates=gates,
            failure_reasons=reasons,
        ))
        if gates.production_passed:
            passing_count += 1
            if selected_candidate is None:
                selected_candidate = candidate
                selected_record_index = index
                selected_position_sha256 = position_sha256

    frozen_records = tuple(records)
    if len(frozen_records) != 160:
        raise RuntimeError("POSITION_ONLY_SEARCH_INCOMPLETE")
    status = OFFLINE_CANDIDATE if selected_candidate is not None else POSITION_ONLY_UNFIXABLE
    json_bytes = _serialize_result(
        status,
        frozen_records,
        passing_count,
        selected_record_index,
        selected_position_sha256,
    )
    return SearchResult(
        status=status,
        records=frozen_records,
        passing_count=passing_count,
        selected_record_index=selected_record_index,
        selected_position_sha256=selected_position_sha256,
        selected_candidate=selected_candidate,
        json_bytes=json_bytes,
    )
