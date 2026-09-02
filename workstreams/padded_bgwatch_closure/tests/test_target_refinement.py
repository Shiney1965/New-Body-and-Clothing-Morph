"""Nearest-face refinement preserves the stored-normal oracle and fails boundedly."""

from dataclasses import replace

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure import geometry
from workstreams.padded_bgwatch_closure.geometry import (
    ParsedGlbSurface,
    SurfaceConstraintSetupError,
    build_surface_constraints,
    query_signed_clearance,
)


def _layers(heights, normals=None):
    heights = list(heights)
    normals = normals or [(0.0, 0.0, 1.0)] * len(heights)
    return ParsedGlbSurface(
        # The large base also gives an unaffected, already-passing control.
        positions=np.array([
            point for index, height in enumerate(heights)
            for point in ((0, 0, height), (3 if index == 0 else 1, 0, height),
                          (0, 3 if index == 0 else 1, height))
        ]),
        faces=np.arange(3 * len(heights)).reshape(-1, 3),
        vertex_normals=np.repeat(np.asarray(normals), 3, axis=0),
    )


def test_changed_nearest_face_is_refined_using_actual_clearance_deficit():
    """Catches certifying the initial face instead of correcting the new nearest face."""
    body = _layers([0.0, 0.0015])
    initial = query_signed_clearance([[0.25, 0.25, 0.001002]], body)
    assert initial.face_ids.tolist() == [1]
    assert initial.ambiguous.tolist() == [False]
    assert initial.signed_clearances[0] == pytest.approx(-0.000498)

    constraints = build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])

    np.testing.assert_array_equal(constraints.target_positions, [[0.25, 0.25, 0.002502]])
    assert constraints.face_ids.tolist() == [0]  # Preserve original constraints.
    fresh = query_signed_clearance(constraints.target_positions, body)
    assert fresh.face_ids.tolist() == [1]
    assert fresh.signed_clearances[0] >= 0.001
    for name in geometry.SignedClearanceQuery.__dataclass_fields__:
        np.testing.assert_array_equal(getattr(constraints.target_certification.query, name), getattr(fresh, name))


@pytest.mark.parametrize("order", [(2, 1, 0), (0, 2, 1)])
def test_multiple_failed_targets_keep_ids_order_and_passing_targets_exact(order):
    """Catches dropping failed targets or changing already-passing target bytes."""
    body = _layers([0.0, 0.0015])
    source = [[0.25, 0.25, -0.0001], [2.0, 0.25, -0.0001], [0.1, 0.2, -0.0001]]
    expected = np.array([[0.25, 0.25, 0.002502], [2.0, 0.25, 0.001002], [0.1, 0.2, 0.002502]])
    constraints = build_surface_constraints(source, body, order)

    assert constraints.active_ids == order
    assert constraints.target_certification.active_ids == order
    np.testing.assert_array_equal(constraints.target_positions, expected[list(order)])
    assert constraints.target_positions[list(order).index(1)].tobytes() == expected[1].tobytes()
    assert np.all(constraints.target_certification.query.signed_clearances >= 0.001)


@pytest.mark.parametrize("top_normal", [(0.6, 0.0, 0.8), (0.6, 0.0, -0.8)])
def test_refinement_uses_new_stored_normal_projection_and_orientation(top_normal):
    """Catches reusing the original face normal/projection after a face change."""
    body = _layers([0.0, 0.0015], [(0, 0, 1), top_normal])
    if top_normal[2] < 0:
        # Opposing sheets cannot hold the required clearance between them.
        with pytest.raises(SurfaceConstraintSetupError, match="TARGET_SETUP_REFINEMENT_CYCLE"):
            build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])
    else:
        constraints = build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])
        np.testing.assert_array_equal(constraints.target_positions, [[0.25, 0.25, 0.002752]])
        assert constraints.target_certification.query.signed_clearances[0] >= 0.001


