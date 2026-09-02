"""Byte-derived preparation and writer evidence anti-forgery regression tests."""

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from workstreams.padded_bgwatch_closure import closure
from workstreams.padded_bgwatch_closure.geometry import build_surface_constraints
from workstreams.padded_bgwatch_closure.solver import Candidate
from workstreams.padded_bgwatch_closure.search import _serialize_result, _position_sha256
from workstreams.padded_bgwatch_closure.tests.test_local_integration import _prepared_fixture, _verified, _glb, _dae, _repeated_fixture


@pytest.mark.parametrize("corruption", [
    "fabricated_body_bytes", "unrelated_body_bytes", "unrelated_source_bytes",
    "source_positions", "source_semantics", "body_positions", "body_faces",
    "body_normals", "active_ids", "roi", "cohort_ids", "cohort_points",
    "cohort_normals", "cohort_distance", "constraint_closest_points",
    "constraint_normals", "constraint_clearance", "constraint_face_ids",
    "constraint_barycentric", "constraint_ambiguous",
])
def test_prepared_validation_rederives_every_contract_from_verified_bytes(corruption):
    """Catches accepting unrelated parsed data just because its supplied hash matches."""
    prepared = _prepared_fixture()
    if corruption == "fabricated_body_bytes":
        prepared = replace(prepared, verified_body=replace(
            _verified(b"synthetic body bytes"), input_id="bcb_body_glb"))
    elif corruption == "unrelated_body_bytes":
        prepared = replace(prepared, verified_body=replace(
            _verified(_glb(height=0.01)), input_id="bcb_body_glb"))
    elif corruption == "unrelated_source_bytes":
        verified = _verified(_dae())
        prepared = replace(prepared, verified_source=verified, source=replace(
            prepared.source, content_sha256=verified.actual_sha256))
    elif corruption == "source_positions":
        prepared = replace(prepared, source=replace(prepared.source, positions=prepared.source.positions + 1))
    elif corruption == "source_semantics":
        prepared = replace(prepared, source=replace(prepared.source, non_position_sha256="A" * 64))
    elif corruption.startswith("body_"):
        field = {"body_positions": "positions", "body_faces": "faces", "body_normals": "vertex_normals"}[corruption]
        values = {"positions": prepared.body.positions + 1,
                  "faces": prepared.body.faces[:, ::-1],
                  "vertex_normals": np.array([[0.6, 0, 0.8]] * 3)}[field]
        body = replace(prepared.body, **{field: values})
        constraints = build_surface_constraints(prepared.source.positions, body, prepared.active_ids)
        prepared = replace(prepared, body=body,
                           body_vertex_normals_sha256=hashlib.sha256(np.asarray(body.vertex_normals, dtype="<f8").tobytes()).hexdigest().upper(),
                           contract=replace(prepared.contract, constraints=constraints))
    elif corruption == "active_ids":
        prepared = replace(prepared, active_ids=(0,))
    elif corruption == "roi":
        prepared = replace(prepared, contract=replace(prepared.contract,
                           roi=replace(prepared.contract.roi, movable_ids=(0, 1, 2, 3))))
    elif corruption == "cohort_ids":
        prepared = replace(prepared, coverage=replace(prepared.coverage, body_vertex_ids=(0,)))
    elif corruption.startswith("cohort_"):
        field = {"cohort_points": "points", "cohort_normals": "normals", "cohort_distance": "maximum_distance"}[corruption]
        values = {"points": prepared.coverage.contract.points + 1,
                  "normals": -prepared.coverage.contract.normals,
                  "maximum_distance": 0.1}[field]
        coverage = replace(prepared.coverage.contract, **{field: values})
        prepared = replace(prepared, coverage=replace(prepared.coverage, contract=coverage),
                           contract=replace(prepared.contract, fixed_cohort=coverage))
    else:
        field = {"constraint_closest_points": "closest_points", "constraint_normals": "surface_normals",
                 "constraint_clearance": "signed_clearances", "constraint_face_ids": "face_ids",
                 "constraint_barycentric": "barycentric", "constraint_ambiguous": "ambiguous"}[corruption]
        original = getattr(prepared.contract.constraints, field)
        values = -original if field == "surface_normals" else ~original if field == "ambiguous" else original + 1
        constraints = replace(prepared.contract.constraints, **{field: values})
        prepared = replace(prepared, contract=replace(prepared.contract, constraints=constraints))

    with pytest.raises((RuntimeError, ValueError), match="PREPARED_.*(MISMATCH|INVALID)"):
        closure._validate_prepared_closure(prepared)


