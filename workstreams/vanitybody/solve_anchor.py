"""Bounded position-only clearance patches for approved VanityBody anchors."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .anchors import AnchorContract
from .clearance import Surface, measure_penetration


@dataclass(frozen=True)
class PositionPatch:
    indices: np.ndarray
    positions: np.ndarray
    displacements: np.ndarray
    clearance: float


def topology_signature(faces: np.ndarray) -> str:
    """Hash connectivity only; position-only corrections must leave it fixed."""
    canonical = np.asarray(faces, dtype="<i8")
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def semantic_non_position_hash(payload: bytes) -> str:
    """Hash caller-supplied non-position stream bytes without normalizing them."""
    return hashlib.sha256(payload).hexdigest()


def solve_local_clearance(
    contract: AnchorContract,
    body: Surface,
    garment_vertices: np.ndarray,
    *,
    clearance: float,
) -> PositionPatch:
    """Push only under-clearance vertices along the nearest body-surface normal.

    This intentionally refuses broad transforms: no vertex outside the declared
    groin box is changed, and no non-position payload is accepted or emitted.
    """
    report = measure_penetration(body, garment_vertices, contract.defect_region, clearance)
    deficient = report.signed_distances < clearance
    indices = report.regional_indices[deficient]
    if not len(indices):
        return PositionPatch(
            indices=np.empty(0, dtype=np.int64),
            positions=np.empty((0, 3), dtype=np.float64),
            displacements=np.empty((0, 3), dtype=np.float64),
            clearance=clearance,
        )

    deficits = clearance - report.signed_distances[deficient]
    displacements = report.nearest_surface_normals[deficient] * deficits[:, None]
    original = np.asarray(garment_vertices, dtype=np.float64)
    return PositionPatch(
        indices=indices.astype(np.int64, copy=False),
        positions=original[indices] + displacements,
        displacements=displacements,
        clearance=clearance,
    )


def apply_patch(vertices: np.ndarray, patch: PositionPatch) -> np.ndarray:
    """Produce a copy with only the explicitly listed POSITION triples replaced."""
    result = np.asarray(vertices, dtype=np.float64).copy()
    result[patch.indices] = patch.positions
    return result
