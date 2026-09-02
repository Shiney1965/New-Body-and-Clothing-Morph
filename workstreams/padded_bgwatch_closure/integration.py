"""Hash-locked real-input preparation and serialized candidate readback."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np

from .configuration import VerifiedInput, WORKSTREAM_ROOT, load_and_verify_canonical_inputs
from .geometry import (
    ParsedColladaGeometry,
    ParsedGlbSurface,
    build_surface_constraints,
    derive_minimal_roi,
    parse_collada_geometry,
    parse_glb_surface,
    serialize_collada_positions,
)
from .models import BASELINES
from .solver import Candidate, CandidateContract, CoverageContract
from .surface import exact_closest_points


def derive_original_active_ids(
    source_positions: object,
    body: ParsedGlbSurface,
) -> tuple[int, ...]:
    """Reproduce the retained confident signed-penetration active-set rule."""
    points = np.asarray(source_positions, dtype=np.float64)
    closest = exact_closest_points(points, body.positions, body.faces)
    face_vertices = body.faces[closest.face_ids]
    vertex_normals = body.vertex_normals[face_vertices]
    interpolated = np.einsum("ni,nij->nj", closest.barycentric, vertex_normals)
    lengths = np.linalg.norm(interpolated, axis=1)
    valid = lengths > 1e-12
    interpolated[valid] /= lengths[valid, None]
    signed = np.einsum("ij,ij->i", points - closest.closest_points, interpolated)
    active = np.flatnonzero((~closest.ambiguous) & valid & (signed < 0.0))
    return tuple(int(value) for value in active)


@dataclass(frozen=True)
class FixedCoverageEvidence:
    """The immutable pristine-covered body cohort and its production contract."""

    body_vertex_ids: tuple[int, ...]
    contract: CoverageContract


@dataclass(frozen=True)
class PreparedClosure:
    """All hash-verified real geometry and immutable production gates."""

    verified_source: VerifiedInput
    verified_body: VerifiedInput
    source: ParsedColladaGeometry
    body: ParsedGlbSurface
    body_vertex_normals_sha256: str
    active_ids: tuple[int, ...]
    coverage: FixedCoverageEvidence
    contract: CandidateContract


def derive_fixed_coverage_contract(
    source_positions: object,
    source_faces: object,
    body: ParsedGlbSurface,
) -> FixedCoverageEvidence:
    """Freeze in-bounds, outward, at-most-0.05 m pristine body samples."""
    positions = np.asarray(source_positions, dtype=np.float64)
    faces = np.asarray(source_faces, dtype=np.int64)
    bounds_min = positions.min(axis=0)
    bounds_max = positions.max(axis=0)
    in_bounds_ids = np.flatnonzero(np.all(
        (body.positions >= bounds_min) & (body.positions <= bounds_max), axis=1,
    ))
    if not len(in_bounds_ids):
        raise ValueError("PRISTINE_IN_BOUNDS_BODY_COHORT_EMPTY")
    queries = body.positions[in_bounds_ids]
    closest = exact_closest_points(queries, positions, faces)
    vectors = closest.closest_points - queries
    projection = np.einsum("ij,ij->i", vectors, body.vertex_normals[in_bounds_ids])
    retained = (projection > 0.0) & (closest.distances <= 0.05)
    body_vertex_ids = tuple(int(value) for value in in_bounds_ids[retained])
    if not body_vertex_ids:
        raise ValueError("PRISTINE_FIXED_COVERAGE_COHORT_EMPTY")
    selected = np.asarray(body_vertex_ids, dtype=np.int64)
    return FixedCoverageEvidence(
        body_vertex_ids=body_vertex_ids,
        contract=CoverageContract(
            points=body.positions[selected],
            normals=body.vertex_normals[selected],
            maximum_distance=0.05,
        ),
    )


def _ids_digest(values: tuple[int, ...]) -> str:
    return hashlib.sha256(
        np.asarray(values, dtype="<i8").tobytes(order="C"),
    ).hexdigest().upper()


def prepare_verified_closure(
    verified_source: VerifiedInput, verified_body: VerifiedInput,
) -> PreparedClosure:
    """Pure preparation shared by canonical loading and output-boundary replay."""
    source = parse_collada_geometry(verified_source)
    body = parse_glb_surface(verified_body)
    active_ids = derive_original_active_ids(source.positions, body)
    roi = derive_minimal_roi(source.positions, source.faces, active_ids)
    constraints = build_surface_constraints(source.positions, body, active_ids)
    coverage = derive_fixed_coverage_contract(source.positions, source.faces, body)
    contract = CandidateContract(roi, constraints, fixed_cohort=coverage.contract)
    return PreparedClosure(
        verified_source=verified_source,
        verified_body=verified_body,
        source=source,
        body=body,
        body_vertex_normals_sha256=hashlib.sha256(
            np.asarray(body.vertex_normals, dtype="<f8").tobytes(order="C"),
        ).hexdigest().upper(),
        active_ids=active_ids,
        coverage=coverage,
        contract=contract,
    )


def prepare_real_closure(workstream_root=WORKSTREAM_ROOT) -> PreparedClosure:
    """Hash before parse, then reconstruct and pin the exact real gate contract."""
    prepared = prepare_verified_closure(*load_and_verify_canonical_inputs(workstream_root))
    require_canonical_preparation(prepared)
    return prepared


def require_canonical_preparation(prepared: PreparedClosure) -> None:
    """Independently bind production evidence to the pinned Padded input profile."""
    if (
        prepared.verified_source.actual_sha256 != BASELINES.pristine_source_dae.sha256
        or prepared.verified_body.actual_sha256 != BASELINES.bcb_body_glb.sha256
    ):
        raise ValueError("CANONICAL_PREPARATION_INPUT_IDENTITY_MISMATCH")
    if (
        len(prepared.source.positions) != BASELINES.pristine_source_dae.vertex_count
        or len(prepared.source.faces) != BASELINES.pristine_source_dae.face_count
    ):
        raise ValueError("PRISTINE_SOURCE_LOD0_SHAPE_MISMATCH")
    if len(prepared.body.positions) != 10_800 or len(prepared.body.faces) != 18_828:
        raise ValueError("BCB_BODY_SURFACE_SHAPE_MISMATCH")
    if len(prepared.active_ids) != 593:
        raise ValueError("ORIGINAL_ACTIVE_VERTEX_COUNT_MISMATCH")
    if _ids_digest(prepared.active_ids) != "726ADFC0E20E00ADC0D8D4B6B0451D0939D7CF0FFCC1D904BFEAAE38A5220DF5":
        raise ValueError("ORIGINAL_ACTIVE_VERTEX_IDENTITY_MISMATCH")
    if len(prepared.coverage.body_vertex_ids) != 2_800:
        raise ValueError("FIXED_COVERAGE_COHORT_COUNT_MISMATCH")
    if _ids_digest(prepared.coverage.body_vertex_ids) != "A15EA818F106A23B44AC3DF26BD50AEC1FBBF3D4DCD157255E6FA0B2C95071E2":
        raise ValueError("FIXED_COVERAGE_COHORT_IDENTITY_MISMATCH")


def roundtrip_candidate(
    verified_source: VerifiedInput,
    parsed_source: ParsedColladaGeometry,
    candidate: Candidate,
) -> Candidate:
    """Serialize POSITION only, parse it back, and rebuild the gate candidate."""
    written = serialize_collada_positions(verified_source, parsed_source, candidate.positions)
    digest = hashlib.sha256(written).hexdigest().upper()
    readback = parse_collada_geometry(VerifiedInput(
        input_id="pristine_source_dae",
        content=written,
        byte_count=len(written),
        expected_sha256=digest,
        actual_sha256=digest,
    ))
    if readback.geometry_id != parsed_source.geometry_id:
        raise ValueError("READBACK_GEOMETRY_ID_MISMATCH")
    if readback.face_indices_sha256 != parsed_source.face_indices_sha256:
        raise ValueError("READBACK_FACE_IDENTITY_MISMATCH")
    if readback.non_position_sha256 != parsed_source.non_position_sha256:
        raise ValueError("READBACK_NON_POSITION_IDENTITY_MISMATCH")
    return Candidate.from_positions(
        parsed_source.positions,
        parsed_source.faces,
        readback.positions,
        status=candidate.status,
        source_non_position_sha256=readback.non_position_sha256,
        accepted_step_scales=candidate.accepted_step_scales,
        rejected_iteration_count=candidate.rejected_iteration_count,
    )
