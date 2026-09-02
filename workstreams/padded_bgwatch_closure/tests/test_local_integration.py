"""DAE roundtrip and local real-input integration contracts for Task 4."""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure.configuration import VerifiedInput
from workstreams.padded_bgwatch_closure.geometry import (
    parse_collada_geometry,
    serialize_collada_positions,
)
from workstreams.padded_bgwatch_closure.integration import roundtrip_candidate
from workstreams.padded_bgwatch_closure.closure import build_terminal_exclusion_event
from workstreams.padded_bgwatch_closure.solver import Candidate


def _verified(content: bytes) -> VerifiedInput:
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput("pristine_source_dae", content, len(content), digest, digest)


def _dae() -> bytes:
    return b"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema">
  <library_geometries>
    <geometry id="lod0"><mesh>
      <source id="lod0-positions"><float_array id="lod0-positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array><technique_common><accessor source="#lod0-positions-array" count="3" stride="3"/></technique_common></source>
      <source id="lod0-normal"><float_array id="lod0-normal-array" count="3">0 0 1</float_array><technique_common><accessor source="#lod0-normal-array" count="1" stride="3"/></technique_common></source>
      <vertices id="lod0-vertices"><input semantic="POSITION" source="#lod0-positions"/></vertices>
      <triangles count="1" material="cloth"><input semantic="VERTEX" source="#lod0-vertices" offset="0"/><input semantic="NORMAL" source="#lod0-normal" offset="1"/><p>0 0 1 0 2 0</p></triangles>
    </mesh></geometry>
    <geometry id="lod1"><mesh>
      <source id="lod1-positions"><float_array id="lod1-positions-array" count="9">9 9 9 8 8 8 7 7 7</float_array><technique_common><accessor source="#lod1-positions-array" count="3" stride="3"/></technique_common></source>
      <vertices id="lod1-vertices"><input semantic="POSITION" source="#lod1-positions"/></vertices>
      <triangles count="1"><input semantic="VERTEX" source="#lod1-vertices" offset="0"/><p>0 1 2</p></triangles>
    </mesh></geometry>
  </library_geometries>
</COLLADA>"""


def test_position_writer_changes_only_selected_position_payload_and_roundtrips_six_decimals():
    """Catches XML reserialization, LOD1 mutation, or gates using pre-write coordinates."""
    verified = _verified(_dae())
    source = parse_collada_geometry(verified)
    candidate = np.array([
        [0.123456789, -0.0, 0.00000049],
        [1.00000051, 0.0, 0.0],
        [0.0, 1.0, -0.00000051],
    ])

    written = serialize_collada_positions(verified, source, candidate)
    readback = parse_collada_geometry(_verified(written))

    np.testing.assert_array_equal(
        readback.positions,
        np.array([[0.123457, 0.0, 0.0], [1.000001, 0.0, 0.0], [0.0, 1.0, -0.000001]]),
    )
    assert readback.geometry_id == source.geometry_id
    assert readback.faces.tolist() == source.faces.tolist()
    assert readback.non_position_sha256 == source.non_position_sha256
    assert b"9 9 9 8 8 8 7 7 7" in written
    assert b"lod0-normal-array" in written


def test_position_writer_rejects_a_candidate_not_bound_to_verified_source_shape():
    """Catches silently truncating or padding a position array during DAE emission."""
    verified = _verified(_dae())
    source = parse_collada_geometry(verified)

    try:
        serialize_collada_positions(verified, source, np.zeros((2, 3)))
    except ValueError as error:
        assert str(error) == "CANDIDATE_POSITION_SHAPE_MISMATCH"
    else:
        raise AssertionError("shape mismatch was accepted")


def test_candidate_roundtrip_rebuilds_candidate_from_serialized_readback_and_keeps_search_metadata():
    """Catches the search hashing/evaluating the pre-write float array or losing solver evidence."""
    verified = _verified(_dae())
    source = parse_collada_geometry(verified)
    candidate = Candidate.from_positions(
        source.positions,
        source.faces,
        np.array([[0.123456789, 0, 0], [1.00000051, 0, 0], [0, 1, -0.00000051]]),
        status="CANDIDATE",
        source_non_position_sha256=source.non_position_sha256,
        accepted_step_scales=(1.0, 0.5),
        rejected_iteration_count=1,
    )

    readback = roundtrip_candidate(verified, source, candidate)

    np.testing.assert_array_equal(
        readback.positions,
        np.array([[0.123457, 0.0, 0.0], [1.000001, 0.0, 0.0], [0.0, 1.0, -0.000001]]),
    )
    assert readback.source_non_position_sha256 == source.non_position_sha256
    assert readback.source_face_indices_sha256 == source.face_indices_sha256
    assert readback.accepted_step_scales == (1.0, 0.5)
    assert readback.rejected_iteration_count == 1


@pytest.mark.skipif(
    os.environ.get("PADDED_RUN_REAL_INTEGRATION") != "1",
    reason="requires hash-pinned ignored local Padded inputs",
)
def test_real_preparation_pins_the_original_active_set_and_fixed_coverage_cohort():
    """Catches real closure drifting from the retained 593/2800 identities."""
    from workstreams.padded_bgwatch_closure.integration import prepare_real_closure

    prepared = prepare_real_closure()

    assert len(prepared.source.positions) == 8_033
    assert len(prepared.source.faces) == 14_943
    assert len(prepared.body.positions) == 10_800
    assert len(prepared.body.faces) == 18_828
    assert len(prepared.active_ids) == 593
    assert hashlib.sha256(
        np.asarray(prepared.active_ids, dtype="<i8").tobytes(order="C")
    ).hexdigest().upper() == "726ADFC0E20E00ADC0D8D4B6B0451D0939D7CF0FFCC1D904BFEAAE38A5220DF5"
    assert len(prepared.coverage.body_vertex_ids) == 2_800
    assert hashlib.sha256(
        np.asarray(prepared.coverage.body_vertex_ids, dtype="<i8").tobytes(order="C")
    ).hexdigest().upper() == "A15EA818F106A23B44AC3DF26BD50AEC1FBBF3D4DCD157255E6FA0B2C95071E2"
    assert prepared.contract.roi.active_ids == prepared.active_ids
    assert prepared.contract.constraints.active_ids == prepared.active_ids


def test_terminal_exclusion_event_is_canonical_and_names_only_bounded_architecture_exhaustion(tmp_path):
    """Catches a zero-pass result claiming impossibility or emitting an unbound event ID."""
    evidence = tmp_path / "position_only_search.json"
    evidence.write_bytes(b'{"status":"POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY"}')

    event = build_terminal_exclusion_event(
        search_evidence_path=evidence,
        search_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest().upper(),
        created_utc="2026-09-01T23:59:59Z",
    )
    without_id = {key: value for key, value in event.items() if key != "event_id"}
    expected_digest = hashlib.sha256(json.dumps(
        without_id, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")).hexdigest().upper()

    assert event["event_id"] == f"EXCLUSION_{expected_digest}"
    assert event["reason"] == "NO_SAFE_GEOMETRY_AVAILABLE"
    assert event["protected_impact"]["result"] == "NO_PROTECTED_MUTATION"
    assert event["next_project_if_reopened"].startswith("separately approved manual-remesh")
    assert "mathematically impossible" not in json.dumps(event).lower()