def test_byte_encoded_preparation_is_accepted_without_object_identity_shortcuts():
    """Catches validation confusing a freshly parsed equivalent body with bad provenance."""
    prepared = _prepared_fixture()
    closure._validate_prepared_closure(prepared)


@pytest.fixture(scope="module")
def passing_repeated():
    return _repeated_fixture(passing=True)


def _reserialized(result, **changes):
    result = replace(result, **changes)
    return replace(result, json_bytes=_serialize_result(
        result.status, result.records, result.passing_count,
        result.selected_record_index, result.selected_position_sha256,
    ))


@pytest.mark.parametrize("field,value", [
    ("source_position_count", 999), ("source_position_count", 6.0),
    ("source_face_indices_sha256", "F" * 64), ("source_non_position_sha256", "E" * 64),
    ("moved_vertex_count", 999), ("moved_vertex_count", -1), ("moved_vertex_count", True),
    ("moved_vertex_count", 4), ("moved_vertex_count", 0),
])
def test_every_record_metadata_is_bound_to_the_actual_source(passing_repeated, field, value):
    """Catches internally serialized but fabricated source facts in nonselected rows."""
    records = tuple(replace(record, **{field: value}) if record.index == 159 else record
                    for record in passing_repeated.first.records)
    result = _reserialized(passing_repeated.first, records=records)
    forged = replace(passing_repeated, first=result, second=result)
    with pytest.raises(RuntimeError, match="SEARCH_RESULT_RECORD_.*(INVALID|MISMATCH)"):
        closure._validate_repeated_closure(forged)


def test_failed_record_gate_counts_cannot_exceed_the_verified_active_set(passing_repeated):
    """Catches a numerically impossible failure count hidden by an already-failing summary."""
    first = passing_repeated.first
    records = list(first.records)
    records[0] = replace(records[0], gates=replace(records[0].gates, active_vertices_below_clearance=999))
    result = _reserialized(first, records=tuple(records))
    with pytest.raises(RuntimeError, match="SEARCH_RESULT_GATE_COUNTS_INVALID"):
        closure._validate_repeated_closure(replace(passing_repeated, first=result, second=result))


@pytest.mark.parametrize("target,field,value", [
    ("record", "moved_vertex_count", 2),
    ("candidate", "moved_vertex_count", 2),
    ("candidate", "source_face_indices_sha256", "F" * 64),
    ("candidate", "source_non_position_sha256", "E" * 64),
])
def test_selected_metadata_agrees_with_actual_serialized_readback(passing_repeated, target, field, value):
    """Catches plausible bounded metadata that disagrees with the actual selected positions."""
    first = passing_repeated.first
    if target == "record":
        records = list(first.records)
        records[first.selected_record_index] = replace(records[first.selected_record_index], **{field: value})
        result = _reserialized(first, records=tuple(records))
    else:
        result = replace(first, selected_candidate=replace(first.selected_candidate, **{field: value}))
    with pytest.raises(RuntimeError, match="SEARCH_RESULT_SELECTED_METADATA_MISMATCH"):
        closure._validate_repeated_closure(replace(passing_repeated, first=result, second=result))


def test_default_writer_cannot_promote_synthetic_zero_pass_to_canonical_garment_packet(tmp_path):
    """Catches a small valid fixture emitting the pinned garment's 593/2800 claims."""
    repeated = _repeated_fixture(passing=False)
    with pytest.raises(ValueError, match="CANONICAL_PREPARATION_INPUT_IDENTITY_MISMATCH"):
        closure.write_real_closure_artifacts(repeated, workstream_root=tmp_path, created_utc="2026-09-02T00:00:00Z")
    assert not (tmp_path / "local").exists()


