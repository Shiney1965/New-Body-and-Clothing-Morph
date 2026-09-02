"""Production target feasibility uses the exact retained stored-normal oracle."""

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure import geometry
from workstreams.padded_bgwatch_closure.configuration import VerifiedInput
from workstreams.padded_bgwatch_closure.geometry import (
    ParsedGlbSurface,
    TriangleMesh,
    build_surface_constraints,
    derive_minimal_roi,
    parse_collada_geometry,
    query_signed_clearance,
    serialize_collada_positions,
)
from workstreams.padded_bgwatch_closure.integration import derive_fixed_coverage_contract
from workstreams.padded_bgwatch_closure.search import run_position_only_search
from workstreams.padded_bgwatch_closure.solver import (
    Candidate,
    CandidateContract,
    evaluate_candidate,
    solve_coherent_field,
)


def _plane(normal=(0.6, 0.0, 0.8), *, height=0.0, reverse=False):
    return ParsedGlbSurface(
        positions=np.array([[0, 0, height], [1, 0, height], [0, 1, height]]),
        faces=np.array([[0, 2, 1] if reverse else [0, 1, 2]]),
        vertex_normals=np.array([normal] * 3),
    )


@pytest.mark.parametrize("normal,reverse", [
    ((0.6, 0.0, 0.8), False),
    ((0.0, 0.0, 1.0), False),
    ((0.0, 0.0, -1.0), False),
    ((0.6, 0.0, 0.8), True),
])
def test_rounded_targets_meet_exact_stored_normal_clearance(normal, reverse):
    """Catches stored-normal offsets losing clearance after closest-point reprojection."""
    body = _plane(normal, reverse=reverse)
    constraints = build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])
    rounded = np.array([[float(f"{v:.6f}") for v in row] for row in constraints.target_positions])
    query = query_signed_clearance(rounded, body)

    assert query.signed_clearances[0] >= 0.001
    assert query.ambiguous.tolist() == [False]
    np.testing.assert_array_equal(constraints.target_positions, rounded)
    np.testing.assert_array_equal(rounded[:, :2], [[0.25, 0.25]])


def test_target_margin_survives_non_grid_aligned_surface_height():
    """Catches rounding a target below the unchanged acceptance threshold."""
    body = _plane((0.0, 0.0, 1.0), height=0.00000049)
    constraints = build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])
    rounded = np.array([[float(f"{v:.6f}") for v in row] for row in constraints.target_positions])

    assert query_signed_clearance(rounded, body).signed_clearances[0] >= 0.001
    np.testing.assert_array_equal(constraints.target_positions, rounded)


def _verified(content):
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput("pristine_source_dae", content, len(content), digest, digest)


def _feasible_shell():
    # The first triangle penetrates; the separate upper shell preserves a real
    # pristine-covered cohort at the body's vertices throughout the correction.
    content = b'''<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema">
<library_geometries><geometry id="shell"><mesh>
<source id="positions"><float_array id="positions-array" count="18">0.1 0.1 -0.0001 0.3 0.1 -0.0001 0.1 0.3 -0.0001 0 0 0.01 1 0 0.01 0 1 0.01</float_array><technique_common><accessor source="#positions-array" count="6" stride="3"/></technique_common></source>
<vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
<triangles count="2" material="cloth"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2 3 4 5</p></triangles>
</mesh></geometry></library_geometries></COLLADA>'''
    verified = _verified(content)
    source = parse_collada_geometry(verified)
    body = _plane()
    roi = derive_minimal_roi(source.positions, source.faces, [0, 1, 2])
    constraints = build_surface_constraints(source.positions, body, roi.active_ids)
    cohort = derive_fixed_coverage_contract(source.positions, source.faces, body).contract
    return verified, source, CandidateContract(roi, constraints, cohort)


