"""DAE roundtrip and local real-input integration contracts for Task 4."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from dataclasses import replace

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure.configuration import VerifiedInput
from workstreams.padded_bgwatch_closure.geometry import (
    build_surface_constraints,
    derive_minimal_roi,
    parse_collada_geometry,
    parse_glb_surface,
    serialize_collada_positions,
)
from workstreams.padded_bgwatch_closure.integration import (
    PreparedClosure,
    derive_original_active_ids,
    derive_fixed_coverage_contract,
    roundtrip_candidate,
)
from workstreams.padded_bgwatch_closure.closure import (
    RepeatedClosure,
    build_pending_exclusion_evidence_packet,
    write_real_closure_artifacts,
    run_real_closure_twice,
)
from workstreams.padded_bgwatch_closure.search import (
    OFFLINE_CANDIDATE,
    POSITION_ONLY_UNFIXABLE,
)
from workstreams.padded_bgwatch_closure.solver import Candidate, CandidateContract
from workstreams.release_master_ledger.validation import validate_record


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


def _glb(*, height=0.0) -> bytes:
    """Minimal indexed triangle with stored normals; all arrays come from bytes."""
    positions = np.array([[0, 0, height], [1, 0, height], [0, 1, height]], dtype="<f4")
    normals = np.array([[0, 0, 1]] * 3, dtype="<f4")
    binary = positions.tobytes() + normals.tobytes() + struct.pack("<3I", 0, 1, 2)
    document = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": offset, "byteLength": size}
                        for offset, size in [(0, 36), (36, 36), (72, 12)]],
        "accessors": [{"bufferView": view, "componentType": kind, "count": 3, "type": shape}
                      for view, kind, shape in [(0, 5126, "VEC3"), (1, 5126, "VEC3"), (2, 5125, "SCALAR")]],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(binary))
            + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(binary), 0x004E4942) + binary)


def _prepared_fixture(*, passing=True) -> PreparedClosure:
    # Two layers: penetrating vertices and a closer outward layer covering the
    # body's three vertices. The zero-pass variant pins one near-body connector.
    values = "0 0 -0.01 1 0 -0.01 0 1 -0.01 0 0 0.005 1 0 0.005 0 1 0.005"
    faces = "0 0 1 0 2 0 3 0 4 0 5 0"
    if not passing:
        values = "0 0 -10 1 0 -10 0 1 0.0001 0 0 0.005 1 0 0.005 0 1 0.005"
    content = _dae().replace(
        b'count="9">0 0 0 1 0 0 0 1 0', ('count="18">' + values).encode(),
    ).replace(b'count="3" stride="3"', b'count="6" stride="3"', 1).replace(
        b'<triangles count="1" material="cloth">', b'<triangles count="2" material="cloth">',
    ).replace(b'<p>0 0 1 0 2 0</p>', ('<p>' + faces + '</p>').encode())
    verified = _verified(content)
    source = parse_collada_geometry(verified)
    verified_body = replace(_verified(_glb()), input_id="bcb_body_glb")
    body = parse_glb_surface(verified_body)
    active = derive_original_active_ids(source.positions, body)
    roi = derive_minimal_roi(source.positions, source.faces, active)
    constraints = build_surface_constraints(source.positions, body, active)
    cohort = derive_fixed_coverage_contract(source.positions, source.faces, body)
    return PreparedClosure(
        verified_source=verified,
        verified_body=verified_body,
        source=source,
        body=body,
        body_vertex_normals_sha256=hashlib.sha256(
            np.asarray(body.vertex_normals, dtype="<f8").tobytes(order="C"),
        ).hexdigest().upper(),
        active_ids=active,
        coverage=cohort,
        contract=CandidateContract(roi, constraints, fixed_cohort=cohort.contract),
    )


def _repeated_fixture(*, passing: bool) -> RepeatedClosure:
    prepared = _prepared_fixture(passing=passing)
    repeated = run_real_closure_twice(prepared)
    assert (repeated.first.status == OFFLINE_CANDIDATE) is passing
    return repeated


def test_pending_exclusion_packet_is_explicitly_nonattachable_to_release_ledger(tmp_path):
    """Catches the Padded closure inventing a canonical record/profile/event binding."""
    evidence = tmp_path / "position_only_search.json"
    evidence.write_bytes(b'{"status":"POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY"}')

    packet = build_pending_exclusion_evidence_packet(
        search_evidence_path=evidence,
        search_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest().upper(),
        created_utc="2026-09-01T23:59:59Z",
    )
    assert packet["attachment_status"] == "NOT_ATTACHABLE_SOURCE_PROFILE_AND_CANONICAL_BINDING_UNRESOLVED"
    assert packet["reason"] == "NO_SAFE_GEOMETRY_AVAILABLE"
    assert packet["protected_impact"]["result"] == "NO_PROTECTED_MUTATION"
    assert packet["next_project_if_reopened"].startswith("separately approved manual-remesh")
    assert {"event_id", "record_id", "identity_sha256", "source_profile_id"}.isdisjoint(packet)
    assert "mathematically impossible" not in json.dumps(packet).lower()
    ledger_errors = validate_record(packet)
    assert "MISSING:record_id" in ledger_errors
    assert "MISSING:identity_sha256" in ledger_errors


def test_pending_packet_registers_and_revalidates_every_retained_prior_architecture_artifact(tmp_path):
    """Catches architecture claims relying on an unhashed clearance report or side evidence."""
    evidence = tmp_path / "position_only_search.json"
    evidence.write_bytes(b'{"status":"POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY"}')

    packet = build_pending_exclusion_evidence_packet(
        search_evidence_path=evidence,
        search_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest().upper(),
        created_utc="2026-09-01T23:59:59Z",
    )

    registered = packet["registered_prior_artifacts"]
    by_path = {item["path"]: item for item in registered}
    assert len(registered) == 36
    assert by_path["CLEARANCE_COMPARISON.md"]["sha256"] == (
        "3EABA70C12BFACD4D0862AE93EE342350E4A969CBAC50D8D7ECAA9F7B9F8739D"
    )
    assert by_path["evidence/four_way_clearance.json"]["sha256"] == (
        "46EC39E4EAEA832B4DF3BFCD9ADA0B5BA9DDD560E452F1BCB306D3E87DE22805"
    )
    assert by_path["evidence/local_repair_manifest.json"]["sha256"] == (
        "CC097FD41746ED2474A604CF042D037D18C920B80044F5338CEB8F2C6A310066"
    )
    assert all(item["sha256"] == item["verified_sha256"] for item in registered)
    architectures = {item["name"]: item["evidence_paths"] for item in packet["prior_architectures"]}
    assert "CLEARANCE_COMPARISON.md" in architectures["strict_global_alpha_interpolation"]
    assert "CLEARANCE_COMPARISON.md" in architectures["confidence_gated_local_clearance_repair"]


def test_artifact_writer_emits_candidate_only_for_a_passing_closure(tmp_path):
    """Catches a passing position-only result omitting its only allowed candidate DAE."""
    result = write_real_closure_artifacts(
        _repeated_fixture(passing=True), workstream_root=tmp_path,
        created_utc="2026-09-02T01:00:00Z", evidence_scope="SYNTHETIC_FIXTURE",
    )

    generated = tmp_path / "local" / "generated"
    assert result["status"] == OFFLINE_CANDIDATE
    assert result["evidence_scope"] == "SYNTHETIC_FIXTURE"
    assert result["canonical_garment_claim_established"] is False
    assert (generated / "synthetic_candidate.dae").is_file()
    assert not (generated / "HUM_F_ARM_BG_Watch_Leather_A_Body_CMcover_candidate.dae").exists()
    assert not (generated / "pending_exclusion_evidence_packet.json").exists()


def test_artifact_writer_emits_pending_packet_only_for_zero_pass_closure(tmp_path):
    """Catches an unfixable result emitting a candidate or a ledger-attachable event."""
    result = write_real_closure_artifacts(
        _repeated_fixture(passing=False), workstream_root=tmp_path,
        created_utc="2026-09-02T01:00:00Z", evidence_scope="SYNTHETIC_FIXTURE",
    )

    generated = tmp_path / "local" / "generated"
    assert result["status"] == POSITION_ONLY_UNFIXABLE
    assert not (generated / "HUM_F_ARM_BG_Watch_Leather_A_Body_CMcover_candidate.dae").exists()
    assert not (generated / "pending_exclusion_evidence_packet.json").exists()
    packet = json.loads((generated / "synthetic_fixture_report.json").read_text(encoding="utf-8"))
    assert packet["evidence_scope"] == "SYNTHETIC_FIXTURE"
    assert packet["canonical_garment_claim_established"] is False
    assert "fixed_acceptance_gates" not in packet
    assert packet["active_vertex_count"] == 2
    assert packet["input_sha256"] == result["input_sha256"]
    assert {"event_id", "record_id", "identity_sha256", "source_profile_id"}.isdisjoint(packet)


def test_artifact_writer_refuses_preexisting_stale_artifacts_without_deleting_them(tmp_path):
    """Catches zero-pass cleanup unlinking a stale candidate or overwriting its audit trail."""
    stale = tmp_path / "local" / "generated" / "HUM_F_ARM_BG_Watch_Leather_A_Body_CMcover_candidate.dae"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale-candidate")

    with pytest.raises(FileExistsError, match="CLOSURE_ARTIFACT_PATH_ALREADY_EXISTS"):
        write_real_closure_artifacts(
            _repeated_fixture(passing=False), workstream_root=tmp_path,
            created_utc="2026-09-02T01:00:00Z", evidence_scope="SYNTHETIC_FIXTURE",
        )

    assert stale.read_bytes() == b"stale-candidate"
    assert sorted(path.name for path in stale.parent.iterdir()) == [stale.name]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("json_bytes", b'{"different":true}', "REPEATED_CLOSURE_JSON_MISMATCH"),
        ("selected_position_sha256", "B" * 64, "REPEATED_CLOSURE_SELECTION_MISMATCH"),
    ],
)
def test_artifact_writer_revalidates_directly_constructed_repeated_closure_before_writing(
    tmp_path, field, value, error,
):
    """Catches forged RepeatedClosure objects bypassing the two-run determinism claim."""
    repeated = _repeated_fixture(passing=True)
    forged = RepeatedClosure(repeated.prepared, repeated.first, replace(repeated.second, **{field: value}))

    with pytest.raises(RuntimeError, match=error):
        write_real_closure_artifacts(
            forged, workstream_root=tmp_path, created_utc="2026-09-02T01:00:00Z",
        )

    assert not (tmp_path / "local").exists()