@pytest.mark.parametrize("field,value", [
    ("passed", False), ("production_passed", False), ("status", "PRODUCTION_FAIL"),
    ("topology_identity_equal", False), ("non_position_semantics_equal", False),
    ("position_count_equal", False), ("fixed_vertex_moves", 1),
    ("active_vertices_below_clearance", 1), ("active_surface_ambiguities", 1),
    ("moved_roi_vertices_below_clearance", 1), ("moved_roi_surface_ambiguities", 1),
    ("fixed_cohort_coverage_loss", 1), ("flipped_faces", 1), ("new_zero_area_faces", 1),
    ("faces_below_published_area", 1), ("faces_above_published_area", 1),
    ("faces_below_internal_area", 1), ("faces_above_internal_area", 1),
    ("faces_below_orientation_cosine", 1), ("minimum_area_ratio", 0.1),
    ("maximum_area_ratio", 3.0), ("minimum_orientation_cosine", 0.0),
])
def test_writer_rejects_gate_fields_that_disagree_with_passing_summary(
    passing_repeated, field, value,
):
    """Catches trusting production_passed/reasons while an individual gate contradicts it."""
    repeated = passing_repeated
    records = list(repeated.first.records)
    index = repeated.first.selected_record_index
    records[index] = replace(records[index], gates=replace(records[index].gates, **{field: value}))
    forged = _reserialized(repeated.first, records=tuple(records))
    with pytest.raises(RuntimeError, match="SEARCH_RESULT_GATE_.*(INVALID|MISMATCH)"):
        closure._validate_search_result(forged, repeated.prepared)


@pytest.mark.parametrize("field,reason", [
    ("moved_roi_vertices_below_clearance", "MOVED_ROI_CLEARANCE_NOT_MET"),
    ("moved_roi_surface_ambiguities", "MOVED_ROI_SURFACE_AMBIGUITY"),
])
def test_writer_rejects_historical_style_moved_roi_reason_omissions(passing_repeated, field, reason):
    """Catches the retained-run defect even when the row was already a production failure."""
    records = list(passing_repeated.first.records)
    assert reason not in records[0].failure_reasons
    records[0] = replace(records[0], gates=replace(records[0].gates, **{field: 1}))
    forged = _reserialized(passing_repeated.first, records=tuple(records))
    with pytest.raises(RuntimeError, match="SEARCH_RESULT_GATE_REASONS_MISMATCH"):
        closure._validate_search_result(forged, passing_repeated.prepared)


def test_writer_reevaluates_actual_selected_geometry_despite_consistent_passing_metadata(
    passing_repeated, tmp_path,
):
    """Catches a hash-consistent selected DAE whose positions fail actual clearance."""
    source = passing_repeated.prepared.source
    positions = source.positions.copy()
    positions[:3, 2] = 0.0005
    original = passing_repeated.first.selected_candidate
    candidate = Candidate.from_positions(
        source.positions, source.faces, positions, status="CANDIDATE",
        source_non_position_sha256=source.non_position_sha256,
        accepted_step_scales=original.accepted_step_scales,
        rejected_iteration_count=original.rejected_iteration_count,
    )
    digest = _position_sha256(candidate)
    records = list(passing_repeated.first.records)
    index = passing_repeated.first.selected_record_index
    records[index] = replace(records[index], candidate_position_sha256=digest)
    result = _reserialized(passing_repeated.first, selected_candidate=candidate,
                           selected_position_sha256=digest, records=tuple(records))
    forged = replace(passing_repeated, first=result, second=result)
    with pytest.raises(RuntimeError, match="SEARCH_RESULT_SELECTED_GATES_MISMATCH"):
        closure.write_real_closure_artifacts(forged, workstream_root=tmp_path, created_utc="2026-09-02T00:00:00Z")
    assert not (tmp_path / "local").exists()


