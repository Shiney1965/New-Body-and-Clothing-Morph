"""Fail-closed coherent position solver and fixed candidate gates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np

from .geometry import (
    ParsedColladaGeometry,
    ParsedGlbSurface,
    RoiContract,
    SurfaceConstraints,
    TARGET_CLEARANCE_M,
    TriangleMesh,
    require_certified_targets,
)


PUBLISHED_MIN_AREA_RATIO = 0.5
PUBLISHED_MAX_AREA_RATIO = 2.0
INTERNAL_MIN_AREA_RATIO = 0.51
INTERNAL_MAX_AREA_RATIO = 1.99
INTERNAL_MIN_ORIENTATION_COSINE = 0.05
ZERO_AREA_EPSILON = 1e-12
SERIALIZATION_DECIMALS = 6
DEFERRED_NO_SOLUTION = "DEFERRED_NO_POSITION_ONLY_SOLUTION"


def _readonly(values: object, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(values, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


def _face_digest(faces: np.ndarray) -> str:
    canonical = np.asarray(faces, dtype="<i8")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest().upper()


@dataclass(frozen=True)
class CoverageContract:
    """Pristine-covered body samples that the candidate must keep covered."""

    points: np.ndarray
    normals: np.ndarray
    maximum_distance: float = 0.05

    def __post_init__(self) -> None:
        points = _readonly(self.points, np.float64)
        normals = _readonly(self.normals, np.float64)
        if points.ndim != 2 or points.shape[1] != 3 or normals.shape != points.shape:
            raise ValueError("coverage points and normals must have matching shape (N,3)")
        if not np.all(np.isfinite(points)) or not np.all(np.isfinite(normals)):
            raise ValueError("COVERAGE_VALUES_MUST_BE_FINITE")
        if self.maximum_distance <= 0 or not np.isfinite(self.maximum_distance):
            raise ValueError("coverage maximum distance must be finite and positive")
        lengths = np.linalg.norm(normals, axis=1)
        if np.any(np.abs(lengths - 1.0) > 1e-9):
            raise ValueError("coverage normals must be unit vectors")
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "normals", normals)


@dataclass(frozen=True)
class CandidateContract:
    """Strict production inputs; numeric acceptance thresholds stay fixed in code."""

    roi: RoiContract
    constraints: SurfaceConstraints
    fixed_cohort: CoverageContract | None = None

    def __post_init__(self) -> None:
        _require_exact_active_identity(self.roi, self.constraints)
        if self.constraints.body_mesh is None:
            raise ValueError("PRODUCTION_BODY_SURFACE_REQUIRED")
        if self.fixed_cohort is None or len(self.fixed_cohort.points) == 0:
            raise ValueError("PRODUCTION_FIXED_COHORT_REQUIRED")
        require_certified_targets(self.constraints)


@dataclass(frozen=True)
class SyntheticCandidateContract:
    """Explicit test-only contract that can never produce a production PASS."""

    roi: RoiContract
    constraints: SurfaceConstraints
    fixed_cohort: CoverageContract | None = None

    def __post_init__(self) -> None:
        _require_exact_active_identity(self.roi, self.constraints)


def _require_exact_active_identity(
    roi: RoiContract,
    constraints: SurfaceConstraints,
) -> None:
    if roi.active_ids != constraints.active_ids:
        raise ValueError("ACTIVE_VERTEX_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class Candidate:
    """Position-only output bound to its source topology and semantics."""

    positions: np.ndarray
    status: str
    moved_vertex_count: int
    source_position_count: int
    source_face_indices_sha256: str
    source_non_position_sha256: str | None
    accepted_step_scales: tuple[float, ...] = ()
    rejected_iteration_count: int = 0

    def __post_init__(self) -> None:
        positions = _readonly(self.positions, np.float64)
        if positions.ndim != 2 or positions.shape[1] != 3 or not np.all(np.isfinite(positions)):
            raise ValueError("candidate positions must have finite shape (N,3)")
        if len(positions) != self.source_position_count:
            raise ValueError("candidate position count differs from source")
        object.__setattr__(self, "positions", positions)

    @classmethod
    def from_positions(
        cls,
        source_positions: object,
        source_faces: object,
        candidate_positions: object,
        *,
        status: str,
        source_non_position_sha256: str | None = None,
        accepted_step_scales: tuple[float, ...] = (),
        rejected_iteration_count: int = 0,
    ) -> "Candidate":
        base = np.asarray(source_positions, dtype=np.float64)
        faces = np.asarray(source_faces, dtype=np.int64)
        positions = np.asarray(candidate_positions, dtype=np.float64)
        if base.ndim != 2 or base.shape[1] != 3 or positions.shape != base.shape:
            raise ValueError("source and candidate positions must have matching shape (N,3)")
        if faces.ndim != 2 or faces.shape[1] != 3:
            raise ValueError("source faces must have shape (M,3)")
        moved = np.linalg.norm(positions - base, axis=1) > 0.0
        return cls(
            positions=positions,
            status=status,
            moved_vertex_count=int(np.count_nonzero(moved)),
            source_position_count=len(base),
            source_face_indices_sha256=_face_digest(faces),
            source_non_position_sha256=source_non_position_sha256,
            accepted_step_scales=accepted_step_scales,
            rejected_iteration_count=rejected_iteration_count,
        )


@dataclass(frozen=True)
class _TopologyMetrics:
    flipped_faces: int
    new_zero_area_faces: int
    faces_below_published_area: int
    faces_above_published_area: int
    faces_below_internal_area: int
    faces_above_internal_area: int
    faces_below_orientation_cosine: int
    minimum_area_ratio: float
    maximum_area_ratio: float
    minimum_orientation_cosine: float

    @property
    def internal_passed(self) -> bool:
        return (
            self.flipped_faces == 0
            and self.new_zero_area_faces == 0
            and self.faces_below_internal_area == 0
            and self.faces_above_internal_area == 0
            and self.faces_below_orientation_cosine == 0
        )


@dataclass(frozen=True)
class GateReport:
    """Fixed, non-weakenable candidate evaluation after position serialization."""

    passed: bool
    production_passed: bool
    status: str
    topology_identity_equal: bool
    non_position_semantics_equal: bool
    position_count_equal: bool
    fixed_vertex_moves: int
    active_vertices_below_clearance: int
    active_surface_ambiguities: int
    moved_roi_vertices_below_clearance: int
    moved_roi_surface_ambiguities: int
    fixed_cohort_coverage_loss: int
    flipped_faces: int
    new_zero_area_faces: int
    faces_below_published_area: int
    faces_above_published_area: int
    faces_below_internal_area: int
    faces_above_internal_area: int
    faces_below_orientation_cosine: int
    minimum_area_ratio: float
    maximum_area_ratio: float
    minimum_orientation_cosine: float


def _source_arrays(
    source: object,
    *,
    production: bool,
) -> tuple[np.ndarray, np.ndarray, str | None, str | None]:
    if production:
        if not isinstance(source, ParsedColladaGeometry):
            raise TypeError("PRODUCTION_PARSED_COLLADA_SOURCE_REQUIRED")
        positions = source.positions
        faces = source.faces
        semantics = source.non_position_sha256
        parsed_face_digest = source.face_indices_sha256
        if not semantics:
            raise ValueError("PRODUCTION_SOURCE_SEMANTIC_IDENTITY_REQUIRED")
        if parsed_face_digest != _face_digest(faces):
            raise ValueError("PRODUCTION_SOURCE_FACE_IDENTITY_MISMATCH")
    elif isinstance(source, TriangleMesh):
        positions = source.positions
        faces = source.faces
        semantics = getattr(source, "non_position_sha256", None)
        parsed_face_digest = getattr(source, "face_indices_sha256", None)
    elif isinstance(source, tuple) and len(source) == 2:
        positions, faces = source
        semantics = None
        parsed_face_digest = None
    else:
        raise TypeError("source must be a TriangleMesh or (positions, faces) tuple")
    positions = np.asarray(positions, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("source positions must have shape (N,3)")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("source faces must have shape (M,3)")
    if np.any(faces < 0) or np.any(faces >= len(positions)):
        raise ValueError("source faces contain an out-of-range index")
    return positions, faces, semantics, parsed_face_digest


def _topology_metrics(base: np.ndarray, candidate: np.ndarray, faces: np.ndarray) -> _TopologyMetrics:
    before = base[faces]
    after = candidate[faces]
    before_vectors = np.cross(before[:, 1] - before[:, 0], before[:, 2] - before[:, 0])
    after_vectors = np.cross(after[:, 1] - after[:, 0], after[:, 2] - after[:, 0])
    before_areas = np.linalg.norm(before_vectors, axis=1)
    after_areas = np.linalg.norm(after_vectors, axis=1)
    if np.any(before_areas <= ZERO_AREA_EPSILON):
        raise ValueError("source contains a zero-area face")
    ratios = after_areas / before_areas
    orientation = np.einsum("ij,ij->i", before_vectors, after_vectors)
    cosine = np.divide(
        orientation,
        before_areas * after_areas,
        out=np.full_like(orientation, -np.inf),
        where=after_areas > ZERO_AREA_EPSILON,
    )
    return _TopologyMetrics(
        flipped_faces=int(np.count_nonzero(orientation < 0.0)),
        new_zero_area_faces=int(np.count_nonzero(after_areas <= ZERO_AREA_EPSILON)),
        faces_below_published_area=int(np.count_nonzero(ratios < PUBLISHED_MIN_AREA_RATIO)),
        faces_above_published_area=int(np.count_nonzero(ratios > PUBLISHED_MAX_AREA_RATIO)),
        faces_below_internal_area=int(np.count_nonzero(ratios < INTERNAL_MIN_AREA_RATIO)),
        faces_above_internal_area=int(np.count_nonzero(ratios > INTERNAL_MAX_AREA_RATIO)),
        faces_below_orientation_cosine=int(np.count_nonzero(cosine < INTERNAL_MIN_ORIENTATION_COSINE)),
        minimum_area_ratio=float(ratios.min()),
        maximum_area_ratio=float(ratios.max()),
        minimum_orientation_cosine=float(cosine.min()),
    )


def _adjacency(vertex_count: int, faces: np.ndarray) -> tuple[tuple[int, ...], ...]:
    neighbors = [set() for _ in range(vertex_count)]
    for a, b, c in faces:
        a, b, c = int(a), int(b), int(c)
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))
    return tuple(tuple(sorted(values)) for values in neighbors)


def solve_coherent_field(
    base: object,
    faces: object,
    roi: RoiContract,
    constraints: SurfaceConstraints,
    scale: float,
    fairness: float,
    iterations: int,
) -> Candidate:
    """Solve one simultaneous neighborhood field and reject illegal writes atomically."""
    if isinstance(base, ParsedColladaGeometry):
        base_positions = np.asarray(base.positions, dtype=np.float64)
        source_non_position_sha256 = base.non_position_sha256
        expected_face_digest = base.face_indices_sha256
    else:
        base_positions = np.asarray(base, dtype=np.float64)
        source_non_position_sha256 = None
        expected_face_digest = None
    checked_faces = np.asarray(faces, dtype=np.int64)
    if base_positions.ndim != 2 or base_positions.shape[1] != 3 or not np.all(np.isfinite(base_positions)):
        raise ValueError("base positions must have finite shape (N,3)")
    if checked_faces.ndim != 2 or checked_faces.shape[1] != 3:
        raise ValueError("faces must have shape (M,3)")
    if expected_face_digest is not None:
        if not source_non_position_sha256:
            raise ValueError("PRODUCTION_SOURCE_SEMANTIC_IDENTITY_REQUIRED")
        if expected_face_digest != _face_digest(checked_faces) or not np.array_equal(
            checked_faces, base.faces,
        ):
            raise ValueError("PRODUCTION_SOURCE_FACE_IDENTITY_MISMATCH")
    if not np.isfinite(scale) or scale <= 0.0 or scale > 1.0:
        raise ValueError("scale must be in (0,1]")
    if not np.isfinite(fairness) or fairness < 0.0:
        raise ValueError("fairness must be finite and nonnegative")
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    movable = np.asarray(roi.movable_ids, dtype=np.int64)
    active = np.asarray(constraints.active_ids, dtype=np.int64)
    _require_exact_active_identity(roi, constraints)
    if isinstance(base, ParsedColladaGeometry):
        require_certified_targets(constraints)
    adjacency = _adjacency(len(base_positions), checked_faces)
    target_displacements = {
        int(vertex_id): scale * (target - base_positions[int(vertex_id)])
        for vertex_id, target in zip(active, constraints.target_positions)
    }
    current = base_positions.copy()
    accepted_scales: list[float] = []
    rejected_iterations = 0
    for _ in range(iterations):
        displacement = current - base_positions
        proposed_displacement = displacement.copy()
        for vertex_id in movable:
            vertex_id = int(vertex_id)
            neighbors = adjacency[vertex_id]
            if not neighbors:
                continue
            neighbor_average = np.mean(displacement[np.asarray(neighbors, dtype=np.int64)], axis=0)
            if vertex_id in target_displacements:
                proposed_displacement[vertex_id] = (
                    target_displacements[vertex_id] + fairness * neighbor_average
                ) / (1.0 + fairness)
            else:
                proposed_displacement[vertex_id] = neighbor_average
        proposal = current.copy()
        proposal[movable] = base_positions[movable] + proposed_displacement[movable]
        accepted = None
        step = 1.0
        for _line_search in range(41):
            trial = current.copy()
            trial[movable] = np.round(
                current[movable] + step * (proposal[movable] - current[movable]),
                decimals=SERIALIZATION_DECIMALS,
            )
            if np.array_equal(trial, current):
                step *= 0.5
                continue
            if _topology_metrics(base_positions, trial, checked_faces).internal_passed:
                accepted = trial
                break
            step *= 0.5
        if accepted is None:
            rejected_iterations += 1
            break
        current = accepted
        accepted_scales.append(step)
    moved_count = int(np.count_nonzero(np.linalg.norm(current - base_positions, axis=1) > 0.0))
    status = "CANDIDATE" if moved_count else DEFERRED_NO_SOLUTION
    return Candidate.from_positions(
        base_positions,
        checked_faces,
        current,
        status=status,
        source_non_position_sha256=source_non_position_sha256,
        accepted_step_scales=tuple(accepted_scales),
        rejected_iteration_count=rejected_iterations,
    )


def _active_clearance_loss(candidate: np.ndarray, constraints: SurfaceConstraints) -> tuple[int, int]:
    active_positions = candidate[np.asarray(constraints.active_ids, dtype=np.int64)]
    if constraints.body_mesh is None:
        closest = constraints.closest_points
        normals = constraints.surface_normals
        ambiguous = constraints.ambiguous
    else:
        from .geometry import _closest_points
        closest, normals, _face_ids, _barycentric, _distances, ambiguous = _closest_points(
            active_positions, constraints.body_mesh,
        )
    signed = np.einsum("ij,ij->i", active_positions - closest, normals)
    below = (signed < TARGET_CLEARANCE_M - 1e-12) | ambiguous
    return int(np.count_nonzero(below)), int(np.count_nonzero(ambiguous))


def _clearance_losses(
    base: np.ndarray,
    candidate: np.ndarray,
    contract: CandidateContract | SyntheticCandidateContract,
) -> tuple[int, int, int, int]:
    """Check fixed active vertices and every moved ROI connector with one oracle."""
    active_ids = np.asarray(contract.constraints.active_ids, dtype=np.int64)
    if isinstance(contract.constraints.body_mesh, ParsedGlbSurface):
        from .geometry import query_signed_clearance

        movable = np.asarray(contract.roi.movable_ids, dtype=np.int64)
        moved_connectors = movable[
            np.linalg.norm(candidate[movable] - base[movable], axis=1) > 0.0
        ]
        active_set = set(int(value) for value in active_ids)
        connector_ids = np.asarray(
            [int(value) for value in moved_connectors if int(value) not in active_set],
            dtype=np.int64,
        )
        checked_ids = np.concatenate((active_ids, connector_ids))
        query = query_signed_clearance(candidate[checked_ids], contract.constraints.body_mesh)
        below = (query.signed_clearances < TARGET_CLEARANCE_M - 1e-12) | query.ambiguous
        active_count = len(active_ids)
        return (
            int(np.count_nonzero(below[:active_count])),
            int(np.count_nonzero(query.ambiguous[:active_count])),
            int(np.count_nonzero(below[active_count:])),
            int(np.count_nonzero(query.ambiguous[active_count:])),
        )
    active_below, active_ambiguous = _active_clearance_loss(candidate, contract.constraints)
    return active_below, active_ambiguous, 0, 0


def _coverage_loss(candidate: np.ndarray, faces: np.ndarray, contract: CoverageContract | None) -> int:
    if contract is None or len(contract.points) == 0:
        return 0
    from .geometry import _closest_points
    closest, _normals, _face_ids, _barycentric, distances, _ambiguous = _closest_points(
        contract.points, TriangleMesh(candidate, faces),
    )
    outward = np.einsum("ij,ij->i", closest - contract.points, contract.normals)
    return int(np.count_nonzero((outward <= 0.0) | (distances > contract.maximum_distance)))


def evaluate_candidate(
    source: object,
    candidate: Candidate,
    contract: CandidateContract | SyntheticCandidateContract,
) -> GateReport:
    """Evaluate every fixed topology, preservation, clearance, and coverage gate."""
    if isinstance(contract, CandidateContract):
        production = True
        require_certified_targets(contract.constraints)
    elif isinstance(contract, SyntheticCandidateContract):
        production = False
    else:
        raise TypeError("candidate contract type is not supported")
    _require_exact_active_identity(contract.roi, contract.constraints)
    base, faces, source_semantics, parsed_face_digest = _source_arrays(
        source, production=production,
    )
    if production and not candidate.source_non_position_sha256:
        raise ValueError("PRODUCTION_SOURCE_SEMANTIC_IDENTITY_REQUIRED")
    topology_equal = (
        candidate.source_face_indices_sha256 == _face_digest(faces)
        and (parsed_face_digest is None or candidate.source_face_indices_sha256 == parsed_face_digest)
    )
    semantics_equal = candidate.source_non_position_sha256 == source_semantics
    count_equal = candidate.source_position_count == len(base) == len(candidate.positions)
    if not count_equal:
        raise ValueError("candidate and source position counts differ")
    metrics = _topology_metrics(base, candidate.positions, faces)
    movable = set(contract.roi.movable_ids)
    fixed_ids = np.asarray([index for index in range(len(base)) if index not in movable], dtype=np.int64)
    fixed_moves = int(np.count_nonzero(
        np.linalg.norm(candidate.positions[fixed_ids] - base[fixed_ids], axis=1) > 0.0
    )) if len(fixed_ids) else 0
    clearance_loss, surface_ambiguities, moved_roi_clearance_loss, moved_roi_ambiguities = _clearance_losses(
        base, candidate.positions, contract,
    )
    coverage_loss = _coverage_loss(candidate.positions, faces, contract.fixed_cohort)
    passed = (
        candidate.status == "CANDIDATE"
        and topology_equal
        and semantics_equal
        and count_equal
        and fixed_moves == 0
        and clearance_loss == 0
        and moved_roi_clearance_loss == 0
        and coverage_loss == 0
        and metrics.internal_passed
        and metrics.faces_below_published_area == 0
        and metrics.faces_above_published_area == 0
    )
    production_passed = passed and production
    status = (
        "PRODUCTION_PASS" if production_passed
        else "SYNTHETIC_PASS" if passed
        else "PRODUCTION_FAIL" if production
        else "SYNTHETIC_FAIL"
    )
    return GateReport(
        passed=passed,
        production_passed=production_passed,
        status=status,
        topology_identity_equal=topology_equal,
        non_position_semantics_equal=semantics_equal,
        position_count_equal=count_equal,
        fixed_vertex_moves=fixed_moves,
        active_vertices_below_clearance=clearance_loss,
        active_surface_ambiguities=surface_ambiguities,
        moved_roi_vertices_below_clearance=moved_roi_clearance_loss,
        moved_roi_surface_ambiguities=moved_roi_ambiguities,
        fixed_cohort_coverage_loss=coverage_loss,
        flipped_faces=metrics.flipped_faces,
        new_zero_area_faces=metrics.new_zero_area_faces,
        faces_below_published_area=metrics.faces_below_published_area,
        faces_above_published_area=metrics.faces_above_published_area,
        faces_below_internal_area=metrics.faces_below_internal_area,
        faces_above_internal_area=metrics.faces_above_internal_area,
        faces_below_orientation_cosine=metrics.faces_below_orientation_cosine,
        minimum_area_ratio=metrics.minimum_area_ratio,
        maximum_area_ratio=metrics.maximum_area_ratio,
        minimum_orientation_cosine=metrics.minimum_orientation_cosine,
    )
