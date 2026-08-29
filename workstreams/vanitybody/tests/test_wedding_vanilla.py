import numpy as np

from workstreams.vanitybody.anchors import WEDDING_ROOT, load_anchor_contracts
from workstreams.vanitybody.clearance import Surface, measure_penetration
from workstreams.vanitybody.solve_anchor import (
    apply_patch,
    solve_local_clearance,
)


CONTRACT = next(
    anchor for anchor in load_anchor_contracts() if anchor.root_uuid == WEDDING_ROOT and anchor.mode == "vanilla"
)
BODY = Surface(
    np.array([[-0.2, 0.6, 0.0], [0.2, 0.6, 0.0], [0.2, 1.2, 0.0], [-0.2, 1.2, 0.0]]),
    np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
)
GARMENT = np.array([[-0.05, 0.75, -0.01], [0.05, 0.75, -0.01], [0.0, 0.9, -0.01]])


def test_synthetic_wedding_shaped_solver_example_clears_only_its_synthetic_region():
    """Algorithm-only test; it is not a real GR2 topology or semantic gate."""
    patch = solve_local_clearance(CONTRACT, BODY, GARMENT, clearance=0.002)
    result = apply_patch(GARMENT, patch)
    assert measure_penetration(BODY, result, CONTRACT.defect_region, 0.002).penetrating_vertices == 0
    assert np.array_equal(GARMENT[:, 2], np.full(3, -0.01))
