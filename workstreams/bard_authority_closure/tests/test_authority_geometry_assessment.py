"""Authority geometry assessment under retained safe tooling."""

from pathlib import Path

import pytest

from workstreams.bard_authority_closure.authority_geometry_assessment import (
    CLASSIFICATION_UNASSESSABLE,
    METHODS,
    STATUS_UNASSESSABLE,
    GeometryAssessmentError,
    assess_authority_geometry,
    assessment_payload,
    write_authority_geometry_assessment,
)
from workstreams.bard_authority_closure.authority_gap_audit import canonical_bytes
from workstreams.bard_authority_closure import authority_contracts as contracts


def test_authority_geometry_assessment_is_unassessable_without_source_bound_defect():
    assessment = assess_authority_geometry()

    assert assessment.status == STATUS_UNASSESSABLE
    assert assessment.geometry_admitted is False
    assert assessment.classification == CLASSIFICATION_UNASSESSABLE
    assert assessment.defect_region is None
    assert assessment.exclusion_event_input is None
    assert assessment.ready_for_attachment is False
    assert assessment.release_blocking is True
    assert assessment.landmark_cage_present is False
    assert assessment.methods_tested == METHODS
    assert set(assessment.netherstone_routes) == {
        "HFL_F_ARM_Authority_Robe",
        "HFL_F_ARM_Authority_Robe_Alt",
        "TIF_FS_ARM_Authority_Robe",
        "TIF_FS_ARM_Authority_Robe_Alt",
    }
    assert assessment.findings["source_bound_defect_region_present"] is False
    assert assessment.inventory["source_bound_defect_region_present"] is False
    assert assessment.gap_geometry["source_bound_defect_region_present"] is False
    assert assessment.glb_readbacks["bcbscantily_main_gr2"]["mesh_count"] == 8
    assert assessment.glb_readbacks["bcbscantily_skirt_gr2"]["mesh_count"] == 1


def test_authority_geometry_assessment_writer_is_deterministic_and_nonattachable():
    workstream = Path(__file__).resolve().parents[1]
    out_root = workstream / "local" / "task-4-geometry-assessment-pytest"
    if out_root.exists():
        import shutil
        shutil.rmtree(out_root)
    first = write_authority_geometry_assessment(out_root / "run-1")
    second = write_authority_geometry_assessment(out_root / "run-2")

    assert first.read_bytes() == second.read_bytes()
    payload = assessment_payload(assess_authority_geometry())
    assert first.read_bytes() == canonical_bytes(payload)
    assert payload["exclusion_event_input"] is None
    assert payload["geometry_admitted"] is False
    assert payload["classification"] == CLASSIFICATION_UNASSESSABLE
    assert payload["release_blocking"] is True


def test_authority_geometry_assessment_refuses_corrupt_gap_audit_flags():
    snapshot = contracts.load_current_authority_snapshot(include_gap_audit=True)
    gap = dict(snapshot.source_gap_audit)
    gap["defect_region"] = ("invented",)
    with pytest.raises(GeometryAssessmentError, match="AUTHORITY_GAP_AUDIT_DEFECT_CORRUPT"):
        assess_authority_geometry(gap_audit=gap)


def test_authority_landmark_cage_remains_absent_after_geometry_assessment():
    workstream = Path(__file__).resolve().parents[1]
    assess_authority_geometry()
    assert not (workstream / "authority_landmark_cage.py").exists()
    assert not (workstream / "tests" / "test_authority_landmark_cage.py").exists()
