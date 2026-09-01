"""Synthetic contracts for the coherent Padded BG Watch position solver."""

from __future__ import annotations

import hashlib
import json
import struct

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure.configuration import VerifiedInput
from workstreams.padded_bgwatch_closure.geometry import (
    ParsedColladaGeometry,
    SurfaceConstraints,
    TriangleMesh,
    build_surface_constraints,
    derive_minimal_roi,
    parse_collada_geometry,
    parse_glb_surface,
)
from workstreams.padded_bgwatch_closure.solver import (
    Candidate,
    CandidateContract,
    CoverageContract,
    SyntheticCandidateContract,
    evaluate_candidate,
    solve_coherent_field,
)


def _verified(input_id: str, content: bytes) -> VerifiedInput:
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(input_id, content, len(content), digest, digest)


def _minimal_glb() -> bytes:
    positions = struct.pack("<9f", 0, 0, 0, 0, 1, 0, 0, 0, 1)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + indices
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [{"name": "body", "primitives": [{
            "attributes": {"POSITION": 0}, "indices": 1, "mode": 4,
        }]}],
        "nodes": [{"name": "body_node", "mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    encoded_json = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded_json += b" " * ((4 - len(encoded_json) % 4) % 4)
    total = 12 + 8 + len(encoded_json) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(encoded_json), 0x4E4F534A)
        + encoded_json
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def test_geometry_parsers_consume_verified_content_bytes():
    """Catches a parser reopening a path or losing DAE/GLB topology semantics."""
    dae = b"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema">
  <library_geometries><geometry id="lod0"><mesh>
    <source id="lod0-positions"><float_array id="lod0-positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array><technique_common><accessor source="#lod0-positions-array" count="3" stride="3"/></technique_common></source>
    <source id="lod0-normal"><float_array id="lod0-normal-array" count="3">0 0 1</float_array><technique_common><accessor source="#lod0-normal-array" count="1" stride="3"/></technique_common></source>
    <vertices id="lod0-vertices"><input semantic="POSITION" source="#lod0-positions"/></vertices>
    <triangles count="1" material="cloth"><input semantic="VERTEX" source="#lod0-vertices" offset="0"/><input semantic="NORMAL" source="#lod0-normal" offset="1"/><p>0 0 1 0 2 0</p></triangles>
  </mesh></geometry></library_geometries>
</COLLADA>"""

    garment = parse_collada_geometry(_verified("pristine_source_dae", dae))
    body = parse_glb_surface(_verified("bcb_body_glb", _minimal_glb()))

    assert garment.geometry_id == "lod0"
    assert garment.positions.tolist() == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert garment.faces.tolist() == [[0, 1, 2]]
    assert garment.non_position_sha256 == "12D30A0B8846A9CE163A969EE6AFBB001ADEDA068D80046BD02B4E7221BCF652"
    assert body.positions.tolist() == [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert body.faces.tolist() == [[0, 1, 2]]
    assert garment.positions.flags.writeable is False
    assert body.faces.flags.writeable is False


def test_minimal_roi_connects_active_vertices_and_fixes_one_ring_boundary():
    """Catches disconnected active updates or a movable exterior boundary."""
    positions = np.array([
        [0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0], [1, 1, 0], [2, 1, 0],
    ], dtype=float)
    faces = np.array([[0, 1, 4], [1, 2, 4], [2, 5, 4], [2, 3, 5]], dtype=int)

    roi = derive_minimal_roi(positions, faces, active_ids=[0, 3])

    assert roi.active_ids == (0, 3)
    assert roi.movable_ids == (0, 1, 2, 3)
    assert roi.boundary_ids == (4, 5)
    assert roi.roi_ids == (0, 1, 2, 3, 4, 5)


def test_surface_constraints_use_exact_closest_triangle_not_nearest_vertex():
    """Catches regression from exact closest-surface projection to vertex snapping."""
    base = np.array([[0.25, 0.25, -0.2], [2.0, 2.0, 2.0]], dtype=float)
    body = TriangleMesh(
        positions=np.array([[0, 0, 0], [0, 1, 0], [1, 0, 0]], dtype=float),
        faces=np.array([[0, 1, 2]], dtype=int),
    )

    constraints = build_surface_constraints(base, body, active_ids=[0])

    assert constraints.active_ids == (0,)
    np.testing.assert_allclose(constraints.closest_points, [[0.25, 0.25, 0.0]], atol=1e-12)
    np.testing.assert_allclose(constraints.surface_normals, [[0.0, 0.0, -1.0]], atol=1e-12)
    np.testing.assert_allclose(constraints.signed_clearances, [0.2], atol=1e-12)
    np.testing.assert_allclose(constraints.target_positions, [[0.25, 0.25, -0.001]], atol=1e-12)
    assert constraints.face_ids.tolist() == [0]
    np.testing.assert_allclose(constraints.barycentric, [[0.5, 0.25, 0.25]], atol=1e-12)


def test_candidate_clearance_requeries_exact_surface_after_tangential_move():
    """Catches evaluating clearance only on the active vertex's original closest plane."""
    base = np.array([
        [0.2, 0.2, -0.1], [2.0, 0.0, -0.1], [0.0, 2.0, -0.1],
    ], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    body = TriangleMesh(
        positions=np.array([
            [0, 0, 0], [2, 0, 0], [0, 2, 0],
            [1, 0, 0], [1, 0, 2], [1, 2, 0],
        ], dtype=float),
        faces=np.array([[0, 1, 2], [3, 4, 5]], dtype=int),
    )
    roi = derive_minimal_roi(base, faces, active_ids=[0])
    constraints = build_surface_constraints(base, body, active_ids=[0])
    moved = base.copy()
    moved[0] = [0.9995, 0.2, 0.001]
    candidate = Candidate.from_positions(base, faces, moved, status="CANDIDATE")

    report = evaluate_candidate((base, faces), candidate, SyntheticCandidateContract(roi, constraints))

    assert report.active_vertices_below_clearance == 1
    assert report.passed is False


def test_ambiguous_closest_surface_is_retained_and_fails_clearance_gate():
    """Catches arbitrary face ordering treating an equidistant opposite surface as clear."""
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    body = TriangleMesh(
        positions=np.array([
            [-2, -2, -0.1], [2, -2, -0.1], [-2, 2, -0.1],
            [-2, -2, 0.1], [-2, 2, 0.1], [2, -2, 0.1],
        ], dtype=float),
        faces=np.array([[0, 1, 2], [3, 4, 5]], dtype=int),
    )
    roi = derive_minimal_roi(base, faces, active_ids=[0])
    constraints = build_surface_constraints(base, body, active_ids=[0])
    candidate = Candidate.from_positions(base, faces, base, status="CANDIDATE")

    report = evaluate_candidate((base, faces), candidate, SyntheticCandidateContract(roi, constraints))

    assert constraints.ambiguous.tolist() == [True]
    assert report.active_surface_ambiguities == 1
    assert report.active_vertices_below_clearance == 1
    assert report.passed is False


def test_coplanar_shared_edge_tie_is_same_sheet_not_ambiguous():
    """Catches a harmless triangulation seam being treated as conflicting surfaces."""
    base = np.array([[0.5, 0.5, 0.2]], dtype=float)
    body = TriangleMesh(
        positions=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=int),
    )

    constraints = build_surface_constraints(base, body, active_ids=[0])

    assert constraints.ambiguous.tolist() == [False]


def test_coincident_aligned_but_disconnected_surfaces_remain_ambiguous():
    """Catches disconnected duplicate layers being coalesced as one topological sheet."""
    base = np.array([[0.25, 0.25, 0.2]], dtype=float)
    body = TriangleMesh(
        positions=np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
        ], dtype=float),
        faces=np.array([[0, 1, 2], [3, 4, 5]], dtype=int),
    )

    constraints = build_surface_constraints(base, body, active_ids=[0])

    assert constraints.ambiguous.tolist() == [True]


