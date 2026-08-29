"""Deterministic, common-frame regional garment/body clearance checks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Surface:
    vertices: np.ndarray
    faces: np.ndarray


@dataclass(frozen=True)
class ClearanceReport:
    penetrating_vertices: int
    min_signed_distance: float
    max_penetration: float
    region_vertices: int
    regional_indices: np.ndarray
    nearest_surface_points: np.ndarray
    nearest_surface_normals: np.ndarray
    signed_distances: np.ndarray


def region_mask(points: np.ndarray, region: dict[str, float]) -> np.ndarray:
    """Select the stated common-frame defect box, without a global fallback."""
    return (
        (np.abs(points[:, 0]) <= region["x_abs_max"])
        & (points[:, 1] >= region["y_min"])
        & (points[:, 1] <= region["y_max"])
        & (points[:, 2] >= region["z_min"])
        & (points[:, 2] <= region["z_max"])
    )


def _closest_point_to_triangles(point: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the exact closest point and normal for each candidate triangle."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    ap = point - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    out = np.empty_like(a)
    chosen = np.zeros(len(a), dtype=bool)

    mask = (d1 <= 0.0) & (d2 <= 0.0)
    out[mask] = a[mask]
    chosen |= mask

    bp = point - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    mask = ~chosen & (d3 >= 0.0) & (d4 <= d3)
    out[mask] = b[mask]
    chosen |= mask

    vc = d1 * d4 - d3 * d2
    mask = ~chosen & (vc <= 0.0) & (d1 >= 0.0) & (d3 <= 0.0)
    v = np.divide(d1, d1 - d3, out=np.zeros_like(d1), where=(d1 != d3))
    out[mask] = a[mask] + v[mask, None] * ab[mask]
    chosen |= mask

    cp = point - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    mask = ~chosen & (d6 >= 0.0) & (d5 <= d6)
    out[mask] = c[mask]
    chosen |= mask

    vb = d5 * d2 - d1 * d6
    mask = ~chosen & (vb <= 0.0) & (d2 >= 0.0) & (d6 <= 0.0)
    w = np.divide(d2, d2 - d6, out=np.zeros_like(d2), where=(d2 != d6))
    out[mask] = a[mask] + w[mask, None] * ac[mask]
    chosen |= mask

    va = d3 * d6 - d5 * d4
    mask = ~chosen & (va <= 0.0) & ((d4 - d3) >= 0.0) & ((d5 - d6) >= 0.0)
    w = np.divide(d4 - d3, (d4 - d3) + (d5 - d6), out=np.zeros_like(d4), where=((d4 - d3) + (d5 - d6) != 0.0))
    out[mask] = b[mask] + w[mask, None] * (c[mask] - b[mask])
    chosen |= mask

    mask = ~chosen
    denom = va + vb + vc
    v = np.divide(vb, denom, out=np.zeros_like(vb), where=(denom != 0.0))
    w = np.divide(vc, denom, out=np.zeros_like(vc), where=(denom != 0.0))
    out[mask] = a[mask] + ab[mask] * v[mask, None] + ac[mask] * w[mask, None]

    normals = np.cross(ab, ac)
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-12):
        raise ValueError("body surface includes zero-area triangles")
    return out, normals / lengths[:, None]


def measure_penetration(
    body: Surface,
    garment_vertices: np.ndarray,
    region: dict[str, float],
    clearance_mm: float,
) -> ClearanceReport:
    """Measure signed body-surface clearance for only the declared defect region.

    The name is retained for the plan interface. Positions are measured in the
    common source coordinate frame; the caller supplies clearance in that frame.
    """
    if clearance_mm <= 0.0:
        raise ValueError("clearance must be positive")
    points = np.asarray(garment_vertices, dtype=np.float64)
    vertices = np.asarray(body.vertices, dtype=np.float64)
    faces = np.asarray(body.faces, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("garment vertices must be an Nx3 array")
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("body surface must be Nx3 vertices and Mx3 faces")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError("body faces reference an invalid vertex")

    indices = np.flatnonzero(region_mask(points, region))
    if not len(indices):
        raise ValueError("declared defect region selects no garment vertices")
    triangles = vertices[faces]
    closest = np.empty((len(indices), 3), dtype=np.float64)
    normals = np.empty((len(indices), 3), dtype=np.float64)
    signed = np.empty(len(indices), dtype=np.float64)
    for destination, index in enumerate(indices):
        candidates, candidate_normals = _closest_point_to_triangles(points[index], triangles)
        squared = np.einsum("ij,ij->i", candidates - points[index], candidates - points[index])
        nearest = int(np.argmin(squared))
        closest[destination] = candidates[nearest]
        normals[destination] = candidate_normals[nearest]
        signed[destination] = float(np.dot(points[index] - candidates[nearest], candidate_normals[nearest]))

    deficient = signed < clearance_mm
    return ClearanceReport(
        penetrating_vertices=int(np.count_nonzero(deficient)),
        min_signed_distance=float(signed.min()),
        max_penetration=float(np.maximum(clearance_mm - signed, 0.0).max()),
        region_vertices=len(indices),
        regional_indices=indices,
        nearest_surface_points=closest,
        nearest_surface_normals=normals,
        signed_distances=signed,
    )