def test_refinement_rejects_ambiguity_created_by_a_correction():
    """Catches skipping the oracle's ambiguity gate after moving a target."""
    body = _layers([0.0, 0.0015, 0.003504])
    with pytest.raises(SurfaceConstraintSetupError) as error:
        build_surface_constraints([[2.0, 0.25, -0.0001], [0.25, 0.25, -0.0001]], body, [0, 1])
    assert error.value.reason == "TARGET_SETUP_SURFACE_AMBIGUITY"
    assert error.value.vertex_ids == (1,)


@pytest.mark.parametrize("top_normal", [(1.0, 0.0, 0.0), (1.0, 0.0, 1e-13)])
def test_refinement_rejects_near_zero_projection_on_updated_face(top_normal):
    """Catches a changed face bypassing the existing projection lower bound."""
    body = _layers([0.0, 0.0015], [(0, 0, 1), top_normal])
    with pytest.raises(SurfaceConstraintSetupError) as error:
        build_surface_constraints([[2.0, 0.25, -0.0001], [0.25, 0.25, -0.0001]], body, [1, 0])
    assert error.value.reason == "TARGET_SETUP_PROJECTION_DEGENERATE"
    assert error.value.vertex_ids == (1,)


def test_refinement_detects_unrepresentable_rounded_step_as_stall():
    """Catches unbounded attempts when floating-point spacing erases the correction."""
    body = _layers([1e14])
    with pytest.raises(SurfaceConstraintSetupError) as error:
        build_surface_constraints([[0.25, 0.25, 1e14]], body, [0])
    assert error.value.reason == "TARGET_SETUP_REFINEMENT_STALLED"
    assert error.value.vertex_ids == (0,)


def test_opposing_sheets_reject_repeated_rounded_position_as_cycle():
    """Catches oscillation between different nearest faces being silently certified."""
    body = _layers([0.0, 0.0015], [(0, 0, 1), (0, 0, -1)])
    with pytest.raises(SurfaceConstraintSetupError) as error:
        build_surface_constraints([[0.25, 0.25, -0.0001]], body, [0])
    assert error.value.reason == "TARGET_SETUP_REFINEMENT_CYCLE"
    assert error.value.vertex_ids == (0,)


def test_sixteen_corrections_can_pass_but_seventeenth_is_not_attempted():
    """Catches off-by-one or unbounded refinement across successively closer sheets."""
    source = [[0.25, 0.25, -0.0001]]
    constraints = build_surface_constraints(source, _layers(np.arange(17) * 0.0015), [0])
    np.testing.assert_array_equal(constraints.target_positions, [[0.25, 0.25, 0.025002]])
    assert constraints.target_certification.query.signed_clearances[0] >= 0.001
    with pytest.raises(SurfaceConstraintSetupError) as error:
        build_surface_constraints(source, _layers(np.arange(18) * 0.0015), [0])
    assert error.value.reason == "TARGET_SETUP_REFINEMENT_LIMIT"
    assert error.value.vertex_ids == (0,)


@pytest.mark.parametrize("clearance", [float("nan"), float("-inf"), -np.finfo(float).max])
def test_nonfinite_or_overflowing_correction_is_explicit_setup_failure(monkeypatch, clearance):
    """Fault injection: invalid numerical oracle output must never reach certification."""
    real_query = geometry.query_signed_clearance

    def extreme_target_clearance(points, body):
        query = real_query(points, body)
        if np.any(np.asarray(points)[:, 2] > 0.0):
            return replace(query, signed_clearances=np.full(len(points), clearance))
        return query

    monkeypatch.setattr(geometry, "query_signed_clearance", extreme_target_clearance)
    with pytest.raises(SurfaceConstraintSetupError) as error:
        build_surface_constraints([[0.25, 0.25, -0.0001]], _layers([0.0]), [0])
    assert error.value.reason == "TARGET_SETUP_REFINEMENT_NONFINITE"
    assert error.value.vertex_ids == (0,)