@pytest.mark.parametrize("constraint_ids", [(0,), (1, 0)])
def test_contract_and_solver_require_exact_ordered_active_vertex_identity(constraint_ids):
    """Catches subset or reordered constraints silently omitting an original active vertex."""
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    body = TriangleMesh(
        positions=np.array([[-2, -2, 0.1], [2, -2, 0.1], [0, 2, 0.1]], dtype=float),
        faces=np.array([[0, 1, 2]], dtype=int),
    )
    roi = derive_minimal_roi(base, faces, active_ids=[0, 1])
    constraints = build_surface_constraints(base, body, active_ids=constraint_ids)

    with pytest.raises(ValueError, match="ACTIVE_VERTEX_IDENTITY_MISMATCH"):
        SyntheticCandidateContract(roi, constraints)
    with pytest.raises(ValueError, match="ACTIVE_VERTEX_IDENTITY_MISMATCH"):
        solve_coherent_field(
            base, faces, roi, constraints, scale=1.0, fairness=0.0, iterations=1,
        )


def test_production_contract_requires_body_surface_and_nonempty_fixed_cohort():
    """Catches production evaluation being configured without dynamic clearance or coverage."""
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    roi = derive_minimal_roi(base, faces, active_ids=[0])
    constraints = SurfaceConstraints(
        active_ids=(0,),
        closest_points=np.array([[0, 0, 0.1]]),
        surface_normals=np.array([[0, 0, 1.0]]),
        signed_clearances=np.array([-0.1]),
        target_positions=np.array([[0, 0, 0.101]]),
        face_ids=np.array([0]),
        barycentric=np.array([[1.0, 0.0, 0.0]]),
    )
    cohort = CoverageContract(
        points=np.array([[0.2, 0.2, -0.01]]),
        normals=np.array([[0.0, 0.0, 1.0]]),
    )

    with pytest.raises(ValueError, match="PRODUCTION_BODY_SURFACE_REQUIRED"):
        CandidateContract(roi, constraints, fixed_cohort=cohort)

    constraints_with_body = build_surface_constraints(
        base,
        TriangleMesh(
            positions=np.array([[-2, -2, 0.1], [2, -2, 0.1], [0, 2, 0.1]]),
            faces=np.array([[0, 1, 2]]),
        ),
        active_ids=[0],
    )
    with pytest.raises(ValueError, match="PRODUCTION_FIXED_COHORT_REQUIRED"):
        CandidateContract(roi, constraints_with_body)

    with pytest.raises(ValueError, match="COVERAGE_VALUES_MUST_BE_FINITE"):
        CoverageContract(
            points=np.array([[0.2, 0.2, -0.01]]),
            normals=np.array([[np.nan, 0.0, 1.0]]),
        )


