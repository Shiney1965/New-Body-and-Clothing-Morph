"""Deterministic one-ring repair for the retained Bard SBBF sleeve blocker."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from .contracts import load_bard_contract


PASS_REPAIRED = "PASS_REPAIRED"
PASS_UNCHANGED = "PASS_UNCHANGED"
METHOD_EXHAUSTED = "METHOD_SPECIFIC_EXHAUSTION"
PASS_PAIR = "PASS_OFFLINE_SBBF_PAIR"
BASE_STREAMS = (
    "HUM_F_ARM_Bard_BodyTop_Mesh",
    "HUM_F_ARM_Bard_Footwear_Mesh",
    "HUM_F_ARM_Bard_Pants_Mesh",
    "HUM_F_ARM_Bard_Sleeves_Mesh",
)
THONG_STREAM = "HUM_F_ARM_Gortash_Body_Jacket_Mesh"


@dataclass(frozen=True)
class TopologyMetrics:
    triangles: int
    baseline_zero_area_faces: int
    flipped_faces: int
    new_zero_area_faces: int
    below_area_floor: int
    minimum_area_ratio: float

    @property
    def passed(self) -> bool:
        return (
            self.flipped_faces == 0
            and self.new_zero_area_faces == 0
            and self.below_area_floor == 0
        )


@dataclass(frozen=True)
class RepairRegion:
    failing_face_indices: tuple[int, ...]
    seed_vertex_indices: tuple[int, ...]
    one_ring_face_indices: tuple[int, ...]
    movable_vertex_indices: tuple[int, ...]
    affected_face_indices: tuple[int, ...]


@dataclass(frozen=True)
class GateReport:
    passed: bool
    changed_outside_rows: tuple[int, ...]


@dataclass(frozen=True)
class CandidateResult:
    status: str
    positions: np.ndarray | None
    pre_metrics: TopologyMetrics
    post_metrics: TopologyMetrics | None
    region: RepairRegion
    outside_gate: GateReport | None
    blend_step: int | None
    blend_steps: int
    position_sha256: str | None
    exhaustion_reason: str | None


@dataclass(frozen=True)
class CompletePairResult:
    status: str
    replacement_routes: int
    candidate_positions: dict[str, dict[str, np.ndarray]] | None
    position_digest: str | None
    exhaustion_reason: str | None
    base_results: Mapping[str, CandidateResult]
    thong_result: CandidateResult


def _validated_arrays(
    source: np.ndarray,
    candidate: np.ndarray,
    faces: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source_array = np.asarray(source)
    candidate_array = np.asarray(candidate)
    face_array = np.asarray(faces)
    if source_array.shape != candidate_array.shape or source_array.ndim != 2 or source_array.shape[1] != 3:
        raise ValueError("POSITION_SHAPE_MISMATCH")
    if face_array.ndim != 2 or face_array.shape[1] != 3:
        raise ValueError("TRIANGLE_SHAPE_INVALID")
    if not np.issubdtype(face_array.dtype, np.integer):
        raise ValueError("TRIANGLE_DTYPE_INVALID")
    if len(face_array) and (int(face_array.min()) < 0 or int(face_array.max()) >= len(source_array)):
        raise ValueError("TRIANGLE_INDEX_OUT_OF_RANGE")
    if not np.isfinite(source_array).all() or not np.isfinite(candidate_array).all():
        raise ValueError("POSITION_NONFINITE")
    return (
        source_array.astype(np.float64, copy=False),
        candidate_array.astype(np.float64, copy=False),
        face_array.astype(np.int64, copy=False),
    )


def _metric_masks(
    source: np.ndarray,
    candidate: np.ndarray,
    faces: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    source_cross = np.cross(
        source[faces[:, 1]] - source[faces[:, 0]],
        source[faces[:, 2]] - source[faces[:, 0]],
    )
    candidate_cross = np.cross(
        candidate[faces[:, 1]] - candidate[faces[:, 0]],
        candidate[faces[:, 2]] - candidate[faces[:, 0]],
    )
    source_area = np.linalg.norm(source_cross, axis=1) * 0.5
    candidate_area = np.linalg.norm(candidate_cross, axis=1) * 0.5
    baseline_zero = source_area <= 1e-12
    candidate_zero = candidate_area <= 1e-12
    valid = ~baseline_zero
    ratios = np.ones(len(faces), dtype=np.float64)
    ratios[valid] = candidate_area[valid] / source_area[valid]
    flipped = valid & (np.einsum("ij,ij->i", source_cross, candidate_cross) <= 0.0)
    new_zero = candidate_zero & valid
    below_floor = valid & (ratios < threshold)
    return baseline_zero, flipped, new_zero, below_floor, ratios


def topology_metrics(
    source: np.ndarray,
    candidate: np.ndarray,
    faces: np.ndarray,
    threshold: float = 0.25,
) -> TopologyMetrics:
    """Measure all fixed triangle gates against the unchanged source topology."""
    if not 0.0 < threshold <= 1.0:
        raise ValueError("AREA_THRESHOLD_INVALID")
    source_array, candidate_array, face_array = _validated_arrays(source, candidate, faces)
    baseline_zero, flipped, new_zero, below_floor, ratios = _metric_masks(
        source_array,
        candidate_array,
        face_array,
        threshold,
    )
    valid = ~baseline_zero
    return TopologyMetrics(
        triangles=int(len(face_array)),
        baseline_zero_area_faces=int(np.count_nonzero(baseline_zero)),
        flipped_faces=int(np.count_nonzero(flipped)),
        new_zero_area_faces=int(np.count_nonzero(new_zero)),
        below_area_floor=int(np.count_nonzero(below_floor)),
        minimum_area_ratio=float(np.min(ratios[valid])) if np.any(valid) else 1.0,
    )


def failing_face_neighborhood(
    source: np.ndarray,
    candidate: np.ndarray,
    faces: np.ndarray,
    threshold: float = 0.25,
) -> RepairRegion:
    """Return the only vertices the local repair is authorized to move."""
    source_array, candidate_array, face_array = _validated_arrays(source, candidate, faces)
    _, flipped, new_zero, below_floor, _ = _metric_masks(
        source_array,
        candidate_array,
        face_array,
        threshold,
    )
    failing_faces = np.flatnonzero(flipped | new_zero | below_floor)
    if not len(failing_faces):
        return RepairRegion((), (), (), (), ())
    seed_vertices = np.unique(face_array[failing_faces].reshape(-1))
    one_ring_faces = np.flatnonzero(np.any(np.isin(face_array, seed_vertices), axis=1))
    movable_vertices = np.unique(face_array[one_ring_faces].reshape(-1))
    affected_faces = np.flatnonzero(np.any(np.isin(face_array, movable_vertices), axis=1))
    return RepairRegion(
        failing_face_indices=tuple(map(int, failing_faces)),
        seed_vertex_indices=tuple(map(int, seed_vertices)),
        one_ring_face_indices=tuple(map(int, one_ring_faces)),
        movable_vertex_indices=tuple(map(int, movable_vertices)),
        affected_face_indices=tuple(map(int, affected_faces)),
    )


def verify_outside_region_exact(
    before: np.ndarray,
    after: np.ndarray,
    movable_vertex_indices: tuple[int, ...],
) -> GateReport:
    """Require byte-equivalent float32 POSITION rows outside the repair region."""
    before_array = np.asarray(before, dtype="<f4")
    after_array = np.asarray(after, dtype="<f4")
    if before_array.shape != after_array.shape or before_array.ndim != 2 or before_array.shape[1] != 3:
        raise ValueError("POSITION_SHAPE_MISMATCH")
    movable = np.zeros(len(before_array), dtype=bool)
    indices = np.asarray(movable_vertex_indices, dtype=np.int64)
    if len(indices):
        if int(indices.min()) < 0 or int(indices.max()) >= len(before_array):
            raise ValueError("REPAIR_VERTEX_OUT_OF_RANGE")
        movable[indices] = True
    changed = np.flatnonzero((~movable) & np.any(before_array != after_array, axis=1))
    return GateReport(
        passed=not len(changed),
        changed_outside_rows=tuple(map(int, changed)),
    )


def _position_sha256(positions: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(positions, dtype="<f4").tobytes(order="C")).hexdigest().upper()


def solve_local_area_constrained_positions(
    source: np.ndarray,
    candidate: np.ndarray,
    faces: np.ndarray,
    threshold: float = 0.25,
    *,
    blend_steps: int = 4096,
) -> CandidateResult:
    """Search a fixed grid for the least one-ring relaxation that passes every face gate."""
    if blend_steps <= 0:
        raise ValueError("BLEND_STEPS_INVALID")
    source_array, candidate_array, face_array = _validated_arrays(source, candidate, faces)
    pre_metrics = topology_metrics(source_array, candidate_array, face_array, threshold)
    region = failing_face_neighborhood(source_array, candidate_array, face_array, threshold)
    baseline_f32 = np.asarray(candidate_array, dtype="<f4")

    if pre_metrics.passed:
        post_metrics = topology_metrics(source_array, baseline_f32, face_array, threshold)
        outside = verify_outside_region_exact(baseline_f32, baseline_f32, ())
        if post_metrics.passed:
            return CandidateResult(
                status=PASS_UNCHANGED,
                positions=baseline_f32,
                pre_metrics=pre_metrics,
                post_metrics=post_metrics,
                region=region,
                outside_gate=outside,
                blend_step=0,
                blend_steps=blend_steps,
                position_sha256=_position_sha256(baseline_f32),
                exhaustion_reason=None,
            )

    movable = np.asarray(region.movable_vertex_indices, dtype=np.int64)
    for step in range(1, blend_steps + 1):
        weight = float(step) / float(blend_steps)
        trial = baseline_f32.copy()
        blended = candidate_array[movable] + weight * (source_array[movable] - candidate_array[movable])
        trial[movable] = blended.astype("<f4")
        post_metrics = topology_metrics(source_array, trial, face_array, threshold)
        if not post_metrics.passed:
            continue
        outside = verify_outside_region_exact(baseline_f32, trial, region.movable_vertex_indices)
        if not outside.passed:
            continue
        return CandidateResult(
            status=PASS_REPAIRED,
            positions=trial,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            region=region,
            outside_gate=outside,
            blend_step=step,
            blend_steps=blend_steps,
            position_sha256=_position_sha256(trial),
            exhaustion_reason=None,
        )

    return CandidateResult(
        status=METHOD_EXHAUSTED,
        positions=None,
        pre_metrics=pre_metrics,
        post_metrics=None,
        region=region,
        outside_gate=None,
        blend_step=None,
        blend_steps=blend_steps,
        position_sha256=None,
        exhaustion_reason="ONE_RING_AREA_CONSTRAINED_BLEND_EXHAUSTED",
    )


def _result_admitted(result: CandidateResult) -> bool:
    return (
        result.status in {PASS_REPAIRED, PASS_UNCHANGED}
        and result.positions is not None
        and result.post_metrics is not None
        and result.post_metrics.passed
        and result.outside_gate is not None
        and result.outside_gate.passed
    )


def _exhausted_pair(
    base_results: Mapping[str, CandidateResult],
    thong_result: CandidateResult,
    reason: str,
) -> CompletePairResult:
    return CompletePairResult(
        status=METHOD_EXHAUSTED,
        replacement_routes=0,
        candidate_positions=None,
        position_digest=None,
        exhaustion_reason=reason,
        base_results=base_results,
        thong_result=thong_result,
    )


def complete_sbbf_pair(
    base_results: Mapping[str, CandidateResult],
    thong_result: CandidateResult,
    *,
    semantic_contract_exact: bool = True,
    index_contract_exact: bool = True,
    topology_contract_exact: bool = True,
) -> CompletePairResult:
    """Admit no output unless the exact four-stream base and thong pair both pass."""
    load_bard_contract().require_emittable_pair("sbbf", ("base", "thong"))
    if set(base_results) != set(BASE_STREAMS):
        return _exhausted_pair(base_results, thong_result, "SBBF_BASE_STREAM_SET_INCOMPLETE")
    if not semantic_contract_exact:
        return _exhausted_pair(base_results, thong_result, "SBBF_NON_POSITION_SEMANTIC_CHANGE")
    if not index_contract_exact:
        return _exhausted_pair(base_results, thong_result, "SBBF_INDEX_CHANGE")
    if not topology_contract_exact:
        return _exhausted_pair(base_results, thong_result, "SBBF_TOPOLOGY_CHANGE")
    if not all(_result_admitted(base_results[name]) for name in BASE_STREAMS):
        return _exhausted_pair(base_results, thong_result, "SBBF_BASE_STREAM_GATE_FAILURE")
    if not _result_admitted(thong_result):
        return _exhausted_pair(base_results, thong_result, "SBBF_THONG_GATE_FAILURE")

    positions = {
        "base": {name: np.asarray(base_results[name].positions, dtype="<f4") for name in BASE_STREAMS},
        "thong": {THONG_STREAM: np.asarray(thong_result.positions, dtype="<f4")},
    }
    digest = hashlib.sha256()
    for component in ("base", "thong"):
        for stream in sorted(positions[component]):
            digest.update(component.encode("utf-8"))
            digest.update(stream.encode("utf-8"))
            digest.update(positions[component][stream].tobytes(order="C"))
    return CompletePairResult(
        status=PASS_PAIR,
        replacement_routes=2,
        candidate_positions=positions,
        position_digest=digest.hexdigest().upper(),
        exhaustion_reason=None,
        base_results=base_results,
        thong_result=thong_result,
    )


def _metrics_payload(metrics: TopologyMetrics | None) -> dict[str, object] | None:
    if metrics is None:
        return None
    return {
        "triangles": metrics.triangles,
        "baseline_zero_area_faces": metrics.baseline_zero_area_faces,
        "flipped_faces": metrics.flipped_faces,
        "new_zero_area_faces": metrics.new_zero_area_faces,
        "below_area_floor": metrics.below_area_floor,
        "minimum_area_ratio": metrics.minimum_area_ratio,
    }


def _candidate_payload(result: CandidateResult) -> dict[str, object]:
    return {
        "status": result.status,
        "pre_metrics": _metrics_payload(result.pre_metrics),
        "post_metrics": _metrics_payload(result.post_metrics),
        "failing_face_indices": list(result.region.failing_face_indices),
        "seed_vertex_indices": list(result.region.seed_vertex_indices),
        "movable_vertex_indices": list(result.region.movable_vertex_indices),
        "affected_face_indices": list(result.region.affected_face_indices),
        "blend_step": result.blend_step,
        "blend_steps": result.blend_steps,
        "position_sha256": result.position_sha256,
        "outside_rows_exact": None if result.outside_gate is None else result.outside_gate.passed,
        "exhaustion_reason": result.exhaustion_reason,
    }


def write_offline_result(
    output_directory: Path,
    result: CompletePairResult,
    *,
    input_hashes: Mapping[str, str] | None = None,
) -> tuple[Path, Path | None]:
    """Write ignored evidence, and write position-only bytes only for an admitted full pair."""
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    candidate_path: Path | None = None
    if result.candidate_positions is not None:
        candidate_path = output_directory / "bard_sbbf_candidate_positions.npz"
        arrays = {
            f"{component}::{stream}": positions
            for component, streams in result.candidate_positions.items()
            for stream, positions in streams.items()
        }
        np.savez(candidate_path, **arrays)
    report_path = output_directory / "bard_sbbf_repair_report.json"
    report = {
        "schema": "bard_sbbf_one_ring_repair_v1",
        "method": "failing-face one-ring fixed-grid relaxation toward source POSITION rows",
        "status": result.status,
        "replacement_routes": result.replacement_routes,
        "position_digest": result.position_digest,
        "exhaustion_reason": result.exhaustion_reason,
        "candidate_file": None if candidate_path is None else candidate_path.name,
        "verified_input_sha256": dict(sorted((input_hashes or {}).items())),
        "base_streams": {
            name: _candidate_payload(value)
            for name, value in result.base_results.items()
        },
        "thong": _candidate_payload(result.thong_result),
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report_path, candidate_path
