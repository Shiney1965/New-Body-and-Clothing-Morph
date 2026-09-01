"""Hash-locked component landmark contracts and deterministic harmonic cages for Bard Vanilla."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import types
from typing import Mapping
import zipfile

import numpy as np

from .bard_sbbf_repair import (
    BASE_STREAMS,
    THONG_STREAM,
    StreamIdentity,
    TopologyMetrics,
    index_topology_digest,
    topology_metrics,
)
from .contracts import load_bard_contract
from .configuration import load_local_configuration, verify_evidence_inputs


SCHEMA = "bard_component_landmark_cage_v1"
SCHEMA_VERSION = 1
SEARCH_ALPHAS = (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5)
STREAM_PASS = "PASS_STREAM_CAGE"
STREAM_EXHAUSTED = "CAGE_SEARCH_EXHAUSTED"
COMPLETE_PAIR_PASS = "PASS_OFFLINE_VANILLA_PAIR"
UNFIXABLE = "UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING"
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
WORKSTREAM_ROOT = Path(__file__).resolve().parent
LANDMARKS_PATH = WORKSTREAM_ROOT / "local" / "landmarks.json"


class LandmarkContractError(ValueError):
    """Raised when ignored local landmarks do not satisfy the frozen cage contract."""


@dataclass(frozen=True)
class LandmarkAnchor:
    anchor_id: str
    component: str
    stream_id: str
    cage_index: tuple[int, int, int]
    source_body_vertex: int
    target_body_vertex: int
    source_point: tuple[float, float, float]
    target_point: tuple[float, float, float]

    @property
    def displacement(self) -> tuple[float, float, float]:
        return tuple(target - source for source, target in zip(self.source_point, self.target_point))


@dataclass(frozen=True)
class StreamLandmarkContract:
    component: str
    stream_id: str
    vertex_count: int
    position_shape: tuple[int, int]
    index_topology_sha256: str
    non_position_semantic_sha256: str
    cage_shape: tuple[int, int, int]
    cage_min: tuple[float, float, float]
    cage_max: tuple[float, float, float]
    anchors: tuple[LandmarkAnchor, ...]


@dataclass(frozen=True)
class LandmarkContract:
    schema: str
    schema_version: int
    mode: str
    component: str
    common_frame_report_sha256: str
    source_body_sha256: str
    target_body_sha256: str
    source_component_sha256: str
    search_alphas: tuple[float, ...]
    streams: tuple[StreamLandmarkContract, ...]

    @property
    def streams_by_id(self) -> dict[str, StreamLandmarkContract]:
        return {stream.stream_id: stream for stream in self.streams}


@dataclass(frozen=True)
class CageStreamInput:
    component: str
    stream_identity: StreamIdentity
    source_positions: np.ndarray
    faces: np.ndarray
    landmark_stream: StreamLandmarkContract


@dataclass(frozen=True)
class StreamCageResult:
    stream_identity: StreamIdentity
    status: str
    positions: np.ndarray | None
    source_metrics: TopologyMetrics
    post_metrics: TopologyMetrics | None
    selected_alpha: float | None
    attempted_alphas: tuple[float, ...]
    attempt_metrics: tuple[TopologyMetrics, ...]
    cage_displacement_sha256: str
    position_sha256: str | None
    maximum_control_displacement: float
    maximum_vertex_displacement: float
    exhaustion_reason: str | None


@dataclass(frozen=True)
class CompletePairResult:
    mode: str
    status: str
    replacement_routes: int
    protected_bcb_replacement_routes: int
    candidate_positions: dict[str, dict[str, np.ndarray]] | None
    position_digest: str | None
    exhaustion_reason: str | None
    verified_input_sha256: Mapping[str, str]
    landmark_contract_sha256: str
    base_inputs: Mapping[str, CageStreamInput]
    base_results: Mapping[str, StreamCageResult]
    thong_input: CageStreamInput | None
    thong_result: StreamCageResult | None


def _mapping(value: object, error: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LandmarkContractError(error)
    return value


def _text(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise LandmarkContractError(f"LANDMARK_{key.upper()}_INVALID")
    return value


def _integer(mapping: dict[str, object], key: str, *, minimum: int = 0) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LandmarkContractError(f"LANDMARK_{key.upper()}_INVALID")
    return value


def _sha256(mapping: dict[str, object], key: str) -> str:
    value = _text(mapping, key)
    if SHA256_RE.fullmatch(value) is None:
        raise LandmarkContractError(f"LANDMARK_{key.upper()}_INVALID")
    return value


def _int3(mapping: dict[str, object], key: str, *, minimum: int = 0) -> tuple[int, int, int]:
    value = mapping.get(key)
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(isinstance(item, bool) or not isinstance(item, int) or item < minimum for item in value)
    ):
        raise LandmarkContractError(f"LANDMARK_{key.upper()}_INVALID")
    return tuple(value)


def _float3(mapping: dict[str, object], key: str) -> tuple[float, float, float]:
    value = mapping.get(key)
    if not isinstance(value, list) or len(value) != 3:
        raise LandmarkContractError(f"LANDMARK_{key.upper()}_INVALID")
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise LandmarkContractError(f"LANDMARK_{key.upper()}_INVALID")
    return tuple(map(float, result))


def _boundary_indices(shape: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (i, j, k)
        for i in range(shape[0])
        for j in range(shape[1])
        for k in range(shape[2])
        if i in {0, shape[0] - 1}
        or j in {0, shape[1] - 1}
        or k in {0, shape[2] - 1}
    )


def _parse_anchor(
    value: object,
    *,
    component: str,
    stream_id: str,
    cage_shape: tuple[int, int, int],
) -> LandmarkAnchor:
    mapping = _mapping(value, "LANDMARK_ANCHOR_INVALID")
    anchor_component = _text(mapping, "component")
    anchor_stream = _text(mapping, "stream_id")
    if anchor_component != component or anchor_stream != stream_id:
        raise LandmarkContractError("LANDMARK_ANCHOR_OUT_OF_COMPONENT")
    cage_index = _int3(mapping, "cage_index")
    if any(index >= cage_shape[axis] for axis, index in enumerate(cage_index)):
        raise LandmarkContractError("LANDMARK_CAGE_INDEX_OUT_OF_RANGE")
    return LandmarkAnchor(
        anchor_id=_text(mapping, "anchor_id"),
        component=anchor_component,
        stream_id=anchor_stream,
        cage_index=cage_index,
        source_body_vertex=_integer(mapping, "source_body_vertex"),
        target_body_vertex=_integer(mapping, "target_body_vertex"),
        source_point=_float3(mapping, "source_point"),
        target_point=_float3(mapping, "target_point"),
    )


def _expand_anchor_columns(
    value: object,
    *,
    component: str,
    stream_id: str,
) -> list[object]:
    if isinstance(value, list):
        return value
    mapping = _mapping(value, "LANDMARK_ANCHORS_INVALID")
    column_names = (
        "cage_indices",
        "source_body_vertices",
        "target_body_vertices",
        "source_points",
        "target_points",
    )
    columns = [mapping.get(name) for name in column_names]
    if any(not isinstance(column, list) for column in columns):
        raise LandmarkContractError("LANDMARK_ANCHORS_INVALID")
    lengths = {len(column) for column in columns}
    if len(lengths) != 1 or lengths == {0}:
        raise LandmarkContractError("LANDMARK_ANCHOR_COLUMNS_LENGTH_MISMATCH")
    expanded: list[object] = []
    for row, values in enumerate(zip(*columns, strict=True)):
        cage_index, source_vertex, target_vertex, source_point, target_point = values
        index_label = ":".join(map(str, cage_index)) if isinstance(cage_index, list) else str(row)
        expanded.append(
            {
                "anchor_id": f"{stream_id}:{index_label}",
                "component": component,
                "stream_id": stream_id,
                "cage_index": cage_index,
                "source_body_vertex": source_vertex,
                "target_body_vertex": target_vertex,
                "source_point": source_point,
                "target_point": target_point,
            }
        )
    return expanded


def _parse_stream(value: object, component: str) -> StreamLandmarkContract:
    mapping = _mapping(value, "LANDMARK_STREAM_INVALID")
    stream_id = _text(mapping, "stream_id")
    vertex_count = _integer(mapping, "vertex_count", minimum=1)
    raw_shape = mapping.get("position_shape")
    if (
        not isinstance(raw_shape, list)
        or len(raw_shape) != 2
        or raw_shape != [vertex_count, 3]
    ):
        raise LandmarkContractError("LANDMARK_POSITION_SHAPE_INVALID")
    cage_shape = _int3(mapping, "cage_shape", minimum=3)
    if any(value > 9 for value in cage_shape):
        raise LandmarkContractError("LANDMARK_CAGE_SHAPE_TOO_LARGE")
    cage_min = _float3(mapping, "cage_min")
    cage_max = _float3(mapping, "cage_max")
    if any(high <= low for low, high in zip(cage_min, cage_max)):
        raise LandmarkContractError("LANDMARK_CAGE_BOUNDS_INVALID")
    raw_anchors = _expand_anchor_columns(
        mapping.get("anchors"),
        component=component,
        stream_id=stream_id,
    )
    anchors = tuple(
        _parse_anchor(
            anchor,
            component=component,
            stream_id=stream_id,
            cage_shape=cage_shape,
        )
        for anchor in raw_anchors
    )
    if len({anchor.anchor_id for anchor in anchors}) != len(anchors):
        raise LandmarkContractError("LANDMARK_ANCHOR_ID_DUPLICATE")
    if len({anchor.cage_index for anchor in anchors}) != len(anchors):
        raise LandmarkContractError("LANDMARK_CAGE_INDEX_DUPLICATE")
    if len({anchor.source_body_vertex for anchor in anchors}) != len(anchors):
        raise LandmarkContractError("LANDMARK_SOURCE_BODY_VERTEX_DUPLICATE")
    if len({anchor.target_body_vertex for anchor in anchors}) != len(anchors):
        raise LandmarkContractError("LANDMARK_TARGET_BODY_VERTEX_DUPLICATE")
    expected_boundary = _boundary_indices(cage_shape)
    actual_boundary = tuple(anchor.cage_index for anchor in anchors)
    if set(actual_boundary) != set(expected_boundary):
        raise LandmarkContractError("LANDMARK_BOUNDARY_ANCHOR_MISSING")
    maximum_displacement = max(np.linalg.norm(anchor.displacement) for anchor in anchors)
    if not np.isfinite(maximum_displacement) or maximum_displacement <= 1e-7:
        raise LandmarkContractError("LANDMARK_CONTROL_FIELD_TRIVIAL")
    return StreamLandmarkContract(
        component=component,
        stream_id=stream_id,
        vertex_count=vertex_count,
        position_shape=(vertex_count, 3),
        index_topology_sha256=_sha256(mapping, "index_topology_sha256"),
        non_position_semantic_sha256=_sha256(mapping, "non_position_semantic_sha256"),
        cage_shape=cage_shape,
        cage_min=cage_min,
        cage_max=cage_max,
        anchors=anchors,
    )


def parse_component_landmark_contract(
    payload: object,
    component: str,
    mode: str,
) -> LandmarkContract:
    """Parse one explicit component contract and reject ambiguous anchor sets."""
    mapping = _mapping(payload, "LANDMARK_ROOT_INVALID")
    if _text(mapping, "schema") != SCHEMA or _integer(mapping, "schema_version", minimum=1) != SCHEMA_VERSION:
        raise LandmarkContractError("LANDMARK_SCHEMA_INVALID")
    actual_mode = _text(mapping, "mode")
    actual_component = _text(mapping, "component")
    if actual_mode != mode:
        raise LandmarkContractError("LANDMARK_MODE_MISMATCH")
    if actual_component != component:
        raise LandmarkContractError("LANDMARK_COMPONENT_MISMATCH")
    raw_alphas = mapping.get("search_alphas")
    if not isinstance(raw_alphas, list):
        raise LandmarkContractError("LANDMARK_SEARCH_ALPHAS_INVALID")
    try:
        search_alphas = tuple(map(float, raw_alphas))
    except (TypeError, ValueError) as error:
        raise LandmarkContractError("LANDMARK_SEARCH_ALPHAS_INVALID") from error
    if search_alphas != SEARCH_ALPHAS:
        raise LandmarkContractError("LANDMARK_SEARCH_ALPHAS_INVALID")
    raw_streams = mapping.get("streams")
    if not isinstance(raw_streams, list) or not raw_streams:
        raise LandmarkContractError("LANDMARK_STREAMS_INVALID")
    streams = tuple(_parse_stream(value, component) for value in raw_streams)
    if len({stream.stream_id for stream in streams}) != len(streams):
        raise LandmarkContractError("LANDMARK_STREAM_ID_DUPLICATE")
    return LandmarkContract(
        schema=SCHEMA,
        schema_version=SCHEMA_VERSION,
        mode=actual_mode,
        component=actual_component,
        common_frame_report_sha256=_sha256(mapping, "common_frame_report_sha256"),
        source_body_sha256=_sha256(mapping, "source_body_sha256"),
        target_body_sha256=_sha256(mapping, "target_body_sha256"),
        source_component_sha256=_sha256(mapping, "source_component_sha256"),
        search_alphas=search_alphas,
        streams=streams,
    )


def _solve_cage_nodes(contract: StreamLandmarkContract) -> np.ndarray:
    shape = contract.cage_shape
    values = np.zeros((*shape, 3), dtype=np.float64)
    fixed = np.zeros(shape, dtype=bool)
    for anchor in contract.anchors:
        values[anchor.cage_index] = np.asarray(anchor.displacement, dtype=np.float64)
        fixed[anchor.cage_index] = True
    interior = [index for index in np.ndindex(shape) if not fixed[index]]
    if not interior:
        return values
    row_by_index = {index: row for row, index in enumerate(interior)}
    matrix = np.zeros((len(interior), len(interior)), dtype=np.float64)
    rhs = np.zeros((len(interior), 3), dtype=np.float64)
    for row, index in enumerate(interior):
        neighbors = []
        for axis in range(3):
            for direction in (-1, 1):
                neighbor = list(index)
                neighbor[axis] += direction
                if 0 <= neighbor[axis] < shape[axis]:
                    neighbors.append(tuple(neighbor))
        matrix[row, row] = float(len(neighbors))
        for neighbor in neighbors:
            if fixed[neighbor]:
                rhs[row] += values[neighbor]
            else:
                matrix[row, row_by_index[neighbor]] -= 1.0
    solved = np.linalg.solve(matrix, rhs)
    for index, value in zip(interior, solved, strict=True):
        values[index] = value
    residual = matrix @ solved - rhs
    if not np.isfinite(solved).all() or float(np.max(np.abs(residual), initial=0.0)) > 1e-10:
        raise ValueError("CAGE_HARMONIC_SOLVE_FAILED")
    return values


def solve_harmonic_cage_displacement(
    source_positions: np.ndarray,
    contract: StreamLandmarkContract,
) -> np.ndarray:
    """Solve a volumetric Dirichlet cage and trilinearly sample it at source rows."""
    positions = np.asarray(source_positions)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("CAGE_POSITION_SHAPE_INVALID")
    if not np.isfinite(positions).all():
        raise ValueError("CAGE_POSITION_NONFINITE")
    minimum = np.asarray(contract.cage_min, dtype=np.float64)
    maximum = np.asarray(contract.cage_max, dtype=np.float64)
    values = positions.astype(np.float64, copy=False)
    tolerance = 1e-9
    if np.any(values < minimum - tolerance) or np.any(values > maximum + tolerance):
        raise ValueError("CAGE_POSITION_OUTSIDE_DECLARED_BOUNDS")
    if tuple(map(int, positions.shape)) != contract.position_shape:
        raise ValueError("CAGE_POSITION_SHAPE_MISMATCH")
    cage = _solve_cage_nodes(contract)
    shape = np.asarray(contract.cage_shape, dtype=np.int64)
    scaled = (values - minimum) / (maximum - minimum) * (shape - 1)
    lower = np.floor(scaled).astype(np.int64)
    lower = np.minimum(lower, shape - 2)
    lower = np.maximum(lower, 0)
    fraction = scaled - lower
    result = np.zeros_like(values, dtype=np.float64)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                weight = (
                    (fraction[:, 0] if di else 1.0 - fraction[:, 0])
                    * (fraction[:, 1] if dj else 1.0 - fraction[:, 1])
                    * (fraction[:, 2] if dk else 1.0 - fraction[:, 2])
                )
                indices = lower + np.array([di, dj, dk], dtype=np.int64)
                result += weight[:, None] * cage[indices[:, 0], indices[:, 1], indices[:, 2]]
    if not np.isfinite(result).all():
        raise ValueError("CAGE_DISPLACEMENT_NONFINITE")
    return result


def validate_common_frame_landmarks(
    contract: StreamLandmarkContract,
    source_body: np.ndarray,
    target_body: np.ndarray,
) -> None:
    """Bind every explicit anchor index and coordinate to the hash-locked posed bodies."""
    source = np.asarray(source_body)
    target = np.asarray(target_body)
    if (
        source.ndim != 2
        or target.ndim != 2
        or source.shape[1:] != (3,)
        or target.shape[1:] != (3,)
        or not np.isfinite(source).all()
        or not np.isfinite(target).all()
    ):
        raise ValueError("LANDMARK_COMMON_FRAME_ARRAY_INVALID")
    for anchor in contract.anchors:
        if anchor.source_body_vertex >= len(source):
            raise ValueError("LANDMARK_SOURCE_VERTEX_OUT_OF_RANGE")
        if anchor.target_body_vertex >= len(target):
            raise ValueError("LANDMARK_TARGET_VERTEX_OUT_OF_RANGE")
        expected_source = np.asarray(anchor.source_point, dtype=np.float64)
        expected_target = np.asarray(anchor.target_point, dtype=np.float64)
        if not np.array_equal(source[anchor.source_body_vertex], expected_source):
            raise ValueError("LANDMARK_SOURCE_POINT_MISMATCH")
        if not np.array_equal(target[anchor.target_body_vertex], expected_target):
            raise ValueError("LANDMARK_TARGET_POINT_MISMATCH")


def _array_sha256(values: np.ndarray, *, dtype: str) -> str:
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes(order="C")).hexdigest().upper()


def solve_stream_landmark_cage(stream_input: CageStreamInput) -> StreamCageResult:
    """Run exactly one declared harmonic cage field over the fixed alpha schedule."""
    identity = stream_input.stream_identity
    contract = stream_input.landmark_stream
    source = np.asarray(stream_input.source_positions)
    faces = np.asarray(stream_input.faces)
    if contract.component != stream_input.component or contract.stream_id != identity.stream_id:
        raise ValueError("CAGE_STREAM_CONTRACT_MISMATCH")
    if identity.position_shape != tuple(map(int, source.shape)) or contract.position_shape != identity.position_shape:
        raise ValueError("CAGE_POSITION_SHAPE_MISMATCH")
    topology_sha256 = index_topology_digest(faces)
    if identity.index_topology_sha256 != topology_sha256 or contract.index_topology_sha256 != topology_sha256:
        raise ValueError("CAGE_INDEX_TOPOLOGY_MISMATCH")
    if identity.non_position_semantic_sha256 != contract.non_position_semantic_sha256:
        raise ValueError("CAGE_NON_POSITION_SEMANTIC_MISMATCH")
    source_metrics = topology_metrics(source, source, faces)
    if not source_metrics.passed:
        raise ValueError("CAGE_SOURCE_TOPOLOGY_INVALID")
    displacement = solve_harmonic_cage_displacement(source, contract)
    control_maximum = max(np.linalg.norm(anchor.displacement) for anchor in contract.anchors)
    vertex_maximum = float(np.max(np.linalg.norm(displacement, axis=1), initial=0.0))
    if control_maximum <= 1e-7 or vertex_maximum <= 1e-7:
        raise ValueError("CAGE_DISPLACEMENT_TRIVIAL")
    attempts: list[TopologyMetrics] = []
    for alpha in SEARCH_ALPHAS:
        positions = np.asarray(source + alpha * displacement, dtype="<f4")
        metrics = topology_metrics(source, positions, faces)
        attempts.append(metrics)
        if metrics.passed:
            return StreamCageResult(
                stream_identity=identity,
                status=STREAM_PASS,
                positions=positions,
                source_metrics=source_metrics,
                post_metrics=metrics,
                selected_alpha=alpha,
                attempted_alphas=SEARCH_ALPHAS,
                attempt_metrics=tuple(attempts),
                cage_displacement_sha256=_array_sha256(displacement, dtype="<f8"),
                position_sha256=_array_sha256(positions, dtype="<f4"),
                maximum_control_displacement=float(control_maximum),
                maximum_vertex_displacement=vertex_maximum,
                exhaustion_reason=None,
            )
    return StreamCageResult(
        stream_identity=identity,
        status=STREAM_EXHAUSTED,
        positions=None,
        source_metrics=source_metrics,
        post_metrics=None,
        selected_alpha=None,
        attempted_alphas=SEARCH_ALPHAS,
        attempt_metrics=tuple(attempts),
        cage_displacement_sha256=_array_sha256(displacement, dtype="<f8"),
        position_sha256=None,
        maximum_control_displacement=float(control_maximum),
        maximum_vertex_displacement=vertex_maximum,
        exhaustion_reason="NO_FIXED_ALPHA_PASSED_AT_OR_ABOVE_0.50",
    )


def _stream_result_exact(
    supplied: StreamCageResult,
    canonical: StreamCageResult,
) -> bool:
    if (
        supplied.stream_identity != canonical.stream_identity
        or supplied.status != canonical.status
        or supplied.source_metrics != canonical.source_metrics
        or supplied.post_metrics != canonical.post_metrics
        or supplied.selected_alpha != canonical.selected_alpha
        or supplied.attempted_alphas != canonical.attempted_alphas
        or supplied.attempt_metrics != canonical.attempt_metrics
        or supplied.cage_displacement_sha256 != canonical.cage_displacement_sha256
        or supplied.position_sha256 != canonical.position_sha256
        or supplied.maximum_control_displacement != canonical.maximum_control_displacement
        or supplied.maximum_vertex_displacement != canonical.maximum_vertex_displacement
        or supplied.exhaustion_reason != canonical.exhaustion_reason
    ):
        return False
    if (supplied.positions is None) != (canonical.positions is None):
        return False
    if supplied.positions is None:
        return True
    supplied_positions = np.asarray(supplied.positions)
    canonical_positions = np.asarray(canonical.positions)
    return (
        supplied_positions.dtype == np.dtype("<f4")
        and supplied_positions.shape == canonical_positions.shape
        and supplied_positions.tobytes(order="C") == canonical_positions.tobytes(order="C")
    )


def _position_digest(positions: Mapping[str, Mapping[str, np.ndarray]]) -> str:
    digest = hashlib.sha256()
    for component in ("base", "thong"):
        for stream in sorted(positions[component]):
            digest.update(component.encode("utf-8"))
            digest.update(stream.encode("utf-8"))
            digest.update(np.asarray(positions[component][stream], dtype="<f4").tobytes(order="C"))
    return digest.hexdigest().upper()


def _complete_mode_candidate(
    mode: str,
    base_inputs: Mapping[str, CageStreamInput],
    base_results: Mapping[str, StreamCageResult],
    thong_input: CageStreamInput | None,
    thong_result: StreamCageResult | None,
    *,
    verified_input_sha256: Mapping[str, str],
    landmark_contract_sha256: str,
) -> CompletePairResult:
    """Admit only the canonical four-stream base plus thong, with zero BCB routes."""
    if mode == "bcb":
        raise ValueError("BARD_BCB_PROTECTED_NO_REPLACEMENT")
    load_bard_contract().require_emittable_pair(mode, ("base", "thong"))
    if SHA256_RE.fullmatch(landmark_contract_sha256) is None:
        raise ValueError("LANDMARK_CONTRACT_DIGEST_INVALID")
    failures: list[str] = []
    if tuple(base_inputs) != BASE_STREAMS:
        failures.append("BASE_INPUT_STREAM_SET_INCOMPLETE")
    if tuple(base_results) != BASE_STREAMS:
        failures.append("BASE_RESULT_STREAM_SET_INCOMPLETE")
    for stream_id in BASE_STREAMS:
        stream_input = base_inputs.get(stream_id)
        supplied = base_results.get(stream_id)
        if stream_input is None or supplied is None:
            failures.append(stream_id)
            continue
        canonical = solve_stream_landmark_cage(stream_input)
        if not _stream_result_exact(supplied, canonical) or canonical.status != STREAM_PASS:
            failures.append(stream_id)
    if thong_input is None or thong_result is None:
        failures.append(THONG_STREAM)
    else:
        canonical_thong = solve_stream_landmark_cage(thong_input)
        if not _stream_result_exact(thong_result, canonical_thong) or canonical_thong.status != STREAM_PASS:
            failures.append(THONG_STREAM)
    if failures:
        return CompletePairResult(
            mode=mode,
            status=UNFIXABLE,
            replacement_routes=0,
            protected_bcb_replacement_routes=0,
            candidate_positions=None,
            position_digest=None,
            exhaustion_reason="FINAL_COMPONENT_LANDMARK_CAGE_EXHAUSTED:" + ",".join(failures),
            verified_input_sha256=dict(sorted(verified_input_sha256.items())),
            landmark_contract_sha256=landmark_contract_sha256,
            base_inputs=base_inputs,
            base_results=base_results,
            thong_input=thong_input,
            thong_result=thong_result,
        )
    positions = {
        "base": {
            stream_id: np.asarray(base_results[stream_id].positions, dtype="<f4")
            for stream_id in BASE_STREAMS
        },
        "thong": {THONG_STREAM: np.asarray(thong_result.positions, dtype="<f4")},
    }
    return CompletePairResult(
        mode=mode,
        status=COMPLETE_PAIR_PASS,
        replacement_routes=2,
        protected_bcb_replacement_routes=0,
        candidate_positions=positions,
        position_digest=_position_digest(positions),
        exhaustion_reason=None,
        verified_input_sha256=dict(sorted(verified_input_sha256.items())),
        landmark_contract_sha256=landmark_contract_sha256,
        base_inputs=base_inputs,
        base_results=base_results,
        thong_input=thong_input,
        thong_result=thong_result,
    )


def _canonical_complete(result: CompletePairResult) -> CompletePairResult:
    return _complete_mode_candidate(
        result.mode,
        result.base_inputs,
        result.base_results,
        result.thong_input,
        result.thong_result,
        verified_input_sha256=result.verified_input_sha256,
        landmark_contract_sha256=result.landmark_contract_sha256,
    )


def _validate_offline_result(result: CompletePairResult) -> None:
    canonical = _canonical_complete(result)
    if (
        result.status != canonical.status
        or result.replacement_routes != canonical.replacement_routes
        or result.protected_bcb_replacement_routes != 0
        or canonical.protected_bcb_replacement_routes != 0
        or result.position_digest != canonical.position_digest
        or result.exhaustion_reason != canonical.exhaustion_reason
        or dict(result.verified_input_sha256) != dict(canonical.verified_input_sha256)
        or result.landmark_contract_sha256 != canonical.landmark_contract_sha256
    ):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if _REAL_INPUT_IDS <= set(result.verified_input_sha256):
        current = {
            item.input_id: item.actual_sha256
            for item in verify_evidence_inputs(load_local_configuration())
        }
        if dict(result.verified_input_sha256) != dict(sorted(current.items())):
            raise ValueError("OFFLINE_RESULT_INPUT_HASH_MISMATCH")
        if hashlib.sha256(LANDMARKS_PATH.read_bytes()).hexdigest().upper() != (
            result.landmark_contract_sha256
        ):
            raise ValueError("OFFLINE_RESULT_LANDMARK_HASH_MISMATCH")
    if (result.candidate_positions is None) != (canonical.candidate_positions is None):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if result.candidate_positions is None:
        return
    if set(result.candidate_positions) != {"base", "thong"}:
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if tuple(result.candidate_positions["base"]) != BASE_STREAMS:
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if tuple(result.candidate_positions["thong"]) != (THONG_STREAM,):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    for component in ("base", "thong"):
        for stream_id, expected in canonical.candidate_positions[component].items():
            actual = np.asarray(result.candidate_positions[component][stream_id])
            if (
                actual.dtype != np.dtype("<f4")
                or actual.shape != expected.shape
                or actual.tobytes(order="C") != expected.tobytes(order="C")
            ):
                raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if result.position_digest != _position_digest(result.candidate_positions):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")


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


def _result_payload(result: StreamCageResult) -> dict[str, object]:
    return {
        "stream_identity": {
            "stream_id": result.stream_identity.stream_id,
            "verified_source_path": result.stream_identity.verified_source_path,
            "verified_source_sha256": result.stream_identity.verified_source_sha256,
            "position_shape": list(result.stream_identity.position_shape),
            "index_topology_sha256": result.stream_identity.index_topology_sha256,
            "non_position_semantic_sha256": result.stream_identity.non_position_semantic_sha256,
        },
        "status": result.status,
        "source_metrics": _metrics_payload(result.source_metrics),
        "post_metrics": _metrics_payload(result.post_metrics),
        "selected_alpha": result.selected_alpha,
        "attempted_alphas": list(result.attempted_alphas),
        "attempt_metrics": [_metrics_payload(value) for value in result.attempt_metrics],
        "cage_displacement_sha256": result.cage_displacement_sha256,
        "position_sha256": result.position_sha256,
        "maximum_control_displacement": result.maximum_control_displacement,
        "maximum_vertex_displacement": result.maximum_vertex_displacement,
        "exhaustion_reason": result.exhaustion_reason,
    }


def _npy_bytes(array: np.ndarray) -> bytes:
    stream = BytesIO()
    np.lib.format.write_array(stream, np.asarray(array, dtype="<f4"), allow_pickle=False)
    return stream.getvalue()


def _write_deterministic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(arrays):
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, _npy_bytes(arrays[name]))


def write_offline_result(
    output_directory: Path,
    result: CompletePairResult,
) -> tuple[Path, Path | None]:
    """Write ignored evidence and serialize POSITION rows only for an atomic pass."""
    _validate_offline_result(result)
    output_directory = Path(output_directory)
    report_path = output_directory / "bard_vanilla_landmark_cage_report.json"
    candidate_path = output_directory / "bard_vanilla_landmark_cage_positions.npz"
    if report_path.exists() or candidate_path.exists():
        raise FileExistsError(f"OFFLINE_OUTPUT_ALREADY_EXISTS:{output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    emitted_candidate: Path | None = None
    if result.candidate_positions is not None:
        arrays = {
            f"{component}::{stream_id}": positions
            for component, streams in result.candidate_positions.items()
            for stream_id, positions in streams.items()
        }
        _write_deterministic_npz(candidate_path, arrays)
        emitted_candidate = candidate_path
    report = {
        "schema": "bard_vanilla_component_landmark_cage_result_v1",
        "method": "component-specific explicit 3D Dirichlet landmark cage with harmonic volumetric solve",
        "materially_distinct_from": [
            "cross-sectional radial profile",
            "nearest-neighbor field",
            "mesh-topology smoothing",
            "failing-face one-ring relaxation",
        ],
        "mode": result.mode,
        "status": result.status,
        "replacement_routes": result.replacement_routes,
        "protected_bcb_replacement_routes": result.protected_bcb_replacement_routes,
        "position_digest": result.position_digest,
        "exhaustion_reason": result.exhaustion_reason,
        "candidate_file": None if emitted_candidate is None else emitted_candidate.name,
        "search_alphas": list(SEARCH_ALPHAS),
        "completion_floor": 0.5,
        "landmark_contract_sha256": result.landmark_contract_sha256,
        "verified_input_sha256": dict(sorted(result.verified_input_sha256.items())),
        "base_streams": {
            stream_id: _result_payload(result.base_results[stream_id])
            for stream_id in result.base_results
        },
        "thong": None if result.thong_result is None else _result_payload(result.thong_result),
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report_path, emitted_candidate


def load_component_landmark_contract(component: str, mode: str) -> LandmarkContract:
    """Load one component from the canonical ignored local landmark file."""
    if not LANDMARKS_PATH.is_file():
        raise LandmarkContractError("CANONICAL_LOCAL_LANDMARKS_MISSING")
    try:
        payload = json.loads(LANDMARKS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LandmarkContractError("LANDMARK_JSON_INVALID") from error
    root = _mapping(payload, "LANDMARK_FILE_ROOT_INVALID")
    raw_contracts = root.get("contracts")
    if not isinstance(raw_contracts, list):
        raise LandmarkContractError("LANDMARK_FILE_CONTRACTS_INVALID")
    matches = [
        value
        for value in raw_contracts
        if isinstance(value, dict)
        and value.get("component") == component
        and value.get("mode") == mode
    ]
    if len(matches) != 1:
        raise LandmarkContractError("LANDMARK_COMPONENT_CONTRACT_MISSING_OR_DUPLICATE")
    return parse_component_landmark_contract(matches[0], component, mode)


_REAL_INPUT_IDS = {
    "legacy_bard_contracts_py",
    "legacy_glb_contract_py",
    "legacy_reconstruct_positions_py",
    "body_bcb_glb",
    "body_vanilla_glb",
    "base_source_glb",
    "thong_source_glb",
    "legacy_offline_search_report",
    "legacy_common_frame_report",
    "legacy_component_contracts",
}


def _load_exact_legacy_modules(verified_by_id: Mapping[str, object]):
    source_directory = Path(verified_by_id["legacy_bard_contracts_py"].path).parent
    module_ids = (
        ("bard_contracts", "legacy_bard_contracts_py"),
        ("glb_contract", "legacy_glb_contract_py"),
        ("reconstruct_positions", "legacy_reconstruct_positions_py"),
    )
    package_digest = hashlib.sha256(
        "|".join(verified_by_id[input_id].actual_sha256 for _, input_id in module_ids).encode("ascii")
    ).hexdigest()[:16]
    package_name = f"_bard_cage_legacy_{package_digest}"
    for module_name, _ in module_ids:
        sys.modules.pop(f"{package_name}.{module_name}", None)
    sys.modules.pop(package_name, None)
    package = types.ModuleType(package_name)
    package.__package__ = package_name
    package.__path__ = [str(source_directory)]
    sys.modules[package_name] = package

    loaded = {}
    prior_dont_write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        for module_name, input_id in module_ids:
            verified = verified_by_id[input_id]
            path = Path(verified.path).resolve()
            if hashlib.sha256(path.read_bytes()).hexdigest().upper() != verified.actual_sha256:
                raise ValueError(f"LEGACY_MODULE_HASH_CHANGED:{input_id}")
            full_name = f"{package_name}.{module_name}"
            specification = importlib.util.spec_from_file_location(full_name, path)
            if specification is None or specification.loader is None:
                raise ValueError(f"LEGACY_MODULE_LOAD_FAILED:{input_id}")
            module = importlib.util.module_from_spec(specification)
            sys.modules[full_name] = module
            specification.loader.exec_module(module)
            if Path(module.__file__).resolve() != path:
                raise ValueError(f"LEGACY_MODULE_PATH_CHANGED:{input_id}")
            loaded[module_name] = module
    finally:
        sys.dont_write_bytecode = prior_dont_write
    return loaded["reconstruct_positions"], loaded["glb_contract"], loaded["bard_contracts"]


def _non_position_semantic_digest(fingerprint: dict[str, object], mesh_name: str) -> str:
    primitive = next(
        value
        for value in fingerprint["primitive_contracts"]
        if value["mesh"] == mesh_name
    )
    payload = {
        "mesh": primitive["mesh"],
        "mode": primitive["mode"],
        "material": primitive["material"],
        "attributes": primitive["attributes"],
        "mesh_order": fingerprint["mesh_order"],
        "skin_fingerprints": fingerprint["skin_fingerprints"],
        "material_order": fingerprint["material_order"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()


def _real_stream_identity(
    stream: dict[str, object],
    verified_source,
    fingerprint: dict[str, object],
) -> StreamIdentity:
    return StreamIdentity(
        stream_id=str(stream["mesh"]),
        verified_source_path=str(Path(verified_source.path).resolve()),
        verified_source_sha256=verified_source.actual_sha256,
        position_shape=tuple(map(int, np.asarray(stream["positions"]).shape)),
        index_topology_sha256=index_topology_digest(stream["triangles"]),
        non_position_semantic_sha256=_non_position_semantic_digest(
            fingerprint,
            str(stream["mesh"]),
        ),
    )


def _validate_common_frame_report(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for component, expected_skins in (("base", 4), ("thong", 1)):
        record = payload[component]["vanilla"]
        if record != {
            "status": "PASS_COMMON_FRAME",
            "source_bones": 82,
            "target_bones": 82,
            "target_skin_count": expected_skins,
            "missing_bones": [],
            "duplicate_bones": [],
            "all_finite": True,
            "minimum_determinant": record["minimum_determinant"],
            "maximum_determinant": record["maximum_determinant"],
            "maximum_condition_number": record["maximum_condition_number"],
        }:
            raise ValueError(f"COMMON_FRAME_REPORT_CONTRACT_MISMATCH:{component}")
        if (
            record["minimum_determinant"] <= 0.0
            or record["maximum_determinant"] <= 0.0
            or record["maximum_condition_number"] >= 1.00001
        ):
            raise ValueError(f"COMMON_FRAME_REPORT_NUMERIC_GATE_FAILURE:{component}")


def _validate_retained_vanilla_failures(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mode = payload["modes"]["vanilla"]
    retained: dict[str, dict[str, object]] = {}
    for component in ("base", "thong"):
        for stream in mode["components"][component]["attempts"][-1]["streams"]:
            retained[str(stream["mesh"])] = stream["topology"]
    expected_by_mesh = {
        BASE_STREAMS[0]: load_bard_contract().failure("vanilla", "BodyTop"),
        BASE_STREAMS[1]: load_bard_contract().failure("vanilla", "Footwear"),
        BASE_STREAMS[2]: load_bard_contract().failure("vanilla", "Pants"),
        BASE_STREAMS[3]: load_bard_contract().failure("vanilla", "Sleeves"),
        THONG_STREAM: load_bard_contract().failure("vanilla", "Thong"),
    }
    if set(retained) != set(expected_by_mesh):
        raise ValueError("RETAINED_VANILLA_FAILURE_STREAM_SET_MISMATCH")
    for mesh, expected in expected_by_mesh.items():
        actual = retained[mesh]
        if (
            actual["flipped_triangles"] != expected.flips
            or actual["new_zero_area_triangles"] != expected.new_zero_area
            or actual["triangles_below_25pct_area"] != expected.below_area_floor
            or actual["minimum_area_ratio"] != expected.minimum_area_ratio
        ):
            raise ValueError(f"RETAINED_VANILLA_FAILURE_MISMATCH:{mesh}")


def _validate_landmark_header(
    contract: LandmarkContract,
    *,
    component: str,
    verified_by_id: Mapping[str, object],
) -> None:
    source_input_id = "base_source_glb" if component == "base" else "thong_source_glb"
    if (
        contract.common_frame_report_sha256
        != verified_by_id["legacy_common_frame_report"].actual_sha256
        or contract.source_body_sha256 != verified_by_id["body_bcb_glb"].actual_sha256
        or contract.target_body_sha256 != verified_by_id["body_vanilla_glb"].actual_sha256
        or contract.source_component_sha256 != verified_by_id[source_input_id].actual_sha256
        or contract.search_alphas != SEARCH_ALPHAS
    ):
        raise ValueError(f"LANDMARK_HASH_LOCK_MISMATCH:{component}")
    expected_streams = BASE_STREAMS if component == "base" else (THONG_STREAM,)
    if tuple(stream.stream_id for stream in contract.streams) != expected_streams:
        raise ValueError(f"LANDMARK_STREAM_SET_MISMATCH:{component}")


def build_complete_mode_candidate(mode: str) -> CompletePairResult:
    """Build the hash-locked real Vanilla pair from the ignored explicit contracts."""
    if mode == "bcb":
        raise ValueError("BARD_BCB_PROTECTED_NO_REPLACEMENT")
    if mode != "vanilla":
        raise ValueError(f"BARD_UNSUPPORTED_CAGE_MODE:{mode}")
    verified = verify_evidence_inputs(load_local_configuration())
    verified_by_id = {item.input_id: item for item in verified}
    missing = _REAL_INPUT_IDS - set(verified_by_id)
    if missing:
        raise ValueError(f"HASH_LOCKED_CAGE_INPUTS_MISSING:{sorted(missing)}")
    _validate_common_frame_report(verified_by_id["legacy_common_frame_report"].path)
    _validate_retained_vanilla_failures(verified_by_id["legacy_offline_search_report"].path)
    base_contract = load_component_landmark_contract("base", mode)
    thong_contract = load_component_landmark_contract("thong", mode)
    _validate_landmark_header(
        base_contract,
        component="base",
        verified_by_id=verified_by_id,
    )
    _validate_landmark_header(
        thong_contract,
        component="thong",
        verified_by_id=verified_by_id,
    )
    landmark_contract_sha256 = hashlib.sha256(LANDMARKS_PATH.read_bytes()).hexdigest().upper()
    legacy, glb_contract, legacy_contracts = _load_exact_legacy_modules(verified_by_id)
    base_path = Path(verified_by_id["base_source_glb"].path).resolve()
    thong_path = Path(verified_by_id["thong_source_glb"].path).resolve()
    source_body_path = Path(verified_by_id["body_bcb_glb"].path).resolve()
    target_body_path = Path(verified_by_id["body_vanilla_glb"].path).resolve()
    if (
        (legacy_contracts.BARD_GLB_ROOT / base_path.name).resolve() != base_path
        or (legacy_contracts.BARD_GLB_ROOT / thong_path.name).resolve() != thong_path
        or (legacy_contracts.BODY_ROOT / source_body_path.name).resolve() != source_body_path
        or (legacy_contracts.BODY_ROOT / target_body_path.name).resolve() != target_body_path
    ):
        raise ValueError("LEGACY_PATH_CONTRACT_MISMATCH")

    base_source_body = legacy.pose_body_to_rig(source_body_path, base_path)
    base_target_body = legacy.pose_body_to_rig(target_body_path, base_path)
    thong_source_body = legacy.pose_body_to_rig(source_body_path, thong_path)
    thong_target_body = legacy.pose_body_to_rig(target_body_path, thong_path)
    for stream in base_contract.streams:
        validate_common_frame_landmarks(stream, base_source_body, base_target_body)
    for stream in thong_contract.streams:
        validate_common_frame_landmarks(stream, thong_source_body, thong_target_body)

    base_fingerprint = glb_contract.fingerprint_glb(base_path)
    thong_fingerprint = glb_contract.fingerprint_glb(thong_path)
    base_inputs: dict[str, CageStreamInput] = {}
    base_results: dict[str, StreamCageResult] = {}
    for stream in legacy.mesh_streams(base_path):
        stream_id = str(stream["mesh"])
        stream_input = CageStreamInput(
            component="base",
            stream_identity=_real_stream_identity(
                stream,
                verified_by_id["base_source_glb"],
                base_fingerprint,
            ),
            source_positions=np.asarray(stream["positions"]),
            faces=np.asarray(stream["triangles"]),
            landmark_stream=base_contract.streams_by_id[stream_id],
        )
        base_inputs[stream_id] = stream_input
        base_results[stream_id] = solve_stream_landmark_cage(stream_input)
    thong_stream = legacy.mesh_streams(thong_path)[0]
    thong_input = CageStreamInput(
        component="thong",
        stream_identity=_real_stream_identity(
            thong_stream,
            verified_by_id["thong_source_glb"],
            thong_fingerprint,
        ),
        source_positions=np.asarray(thong_stream["positions"]),
        faces=np.asarray(thong_stream["triangles"]),
        landmark_stream=thong_contract.streams_by_id[THONG_STREAM],
    )
    thong_result = solve_stream_landmark_cage(thong_input)
    return _complete_mode_candidate(
        mode,
        base_inputs,
        base_results,
        thong_input,
        thong_result,
        verified_input_sha256={
            input_id: item.actual_sha256
            for input_id, item in sorted(verified_by_id.items())
        },
        landmark_contract_sha256=landmark_contract_sha256,
    )