def test_parsed_source_solver_propagates_semantics_and_rejects_none_or_tuple_bypass():
    """Catches a production candidate severing its verified DAE semantic identity."""
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    face_digest = hashlib.sha256(np.asarray(faces, dtype="<i8").tobytes()).hexdigest().upper()
    source = ParsedColladaGeometry(
        positions=base,
        faces=faces,
        geometry_id="lod0",
        content_sha256="A" * 64,
        non_position_sha256="B" * 64,
        face_indices_sha256=face_digest,
    )
    with pytest.raises(ValueError, match="PARSED_SOURCE_FACE_IDENTITY_MISMATCH"):
        ParsedColladaGeometry(
            positions=base,
            faces=faces,
            geometry_id="lod0",
            content_sha256="A" * 64,
            non_position_sha256="B" * 64,
            face_indices_sha256="C" * 64,
        )
    body = TriangleMesh(
        positions=np.array([[-2, -2, 0.1], [2, -2, 0.1], [0, 2, 0.1]], dtype=float),
        faces=np.array([[0, 1, 2]], dtype=int),
    )
    roi = derive_minimal_roi(base, faces, active_ids=[0, 1, 2])
    constraints = build_surface_constraints(base, body, active_ids=[0, 1, 2])
    contract = CandidateContract(
        roi,
        constraints,
        fixed_cohort=CoverageContract(
            points=np.array([[0.2, 0.2, 0.0]]),
            normals=np.array([[0.0, 0.0, 1.0]]),
            maximum_distance=0.2,
        ),
    )

    candidate = solve_coherent_field(
        source, source.faces, roi, constraints, scale=1.0, fairness=0.0, iterations=1,
    )
    report = evaluate_candidate(source, candidate, contract)

    assert candidate.source_non_position_sha256 == source.non_position_sha256
    assert candidate.source_face_indices_sha256 == source.face_indices_sha256
    assert report.passed is True
    assert report.production_passed is True
    assert report.status == "PRODUCTION_PASS"

    missing_semantics = Candidate.from_positions(
        source.positions, source.faces, candidate.positions, status="CANDIDATE",
    )
    with pytest.raises(ValueError, match="PRODUCTION_SOURCE_SEMANTIC_IDENTITY_REQUIRED"):
        evaluate_candidate(source, missing_semantics, contract)
    with pytest.raises(TypeError, match="PRODUCTION_PARSED_COLLADA_SOURCE_REQUIRED"):
        evaluate_candidate((source.positions, source.faces), candidate, contract)


