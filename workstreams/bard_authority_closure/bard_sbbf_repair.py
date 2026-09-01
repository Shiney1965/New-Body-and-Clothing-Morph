"""Deterministic one-ring repair for the retained Bard SBBF sleeve blocker."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

import numpy as np

from .contracts import load_bard_contract


PASS_REPAIRED = "PASS_REPAIRED"
PASS_UNCHANGED = "PASS_UNCHANGED"
METHOD_EXHAUSTED = "METHOD_SPECIFIC_EXHAUSTION"
PASS_PAIR = "PASS_OFFLINE_SBBF_PAIR"
SEARCH_STEPS = 4096
BASE_STREAMS = (
    "HUM_F_ARM_Bard_BodyTop_Mesh",
    "HUM_F_ARM_Bard_Footwear_Mesh",
    "HUM_F_ARM_Bard_Pants_Mesh",
    "HUM_F_ARM_Bard_Sleeves_Mesh",
)
THONG_STREAM = "HUM_F_ARM_Gortash_Body_Jacket_Mesh"
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


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
class StreamIdentity:
    stream_id: str
    verified_source_path: str
    verified_source_sha256: str
    position_shape: tuple[int, int]
    index_topology_sha256: str
    non_position_semantic_sha256: str

    def __post_init__(self) -> None:
        if not self.stream_id:
            raise ValueError("STREAM_ID_MISSING")
        if not Path(self.verified_source_path).is_absolute():
            raise ValueError("STREAM_SOURCE_PATH_NOT_ABSOLUTE")
        for value in (
            self.verified_source_sha256,
            self.index_topology_sha256,
            self.non_position_semantic_sha256,
        ):
            if SHA256_RE.fullmatch(value) is None:
                raise ValueError("STREAM_DIGEST_INVALID")
        if (
            len(self.position_shape) != 2
            or self.position_shape[0] <= 0
            or self.position_shape[1] != 3
        ):
            raise ValueError("STREAM_POSITION_SHAPE_INVALID")


@dataclass(frozen=True)
class SBBFPairContract:
    base_identities: tuple[StreamIdentity, ...]
    thong_identity: StreamIdentity

    def __post_init__(self) -> None:
        if tuple(identity.stream_id for identity in self.base_identities) != BASE_STREAMS:
            raise ValueError("SBBF_BASE_IDENTITY_SET_INVALID")
        if self.thong_identity.stream_id != THONG_STREAM:
            raise ValueError("SBBF_THONG_IDENTITY_INVALID")

    @property
    def base_by_id(self) -> dict[str, StreamIdentity]:
        return {identity.stream_id: identity for identity in self.base_identities}


@dataclass(frozen=True)
class StreamRevalidationContext:
    stream_identity: StreamIdentity
    source_positions: np.ndarray
    retained_candidate_positions: np.ndarray
    faces: np.ndarray
    expected_pre_metrics: TopologyMetrics
    expected_region: RepairRegion
    source_position_sha256: str
    retained_candidate_sha256: str
    threshold: float

    def __post_init__(self) -> None:
        for array in (self.source_positions, self.retained_candidate_positions, self.faces):
            if array.flags.writeable:
                raise ValueError("REVALIDATION_CONTEXT_ARRAY_MUTABLE")


@dataclass(frozen=True)
class SBBFPairRevalidationContext:
    pair_contract: SBBFPairContract
    base_streams: tuple[StreamRevalidationContext, ...]
    thong_stream: StreamRevalidationContext

    def __post_init__(self) -> None:
        if tuple(context.stream_identity.stream_id for context in self.base_streams) != BASE_STREAMS:
            raise ValueError("SBBF_BASE_REVALIDATION_SET_INVALID")
        if tuple(context.stream_identity for context in self.base_streams) != self.pair_contract.base_identities:
            raise ValueError("SBBF_BASE_REVALIDATION_IDENTITY_MISMATCH")
        if self.thong_stream.stream_identity != self.pair_contract.thong_identity:
            raise ValueError("SBBF_THONG_REVALIDATION_IDENTITY_MISMATCH")

    @property
    def base_by_id(self) -> dict[str, StreamRevalidationContext]:
        return {
            context.stream_identity.stream_id: context
            for context in self.base_streams
        }


@dataclass(frozen=True)
class CandidateResult:
    stream_identity: StreamIdentity
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
    pair_contract: SBBFPairContract
    revalidation_context: SBBFPairRevalidationContext
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


def index_topology_digest(faces: np.ndarray) -> str:
    """Digest the ordered TRIANGLES topology in one canonical uint32 encoding."""
    face_array = np.asarray(faces)
    if face_array.ndim != 2 or face_array.shape[1] != 3:
        raise ValueError("TRIANGLE_SHAPE_INVALID")
    if not np.issubdtype(face_array.dtype, np.integer):
        raise ValueError("TRIANGLE_DTYPE_INVALID")
    if len(face_array) and int(face_array.min()) < 0:
        raise ValueError("TRIANGLE_INDEX_OUT_OF_RANGE")
    canonical = face_array.astype("<u4", copy=False)
    digest = hashlib.sha256()
    digest.update(b"TRIANGLES\x00")
    digest.update(str(canonical.shape).encode("ascii"))
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest().upper()


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
    before_bytes = before_array.view(np.uint8).reshape((len(before_array), -1))
    after_bytes = after_array.view(np.uint8).reshape((len(after_array), -1))
    changed = np.flatnonzero((~movable) & np.any(before_bytes != after_bytes, axis=1))
    return GateReport(
        passed=not len(changed),
        changed_outside_rows=tuple(map(int, changed)),
    )


def _position_sha256(positions: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(positions, dtype="<f4").tobytes(order="C")).hexdigest().upper()


def _immutable_array(values: np.ndarray, dtype: str, shape: tuple[int, ...]) -> np.ndarray:
    encoded = np.asarray(values, dtype=dtype).tobytes(order="C")
    return np.frombuffer(encoded, dtype=dtype).reshape(shape)


def _exact_array_sha256(values: np.ndarray) -> str:
    array = np.asarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest().upper()


def build_stream_revalidation_context(
    source: np.ndarray,
    retained_candidate: np.ndarray,
    faces: np.ndarray,
    stream_identity: StreamIdentity,
    threshold: float = 0.25,
) -> StreamRevalidationContext:
    """Freeze the verified input rows and all pre-repair contracts for later admission."""
    source_array, candidate_array, face_array = _validated_arrays(
        source,
        retained_candidate,
        faces,
    )
    if stream_identity.position_shape != tuple(map(int, source_array.shape)):
        raise ValueError("STREAM_POSITION_SHAPE_MISMATCH")
    if stream_identity.index_topology_sha256 != index_topology_digest(face_array):
        raise ValueError("STREAM_INDEX_TOPOLOGY_DIGEST_MISMATCH")
    frozen_source = _immutable_array(source_array, "<f8", source_array.shape)
    frozen_candidate = _immutable_array(candidate_array, "<f8", candidate_array.shape)
    frozen_faces = _immutable_array(face_array, "<i8", face_array.shape)
    expected_pre = topology_metrics(
        frozen_source,
        frozen_candidate,
        frozen_faces,
        threshold,
    )
    expected_region = failing_face_neighborhood(
        frozen_source,
        frozen_candidate,
        frozen_faces,
        threshold,
    )
    return StreamRevalidationContext(
        stream_identity=stream_identity,
        source_positions=frozen_source,
        retained_candidate_positions=frozen_candidate,
        faces=frozen_faces,
        expected_pre_metrics=expected_pre,
        expected_region=expected_region,
        source_position_sha256=_exact_array_sha256(frozen_source),
        retained_candidate_sha256=_exact_array_sha256(frozen_candidate),
        threshold=threshold,
    )


def solve_local_area_constrained_positions(
    source: np.ndarray,
    candidate: np.ndarray,
    faces: np.ndarray,
    threshold: float = 0.25,
    *,
    stream_identity: StreamIdentity,
) -> CandidateResult:
    """Search a fixed grid for the least one-ring relaxation that passes every face gate."""
    source_array, candidate_array, face_array = _validated_arrays(source, candidate, faces)
    if stream_identity.position_shape != tuple(map(int, source_array.shape)):
        raise ValueError("STREAM_POSITION_SHAPE_MISMATCH")
    if stream_identity.index_topology_sha256 != index_topology_digest(face_array):
        raise ValueError("STREAM_INDEX_TOPOLOGY_DIGEST_MISMATCH")
    pre_metrics = topology_metrics(source_array, candidate_array, face_array, threshold)
    region = failing_face_neighborhood(source_array, candidate_array, face_array, threshold)
    baseline_f32 = np.asarray(candidate_array, dtype="<f4")

    if pre_metrics.passed:
        post_metrics = topology_metrics(source_array, baseline_f32, face_array, threshold)
        outside = verify_outside_region_exact(baseline_f32, baseline_f32, ())
        if post_metrics.passed:
            return CandidateResult(
                stream_identity=stream_identity,
                status=PASS_UNCHANGED,
                positions=baseline_f32,
                pre_metrics=pre_metrics,
                post_metrics=post_metrics,
                region=region,
                outside_gate=outside,
                blend_step=0,
                blend_steps=SEARCH_STEPS,
                position_sha256=_position_sha256(baseline_f32),
                exhaustion_reason=None,
            )

    movable = np.asarray(region.movable_vertex_indices, dtype=np.int64)
    completion_floor_blocked = False
    for step in range(1, SEARCH_STEPS + 1):
        weight = float(step) / float(SEARCH_STEPS)
        trial = baseline_f32.copy()
        blended = candidate_array[movable] + weight * (source_array[movable] - candidate_array[movable])
        trial[movable] = blended.astype("<f4")
        post_metrics = topology_metrics(source_array, trial, face_array, threshold)
        if not post_metrics.passed:
            continue
        outside = verify_outside_region_exact(baseline_f32, trial, region.movable_vertex_indices)
        if not outside.passed:
            continue
        if (SEARCH_STEPS - step) * 2 < SEARCH_STEPS:
            completion_floor_blocked = True
            continue
        return CandidateResult(
            stream_identity=stream_identity,
            status=PASS_REPAIRED,
            positions=trial,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            region=region,
            outside_gate=outside,
            blend_step=step,
            blend_steps=SEARCH_STEPS,
            position_sha256=_position_sha256(trial),
            exhaustion_reason=None,
        )

    return CandidateResult(
        stream_identity=stream_identity,
        status=METHOD_EXHAUSTED,
        positions=None,
        pre_metrics=pre_metrics,
        post_metrics=None,
        region=region,
        outside_gate=None,
        blend_step=None,
        blend_steps=SEARCH_STEPS,
        position_sha256=None,
        exhaustion_reason=(
            "ONE_RING_COMPLETION_FLOOR_EXHAUSTED"
            if completion_floor_blocked
            else "ONE_RING_AREA_CONSTRAINED_BLEND_EXHAUSTED"
        ),
    )


def _context_contract_valid(context: StreamRevalidationContext) -> bool:
    try:
        source, candidate, faces = _validated_arrays(
            context.source_positions,
            context.retained_candidate_positions,
            context.faces,
        )
        recomputed_pre = topology_metrics(source, candidate, faces, context.threshold)
        recomputed_region = failing_face_neighborhood(source, candidate, faces, context.threshold)
    except (TypeError, ValueError):
        return False
    return (
        not context.source_positions.flags.writeable
        and not context.retained_candidate_positions.flags.writeable
        and not context.faces.flags.writeable
        and context.stream_identity.position_shape == tuple(map(int, source.shape))
        and context.stream_identity.index_topology_sha256 == index_topology_digest(faces)
        and context.source_position_sha256 == _exact_array_sha256(context.source_positions)
        and context.retained_candidate_sha256 == _exact_array_sha256(
            context.retained_candidate_positions
        )
        and context.expected_pre_metrics == recomputed_pre
        and context.expected_region == recomputed_region
    )


def _context_cache_key(context: StreamRevalidationContext) -> tuple[object, ...]:
    return (
        context.stream_identity,
        context.source_position_sha256,
        context.retained_candidate_sha256,
        _exact_array_sha256(context.faces),
        context.threshold,
    )


def _canonical_result(
    context: StreamRevalidationContext,
    cache: dict[tuple[object, ...], CandidateResult],
) -> CandidateResult:
    """Rerun the fixed-grid solver only from frozen verified context data."""
    key = _context_cache_key(context)
    if key not in cache:
        cache[key] = solve_local_area_constrained_positions(
            context.source_positions,
            context.retained_candidate_positions,
            context.faces,
            context.threshold,
            stream_identity=context.stream_identity,
        )
    return cache[key]


def _candidate_result_exact(
    supplied: CandidateResult,
    canonical: CandidateResult,
) -> bool:
    if (
        supplied.stream_identity != canonical.stream_identity
        or supplied.status != canonical.status
        or supplied.pre_metrics != canonical.pre_metrics
        or supplied.post_metrics != canonical.post_metrics
        or supplied.region != canonical.region
        or supplied.outside_gate != canonical.outside_gate
        or supplied.blend_step != canonical.blend_step
        or supplied.blend_steps != canonical.blend_steps
        or supplied.position_sha256 != canonical.position_sha256
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
        and canonical_positions.dtype == np.dtype("<f4")
        and supplied_positions.shape == canonical_positions.shape
        and supplied_positions.tobytes(order="C") == canonical_positions.tobytes(order="C")
    )


def _result_admitted(
    result: CandidateResult,
    context: StreamRevalidationContext,
    canonical: CandidateResult,
) -> bool:
    """Recompute every admission fact from verified rows; trust no result summary."""
    if not _context_contract_valid(context) or result.stream_identity != context.stream_identity:
        return False
    if not _candidate_result_exact(result, canonical):
        return False
    if result.status not in {PASS_REPAIRED, PASS_UNCHANGED}:
        return False
    if result.exhaustion_reason is not None or result.positions is None:
        return False
    positions = np.asarray(result.positions)
    if positions.dtype != np.dtype("<f4"):
        return False
    if positions.shape != context.stream_identity.position_shape:
        return False
    if not np.isfinite(positions).all():
        return False
    if result.position_sha256 != _position_sha256(positions):
        return False
    if result.blend_steps != SEARCH_STEPS or result.blend_step is None:
        return False
    if result.blend_step < 0 or result.blend_step > SEARCH_STEPS:
        return False
    if (SEARCH_STEPS - result.blend_step) * 2 < SEARCH_STEPS:
        return False

    source = context.source_positions
    retained = context.retained_candidate_positions
    faces = context.faces
    recomputed_pre = topology_metrics(source, retained, faces, context.threshold)
    recomputed_region = failing_face_neighborhood(source, retained, faces, context.threshold)
    if (
        result.pre_metrics != recomputed_pre
        or result.region != recomputed_region
        or recomputed_pre != context.expected_pre_metrics
        or recomputed_region != context.expected_region
    ):
        return False
    recomputed_post = topology_metrics(source, positions, faces, context.threshold)
    recomputed_outside = verify_outside_region_exact(
        retained,
        positions,
        recomputed_region.movable_vertex_indices,
    )
    if (
        result.post_metrics != recomputed_post
        or result.outside_gate != recomputed_outside
        or not recomputed_post.passed
        or not recomputed_outside.passed
    ):
        return False
    retained_f32 = np.asarray(retained, dtype="<f4")
    if result.status == PASS_UNCHANGED:
        return (
            result.blend_step == 0
            and recomputed_pre.passed
            and positions.tobytes(order="C") == retained_f32.tobytes(order="C")
        )
    return (
        result.blend_step > 0
        and not recomputed_pre.passed
        and bool(recomputed_region.failing_face_indices)
    )


def _exhausted_pair(
    base_results: Mapping[str, CandidateResult],
    thong_result: CandidateResult,
    pair_contract: SBBFPairContract,
    revalidation_context: SBBFPairRevalidationContext,
    reason: str,
) -> CompletePairResult:
    return CompletePairResult(
        status=METHOD_EXHAUSTED,
        replacement_routes=0,
        candidate_positions=None,
        position_digest=None,
        exhaustion_reason=reason,
        pair_contract=pair_contract,
        revalidation_context=revalidation_context,
        base_results=base_results,
        thong_result=thong_result,
    )


def complete_sbbf_pair(
    base_results: Mapping[str, CandidateResult],
    thong_result: CandidateResult,
    pair_contract: SBBFPairContract,
    revalidation_context: SBBFPairRevalidationContext,
) -> CompletePairResult:
    """Admit no output unless the exact four-stream base and thong pair both pass."""
    load_bard_contract().require_emittable_pair("sbbf", ("base", "thong"))
    if (
        revalidation_context.pair_contract != pair_contract
        or tuple(context.stream_identity for context in revalidation_context.base_streams)
        != pair_contract.base_identities
        or revalidation_context.thong_stream.stream_identity != pair_contract.thong_identity
    ):
        return _exhausted_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
            "SBBF_REVALIDATION_CONTEXT_CONTRACT_FAILURE",
        )
    if set(base_results) != set(BASE_STREAMS):
        return _exhausted_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
            "SBBF_BASE_STREAM_SET_INCOMPLETE",
        )
    expected_base = pair_contract.base_by_id
    canonical_cache: dict[tuple[object, ...], CandidateResult] = {}
    for name in BASE_STREAMS:
        result = base_results[name]
        if result.stream_identity != expected_base[name] or result.stream_identity.stream_id != name:
            return _exhausted_pair(
                base_results,
                thong_result,
                pair_contract,
                revalidation_context,
                f"SBBF_STREAM_IDENTITY_MISMATCH:{name}",
            )
        if result.blend_steps != SEARCH_STEPS:
            return _exhausted_pair(
                base_results,
                thong_result,
                pair_contract,
                revalidation_context,
                f"SBBF_SEARCH_INVARIANT_FAILURE:{name}",
            )
        if result.blend_step is None or (SEARCH_STEPS - result.blend_step) * 2 < SEARCH_STEPS:
            return _exhausted_pair(
                base_results,
                thong_result,
                pair_contract,
                revalidation_context,
                f"SBBF_COMPLETION_FLOOR_FAILURE:{name}",
            )
        context = revalidation_context.base_by_id[name]
        if not _result_admitted(result, context, _canonical_result(context, canonical_cache)):
            return _exhausted_pair(
                base_results,
                thong_result,
                pair_contract,
                revalidation_context,
                f"SBBF_STREAM_REVALIDATION_FAILURE:{name}",
            )
    if (
        thong_result.stream_identity != pair_contract.thong_identity
        or thong_result.stream_identity.stream_id != THONG_STREAM
    ):
        return _exhausted_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
            "SBBF_STREAM_IDENTITY_MISMATCH:thong",
        )
    if thong_result.blend_steps != SEARCH_STEPS:
        return _exhausted_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
            "SBBF_SEARCH_INVARIANT_FAILURE:thong",
        )
    if (
        thong_result.blend_step is None
        or (SEARCH_STEPS - thong_result.blend_step) * 2 < SEARCH_STEPS
    ):
        return _exhausted_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
            "SBBF_COMPLETION_FLOOR_FAILURE:thong",
        )
    if not _result_admitted(
        thong_result,
        revalidation_context.thong_stream,
        _canonical_result(revalidation_context.thong_stream, canonical_cache),
    ):
        return _exhausted_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
            "SBBF_THONG_GATE_FAILURE",
        )

    positions = {
        "base": {name: np.asarray(base_results[name].positions, dtype="<f4") for name in BASE_STREAMS},
        "thong": {THONG_STREAM: np.asarray(thong_result.positions, dtype="<f4")},
    }
    return CompletePairResult(
        status=PASS_PAIR,
        replacement_routes=2,
        candidate_positions=positions,
        position_digest=_position_digest(positions),
        exhaustion_reason=None,
        pair_contract=pair_contract,
        revalidation_context=revalidation_context,
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


def _position_digest(positions: Mapping[str, Mapping[str, np.ndarray]]) -> str:
    digest = hashlib.sha256()
    for component in ("base", "thong"):
        for stream in sorted(positions[component]):
            digest.update(component.encode("utf-8"))
            digest.update(stream.encode("utf-8"))
            digest.update(np.asarray(positions[component][stream], dtype="<f4").tobytes(order="C"))
    return digest.hexdigest().upper()


def _validate_offline_result(result: CompletePairResult) -> None:
    canonical = complete_sbbf_pair(
        result.base_results,
        result.thong_result,
        result.pair_contract,
        result.revalidation_context,
    )
    if result.status == METHOD_EXHAUSTED:
        if (
            canonical.status != METHOD_EXHAUSTED
            or result.replacement_routes != 0
            or result.candidate_positions is not None
            or result.position_digest is not None
            or result.exhaustion_reason != canonical.exhaustion_reason
        ):
            raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
        return
    if (
        result.status != PASS_PAIR
        or canonical.status != PASS_PAIR
        or result.replacement_routes != 2
        or result.candidate_positions is None
        or result.position_digest is None
        or result.exhaustion_reason is not None
    ):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if set(result.candidate_positions) != {"base", "thong"}:
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if set(result.candidate_positions["base"]) != set(BASE_STREAMS):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if set(result.candidate_positions["thong"]) != {THONG_STREAM}:
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    for component in ("base", "thong"):
        for stream, expected in canonical.candidate_positions[component].items():
            actual = np.asarray(result.candidate_positions[component][stream], dtype="<f4")
            if actual.shape != expected.shape or actual.tobytes(order="C") != expected.tobytes(order="C"):
                raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if result.position_digest != canonical.position_digest:
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")
    if result.position_digest != _position_digest(result.candidate_positions):
        raise ValueError("OFFLINE_RESULT_NOT_EMITTABLE")


def _candidate_payload(result: CandidateResult) -> dict[str, object]:
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
        "pre_metrics": _metrics_payload(result.pre_metrics),
        "post_metrics": _metrics_payload(result.post_metrics),
        "failing_face_indices": list(result.region.failing_face_indices),
        "seed_vertex_indices": list(result.region.seed_vertex_indices),
        "movable_vertex_indices": list(result.region.movable_vertex_indices),
        "affected_face_indices": list(result.region.affected_face_indices),
        "blend_step": result.blend_step,
        "blend_steps": result.blend_steps,
        "retained_completion": (
            None
            if result.blend_step is None
            else {
                "numerator": SEARCH_STEPS - result.blend_step,
                "denominator": SEARCH_STEPS,
            }
        ),
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
    _validate_offline_result(result)
    report_path = output_directory / "bard_sbbf_repair_report.json"
    prior_candidate_path = output_directory / "bard_sbbf_candidate_positions.npz"
    if report_path.exists() or prior_candidate_path.exists():
        raise FileExistsError(f"OFFLINE_OUTPUT_ALREADY_EXISTS:{output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    candidate_path: Path | None = None
    if result.candidate_positions is not None:
        candidate_path = prior_candidate_path
        arrays = {
            f"{component}::{stream}": positions
            for component, streams in result.candidate_positions.items()
            for stream, positions in streams.items()
        }
        np.savez(candidate_path, **arrays)
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
