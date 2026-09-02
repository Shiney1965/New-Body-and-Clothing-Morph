"""Chunked exact point-to-triangle queries used by real closure preparation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ExactClosestPoints:
    closest_points: np.ndarray
    face_ids: np.ndarray
    barycentric: np.ndarray
    distances: np.ndarray
    ambiguous: np.ndarray


def _segment_projection(points, start, end):
    edge = end - start
    denominator = np.einsum("ij,ij->i", edge, edge)
    numerator = np.einsum(
        "mnj,nj->mn", points[:, None, :] - start[None, :, :], edge,
    )
    factor = np.divide(
        numerator,
        denominator[None, :],
        out=np.zeros_like(numerator),
        where=denominator[None, :] > 1e-30,
    )
    factor = np.clip(factor, 0.0, 1.0)
    return start[None, :, :] + factor[:, :, None] * edge[None, :, :], factor


def _block_candidates(points: np.ndarray, triangles: np.ndarray, valid: np.ndarray):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    face_vectors = np.cross(ab, ac)
    normal_sq = np.einsum("ij,ij->i", face_vectors, face_vectors)
    ap = points[:, None, :] - a[None, :, :]
    plane_factor = np.divide(
        np.einsum("mnj,nj->mn", ap, face_vectors),
        normal_sq[None, :],
        out=np.zeros((len(points), len(triangles))),
        where=normal_sq[None, :] > 1e-30,
    )
    projected = points[:, None, :] - plane_factor[:, :, None] * face_vectors[None, :, :]
    d00 = np.einsum("ij,ij->i", ab, ab)
    d01 = np.einsum("ij,ij->i", ab, ac)
    d11 = np.einsum("ij,ij->i", ac, ac)
    v2 = projected - a[None, :, :]
    d20 = np.einsum("mnj,nj->mn", v2, ab)
    d21 = np.einsum("mnj,nj->mn", v2, ac)
    denominator = d00 * d11 - d01 * d01
    bary_b = np.divide(
        d11[None, :] * d20 - d01[None, :] * d21,
        denominator[None, :],
        out=np.zeros_like(d20),
        where=np.abs(denominator[None, :]) > 1e-30,
    )
    bary_c = np.divide(
        d00[None, :] * d21 - d01[None, :] * d20,
        denominator[None, :],
        out=np.zeros_like(d20),
        where=np.abs(denominator[None, :]) > 1e-30,
    )
    bary_a = 1.0 - bary_b - bary_c
    face_bary = np.stack([bary_a, bary_b, bary_c], axis=2)
    face_inside = np.all(face_bary >= -1e-12, axis=2) & valid[None, :]
    ab_point, ab_factor = _segment_projection(points, a, b)
    bc_point, bc_factor = _segment_projection(points, b, c)
    ca_point, ca_factor = _segment_projection(points, c, a)
    ab_bary = np.stack([1.0 - ab_factor, ab_factor, np.zeros_like(ab_factor)], axis=2)
    bc_bary = np.stack([np.zeros_like(bc_factor), 1.0 - bc_factor, bc_factor], axis=2)
    ca_bary = np.stack([ca_factor, np.zeros_like(ca_factor), 1.0 - ca_factor], axis=2)
    candidate_points = np.stack([projected, ab_point, bc_point, ca_point], axis=2)
    candidate_bary = np.stack([face_bary, ab_bary, bc_bary, ca_bary], axis=2)
    distance_sq = np.einsum(
        "mnkj,mnkj->mnk",
        candidate_points - points[:, None, None, :],
        candidate_points - points[:, None, None, :],
    )
    distance_sq[:, :, 0] = np.where(face_inside, distance_sq[:, :, 0], np.inf)
    distance_sq[:, ~valid, :] = np.inf
    choice = np.argmin(distance_sq, axis=2)
    chosen_distance = np.take_along_axis(distance_sq, choice[:, :, None], axis=2)[:, :, 0]
    chosen_points = np.take_along_axis(
        candidate_points, choice[:, :, None, None], axis=2,
    )[:, :, 0, :]
    chosen_bary = np.take_along_axis(
        candidate_bary, choice[:, :, None, None], axis=2,
    )[:, :, 0, :]
    return chosen_distance, chosen_points, chosen_bary


def exact_closest_points(
    points: object,
    vertices: object,
    faces: object,
    *,
    point_chunk: int = 32,
    face_chunk: int = 2048,
    ambiguity_tolerance: float = 1e-9,
) -> ExactClosestPoints:
    """Return exact closest triangles with the retained legacy ambiguity rule."""
    points = np.asarray(points, dtype=np.float64)
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points must have shape (N,3)")
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("vertices must have shape (N,3)")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("faces must have shape (N,3)")
    triangles = vertices[faces]
    vectors = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0],
    )
    valid = np.linalg.norm(vectors, axis=1) > 1e-15
    if not np.any(valid):
        raise ValueError("surface has no nondegenerate triangle")
    out_points = np.empty_like(points)
    out_barycentric = np.empty_like(points)
    out_faces = np.empty(len(points), dtype=np.int64)
    out_best = np.empty(len(points), dtype=np.float64)
    out_second = np.empty(len(points), dtype=np.float64)
    for point_start in range(0, len(points), point_chunk):
        block = points[point_start:point_start + point_chunk]
        count = len(block)
        rows = np.arange(count)
        best = np.full(count, np.inf)
        second = np.full(count, np.inf)
        best_points = np.full((count, 3), np.nan)
        best_barycentric = np.full((count, 3), np.nan)
        best_faces = np.full(count, -1, dtype=np.int64)
        for face_start in range(0, len(faces), face_chunk):
            face_end = min(len(faces), face_start + face_chunk)
            distances, candidate_points, candidate_barycentric = _block_candidates(
                block, triangles[face_start:face_end], valid[face_start:face_end],
            )
            local_ids = np.argmin(distances, axis=1)
            local_best = distances[rows, local_ids]
            local_second = (
                np.partition(distances, 1, axis=1)[:, 1]
                if distances.shape[1] > 1 else np.full(count, np.inf)
            )
            replace = local_best < best
            second = np.where(
                replace, np.minimum(best, local_second), np.minimum(second, local_best),
            )
            best = np.where(replace, local_best, best)
            best_points[replace] = candidate_points[rows[replace], local_ids[replace]]
            best_barycentric[replace] = candidate_barycentric[rows[replace], local_ids[replace]]
            best_faces[replace] = face_start + local_ids[replace]
        if np.any(~np.isfinite(best)):
            raise ValueError("surface has no valid triangle for one or more points")
        target = slice(point_start, point_start + count)
        out_points[target] = best_points
        out_barycentric[target] = best_barycentric
        out_faces[target] = best_faces
        out_best[target] = best
        out_second[target] = second
    distances = np.sqrt(out_best)
    return ExactClosestPoints(
        closest_points=out_points,
        face_ids=out_faces,
        barycentric=out_barycentric,
        distances=distances,
        ambiguous=(np.sqrt(out_second) - distances) <= ambiguity_tolerance,
    )