def test_coherent_field_moves_connected_edge_when_independent_push_breaks_topology():
    """Catches a return to independent vertex pushes instead of one coherent update."""
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    roi = derive_minimal_roi(base, faces, active_ids=[0, 1, 2])
    targets = base + np.array([1.2, 0.0, 0.0])
    constraints = SurfaceConstraints(
        active_ids=(0, 1, 2),
        closest_points=targets - np.array([0.001, 0.0, 0.0]),
        surface_normals=np.tile([1.0, 0.0, 0.0], (3, 1)),
        signed_clearances=np.full(3, -1.199),
        target_positions=targets,
        face_ids=np.array([0, 1, 2]),
        barycentric=np.tile([1.0, 0.0, 0.0], (3, 1)),
    )
    contract = SyntheticCandidateContract(roi=roi, constraints=constraints)
    independent = base.copy()
    independent[0] = constraints.target_positions[0]
    independent_candidate = Candidate.from_positions(base, faces, independent, status="CANDIDATE")

    independent_report = evaluate_candidate((base, faces), independent_candidate, contract)
    coherent = solve_coherent_field(
        base, faces, roi, constraints, scale=1.0, fairness=0.0, iterations=1,
    )
    coherent_report = evaluate_candidate((base, faces), coherent, contract)

    assert independent_report.passed is False
    assert independent_report.flipped_faces == 1
    assert coherent.status == "CANDIDATE"
    assert coherent.moved_vertex_count == 3
    assert coherent_report.passed is True
    assert coherent_report.production_passed is False
    assert coherent_report.status == "SYNTHETIC_PASS"
    assert coherent_report.flipped_faces == 0
    assert coherent_report.new_zero_area_faces == 0
    assert coherent_report.minimum_area_ratio >= 0.5
    assert coherent_report.maximum_area_ratio <= 2.0
    assert coherent_report.fixed_vertex_moves == 0
    np.testing.assert_allclose(coherent.positions, targets, atol=1e-12)
    assert not hasattr(coherent, "faces")


def test_solver_defers_when_six_decimal_shell_has_no_legal_nonzero_move():
    """Catches topology gates being weakened to force a quantized nonzero output."""
    base = np.array([[0, 0, 0], [0.000002, 0, 0], [0, 0.000002, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    roi = derive_minimal_roi(base, faces, active_ids=[0])
    constraints = build_surface_constraints(
        base,
        TriangleMesh(
            positions=np.array([[0.000002, -1, -1], [0.000002, 1, -1], [0.000002, -1, 1]], dtype=float),
            faces=np.array([[0, 1, 2]], dtype=int),
        ),
        active_ids=[0],
    )

    candidate = solve_coherent_field(
        base, faces, roi, constraints, scale=1.0, fairness=0.0, iterations=1,
    )

    assert candidate.status == "DEFERRED_NO_POSITION_ONLY_SOLUTION"
    assert candidate.moved_vertex_count == 0
    np.testing.assert_array_equal(candidate.positions, base)


@pytest.mark.parametrize("bad_value", [0.499, 2.001])
def test_published_area_gate_cannot_be_weakened_by_contract(bad_value: float):
    """Catches caller-selected contracts weakening the fixed published area envelope."""
    base = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=int)
    roi = derive_minimal_roi(base, faces, active_ids=[1])
    constraints = build_surface_constraints(
        base,
        TriangleMesh(
            positions=np.array([[2, -2, -1], [2, 2, -1], [2, -2, 1]], dtype=float),
            faces=np.array([[0, 1, 2]], dtype=int),
        ),
        active_ids=[1],
    )
    candidate_positions = base.copy()
    candidate_positions[1, 0] = bad_value
    candidate = Candidate.from_positions(base, faces, candidate_positions, status="CANDIDATE")

    report = evaluate_candidate((base, faces), candidate, SyntheticCandidateContract(roi, constraints))

    assert report.passed is False
    if bad_value < 1.0:
        assert report.faces_below_published_area == 1
    else:
        assert report.faces_above_published_area == 1
