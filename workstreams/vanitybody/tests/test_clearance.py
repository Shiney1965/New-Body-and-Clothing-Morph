from pathlib import Path

import numpy as np

from workstreams.vanitybody.clearance import Surface, measure_penetration


FIXTURES = Path(__file__).with_name("fixtures")
BODY = np.load(FIXTURES / "synthetic_body.npy")
PENETRATING_GARMENT = np.load(FIXTURES / "synthetic_garment.npy")
CLEAR_GARMENT = PENETRATING_GARMENT.copy()
CLEAR_GARMENT[:, 2] = 0.01
GROIN_REGION = {"x_abs_max": 0.2, "y_min": -0.2, "y_max": 0.2, "z_min": -0.2, "z_max": 0.2}
BODY_FACES = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)


def test_penetrating_fixture_is_detected():
    report = measure_penetration(
        Surface(BODY, BODY_FACES), PENETRATING_GARMENT, GROIN_REGION, 0.002
    )
    assert report.penetrating_vertices > 0
    assert report.max_penetration > 0


def test_clear_fixture_has_no_penetration():
    report = measure_penetration(
        Surface(BODY, BODY_FACES), CLEAR_GARMENT, GROIN_REGION, 0.002
    )
    assert report.penetrating_vertices == 0
    assert report.min_signed_distance >= 0.002