def test_feasible_shell_reaches_all_gates_after_real_dae_roundtrip():
    """Catches infeasible builder targets defeating the scale-one/fairness-zero control."""
    verified, source, contract = _feasible_shell()
    candidate = solve_coherent_field(
        source, source.faces, contract.roi, contract.constraints,
        scale=1.0, fairness=0.0, iterations=1,
    )
    readback = parse_collada_geometry(_verified(serialize_collada_positions(verified, source, candidate.positions)))
    rounded_candidate = Candidate.from_positions(
        source.positions, source.faces, readback.positions, status=candidate.status,
        source_non_position_sha256=readback.non_position_sha256,
    )
    report = evaluate_candidate(source, rounded_candidate, contract)

    assert report.active_vertices_below_clearance == 0
    assert report.active_surface_ambiguities == 0
    assert report.production_passed is True
    assert report.fixed_cohort_coverage_loss == 0
    assert report.fixed_vertex_moves == 0
    assert report.minimum_area_ratio == pytest.approx(1.0)
    assert report.maximum_area_ratio == pytest.approx(1.0)


def _two_planes(separation):
    return ParsedGlbSurface(
        positions=np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [0, 0, separation], [1, 0, separation], [0, 1, separation],
        ]),
        faces=np.array([[0, 1, 2], [3, 4, 5]]),
        vertex_normals=np.array([[0.0, 0.0, 1.0]] * 6),
    )


@pytest.mark.parametrize("separation,reason", [
    (0.0015, "TARGET_SETUP_CLEARANCE_NOT_MET"),
    (0.002004, "TARGET_SETUP_SURFACE_AMBIGUITY"),
])
def test_target_requery_rejects_changed_nearest_or_ambiguous_surface(separation, reason):
    """Catches certifying only against the original face instead of rerunning the oracle."""
    with pytest.raises(ValueError, match=reason) as error:
        build_surface_constraints([[0.25, 0.25, -0.0001]], _two_planes(separation), [0])
    assert error.value.vertex_ids == (0,)


def test_changed_nearest_triangle_is_allowed_only_when_new_query_certifies():
    """Catches face-ID equality replacing exact target clearance certification."""
    constraints = build_surface_constraints([[0.25, 0.25, -0.0001]], _two_planes(0.000001), [0])
    certification = getattr(constraints, "target_certification", None)
    assert certification is not None
    assert constraints.face_ids.tolist() == [0]
    assert certification.query.face_ids.tolist() == [1]
    assert certification.query.signed_clearances[0] >= 0.001
    assert certification.query.ambiguous.tolist() == [False]


@pytest.mark.parametrize("normal", [(1.0, 0.0, 0.0), (1.0, 0.0, 1e-13)])
def test_degenerate_geometric_normal_projection_is_setup_failure(normal):
    """Catches division by a zero/near-zero stored-normal projection entering search."""
    with pytest.raises(ValueError, match="TARGET_SETUP_PROJECTION_DEGENERATE") as error:
        build_surface_constraints([[0.25, 0.25, -0.0001]], _plane(normal), [0])
    assert error.value.vertex_ids == (0,)


def test_degenerate_body_is_explicit_target_setup_failure():
    """Catches raw oracle failure being misclassified as a failed geometry candidate."""
    body = ParsedGlbSurface(
        positions=np.zeros((3, 3)), faces=np.array([[0, 1, 2]]),
        vertex_normals=np.array([[0.0, 0.0, 1.0]] * 3),
    )
    with pytest.raises(ValueError, match="TARGET_SETUP_ORACLE_FAILED") as error:
        build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])
    assert error.value.vertex_ids == (0,)


def test_production_body_cannot_drop_stored_normal_provenance():
    """Catches production contracts and solvers selecting the geometric-only fallback."""
    _verified_source, source, contract = _feasible_shell()
    body = contract.constraints.body_mesh
    constraints = build_surface_constraints(
        source.positions, TriangleMesh(body.positions, body.faces), contract.roi.active_ids,
    )
    with pytest.raises(ValueError, match="TARGET_SETUP_STORED_NORMAL_BODY_REQUIRED"):
        CandidateContract(contract.roi, constraints, contract.fixed_cohort)
    with pytest.raises(ValueError, match="TARGET_SETUP_STORED_NORMAL_BODY_REQUIRED"):
        solve_coherent_field(source, source.faces, contract.roi, constraints, 1.0, 0.0, 1)