def test_writer_manifest_records_matching_start_end_code_and_input_snapshots(passing_repeated, tmp_path):
    """Catches attributing a completed run to code or input hashes first read at output time."""
    result = closure.write_real_closure_artifacts(
        passing_repeated, workstream_root=tmp_path, created_utc="2026-09-02T00:00:00Z", evidence_scope="SYNTHETIC_FIXTURE",
    )
    assert "run_start" in result and "run_end" in result
    assert result["run_start"] == result["run_end"]
    snapshot = result["run_start"]
    assert len(snapshot["implementation_commit"]) == 40
    paths = [entry["path"] for entry in snapshot["implementation_files"]]
    assert paths == sorted(paths)
    for filename in ("closure.py", "integration.py", "search.py", "solver.py", "geometry.py", "surface.py", "configuration.py", "models.py"):
        entry = next(entry for entry in snapshot["implementation_files"] if entry["path"].endswith("/" + filename))
        actual = (Path(closure.__file__).parent / filename).read_bytes()
        assert entry["sha256"] == hashlib.sha256(actual).hexdigest().upper()
    assert dict(snapshot["input_sha256"]) == result["input_sha256"]


@pytest.mark.parametrize("drift", ["code", "commit", "input", "before_start", "during_search", "during_validation"])
def test_isolated_process_refuses_code_commit_or_input_drift_before_emission(tmp_path, drift):
    """Catches a long-lived process emitting evidence after its loaded code/input changes."""
    # Run real code in a disposable repository, never rewrite the actual worktree.
    repository = tmp_path / "isolated"
    package = repository / "workstreams" / "padded_bgwatch_closure"
    package.mkdir(parents=True)
    for path in Path(closure.__file__).parent.glob("*.py"):
        shutil.copy2(path, package / path.name)
    for path in (repository / "workstreams" / "__init__.py",):
        path.write_text("")
    for command in (["init", "-q"], ["add", "."],
                    ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]):
        subprocess.run(["git", *command], cwd=repository, check=True, capture_output=True)
    prepared = _prepared_fixture()
    (repository / "source.dae").write_bytes(prepared.verified_source.content)
    (repository / "body.glb").write_bytes(prepared.verified_body.content)
    script = r'''
from pathlib import Path
import hashlib, subprocess
from workstreams.padded_bgwatch_closure import closure
from workstreams.padded_bgwatch_closure.integration import prepare_verified_closure
from workstreams.padded_bgwatch_closure.configuration import VerifiedInput
def verified(path, input_id):
    content = Path(path).read_bytes()
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(input_id, content, len(content), digest, digest)
prepared = prepare_verified_closure(verified("source.dae", "pristine_source_dae"), verified("body.glb", "bcb_body_glb"))
drift = DRIFT
if drift == "before_start":
    path = Path(closure.__file__).with_name("search.py")
    path.write_bytes(path.read_bytes() + b"\n# isolated drift\n")
if drift == "during_search":
    original_search = closure.run_position_only_search
    def mutate_after_search(*args, **kwargs):
        result = original_search(*args, **kwargs)
        path = Path(closure.__file__).with_name("search.py")
        path.write_bytes(path.read_bytes() + b"\n# isolated drift\n")
        return result
    closure.run_position_only_search = mutate_after_search
try:
    if drift == "input":
        repeated = closure.run_real_closure_twice(prepared, input_paths=(Path("source.dae"), Path("body.glb")))
    else:
        repeated = closure.run_real_closure_twice(prepared)
    if drift == "code":
        path = Path(closure.__file__).with_name("search.py")
        path.write_bytes(path.read_bytes() + b"\n# isolated drift\n")
    elif drift == "commit":
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "drift"], check=True)
    elif drift == "input":
        Path("body.glb").write_bytes(b"changed body bytes")
    elif drift == "during_validation":
        original_validation = closure._validate_search_result
        def mutate_after_validation(*args, **kwargs):
            result = original_validation(*args, **kwargs)
            path = Path(closure.__file__).with_name("search.py")
            path.write_bytes(path.read_bytes() + b"\n# isolated drift\n")
            return result
        closure._validate_search_result = mutate_after_validation
    closure.write_real_closure_artifacts(repeated, workstream_root=Path("output"), created_utc="2026-09-02T00:00:00Z", evidence_scope="SYNTHETIC_FIXTURE")
except RuntimeError as error:
    assert "DRIFT" in str(error), str(error)
    assert not Path("output").exists()
else:
    raise AssertionError("drift emitted evidence")
'''.replace("DRIFT", repr(drift), 1)
    completed = subprocess.run([sys.executable, "-c", script], cwd=repository, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