def test_certification_is_required_and_bound_to_actual_targets_and_body():
    """Catches absent or copied certification authorizing altered production targets."""
    _verified_source, source, contract = _feasible_shell()
    constraints = contract.constraints
    assert getattr(constraints, "target_certification", None) is not None
    invalid_constraints = [
        replace(constraints, target_certification=None),
        replace(constraints, target_positions=constraints.target_positions + [0.0, 0.0, -0.00001]),
        replace(constraints, body_mesh=_plane(height=0.01)),
    ]
    for invalid in invalid_constraints:
        with pytest.raises(ValueError, match="TARGET_SETUP_CERTIFICATION"):
            CandidateContract(contract.roi, invalid, contract.fixed_cohort)
        with pytest.raises(ValueError, match="TARGET_SETUP_CERTIFICATION"):
            solve_coherent_field(source, source.faces, contract.roi, invalid, 1.0, 0.0, 1)


@pytest.mark.parametrize("point,reason", [
    ([0.25, 0.25, float("inf")], "TARGET_SETUP_NONFINITE_TARGET"),
    ([0.25, 0.25, 0.0010004], "TARGET_SETUP_UNROUNDED_TARGET"),
    ([0.25, 0.25, 0.000999], "TARGET_SETUP_CLEARANCE_NOT_MET"),
])
def test_direct_certification_rejects_invalid_or_unclear_targets(point, reason):
    """Catches direct verification bypassing quantization, finiteness, or clearance."""
    certify = getattr(geometry, "certify_surface_targets", None)
    assert callable(certify)
    with pytest.raises(ValueError, match=reason) as error:
        certify([point], _plane((0.0, 0.0, 1.0)), (7,))
    assert error.value.vertex_ids == (7,)


def test_search_propagates_setup_failure_instead_of_returning_exhaustion():
    """Catches the search converting uncertified setup into failed candidate records."""
    _verified_source, source, valid_contract = _feasible_shell()
    # Emulate a malformed supplied/deserialized contract bypassing its constructor;
    # production solver still must stop before a record or terminal result exists.
    malformed_contract = object.__new__(CandidateContract)
    object.__setattr__(malformed_contract, "roi", valid_contract.roi)
    object.__setattr__(malformed_contract, "fixed_cohort", valid_contract.fixed_cohort)
    object.__setattr__(malformed_contract, "constraints", replace(
        valid_contract.constraints, target_certification=None,
    ))

    with pytest.raises(geometry.SurfaceConstraintSetupError, match="TARGET_SETUP_CERTIFICATION_REQUIRED"):
        run_position_only_search(source, malformed_contract)


@pytest.mark.parametrize("query_field,values", [
    ("signed_clearances", [0.000999, 0.001002, 0.001002]),
    ("signed_clearances", [float("nan"), 0.001002, 0.001002]),
    ("ambiguous", [True, False, False]),
])
def test_production_rejects_failed_or_nonfinite_certificate_result(query_field, values):
    """Catches production admission trusting a certificate with failing oracle metrics."""
    _verified_source, _source, contract = _feasible_shell()
    certificate = contract.constraints.target_certification
    invalid = replace(contract.constraints, target_certification=replace(
        certificate, query=replace(certificate.query, **{query_field: np.array(values)}),
    ))

    with pytest.raises(geometry.SurfaceConstraintSetupError, match="TARGET_SETUP_CERTIFICATION_MISMATCH"):
        CandidateContract(contract.roi, invalid, contract.fixed_cohort)


def test_direct_certification_identifies_only_the_failed_active_vertex():
    """Catches target row indices being reported instead of exact source vertex IDs."""
    with pytest.raises(geometry.SurfaceConstraintSetupError) as error:
        geometry.certify_surface_targets(
            [[0.25, 0.25, 0.001002], [0.3, 0.25, 0.000999]],
            _plane((0.0, 0.0, 1.0)), (9, 4),
        )
    assert error.value.reason == "TARGET_SETUP_CLEARANCE_NOT_MET"
    assert error.value.vertex_ids == (4,)
