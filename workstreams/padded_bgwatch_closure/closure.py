"""Real two-run offline closure and ignored evidence emission."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from .configuration import WORKSTREAM_ROOT, generated_output_path
from .geometry import serialize_collada_positions
from .integration import PreparedClosure, prepare_real_closure, roundtrip_candidate
from .search import (
    OFFLINE_CANDIDATE,
    POSITION_ONLY_UNFIXABLE,
    SearchResult,
    _position_sha256,
    _serialize_result,
    build_parameter_grid,
    run_position_only_search,
)


LEGACY_FINDINGS_PATH = Path(
    r"C:\Claude Projects\BG3 Mods\ChatGPT Work Files"
    r"\Padded_BGWatch_TopologyRecovery_20260826\TOPOLOGY_RECOVERY_FINDINGS.md"
)
LEGACY_EVIDENCE_ROOT = LEGACY_FINDINGS_PATH.parent
LEGACY_ARTIFACT_MANIFEST_PATH = LEGACY_EVIDENCE_ROOT / "evidence" / "ARTIFACT_MANIFEST.json"
LEGACY_ARTIFACT_MANIFEST_SHA256 = "68D69D210AA12388D72EA945B1FA9978D3C628E1CBAF474ED4452A9BCE4BCDCE"

# These are architecture labels only.  They deliberately do not infer a
# release-ledger record, a source profile, or canonical route identity.
PRIOR_ARCHITECTURE_EVIDENCE = {
    "smooth_nearest_vertex_body_transfer": (
        "TOPOLOGY_RECOVERY_FINDINGS.md",
        "evidence/deformation_stage_probe.json",
        "evidence/source_dae_lod0_topology.json",
    ),
    "global_nearest_target_vertex_normal_clipping": (
        "TOPOLOGY_RECOVERY_FINDINGS.md",
        "evidence/deformation_stage_probe.json",
        "evidence/source_dae_lod0_topology.json",
    ),
    "strict_global_alpha_interpolation": (
        "TOPOLOGY_RECOVERY_FINDINGS.md",
        "CLEARANCE_COMPARISON.md",
        "evidence/prototype_manifest.json",
        "evidence/four_way_clearance.json",
    ),
    "confidence_gated_local_clearance_repair": (
        "CLEARANCE_COMPARISON.md",
        "evidence/four_way_clearance.json",
        "evidence/local_repair_manifest.json",
    ),
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _load_registered_prior_artifacts() -> tuple[dict[str, object], ...]:
    """Revalidate the complete retained prior-evidence corpus before citing it."""
    manifest_bytes = LEGACY_ARTIFACT_MANIFEST_PATH.read_bytes()
    if _sha256_bytes(manifest_bytes) != LEGACY_ARTIFACT_MANIFEST_SHA256:
        raise RuntimeError("LEGACY_ARTIFACT_MANIFEST_HASH_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("LEGACY_ARTIFACT_MANIFEST_INVALID") from error
    records = manifest.get("records") if isinstance(manifest, dict) else None
    if not isinstance(records, list) or manifest.get("record_count") != len(records):
        raise RuntimeError("LEGACY_ARTIFACT_MANIFEST_RECORD_COUNT_INVALID")

    root = LEGACY_EVIDENCE_ROOT.resolve(strict=True)
    registered: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("LEGACY_ARTIFACT_MANIFEST_RECORD_INVALID")
        relative_path = record.get("relative_path")
        expected_sha256 = record.get("sha256")
        expected_bytes = record.get("bytes")
        if (
            not isinstance(relative_path, str)
            or not isinstance(expected_sha256, str)
            or not isinstance(expected_bytes, int)
            or relative_path in seen_paths
        ):
            raise RuntimeError("LEGACY_ARTIFACT_MANIFEST_RECORD_INVALID")
        candidate = (root / relative_path).resolve(strict=False)
        if root not in candidate.parents:
            raise RuntimeError("LEGACY_ARTIFACT_PATH_OUTSIDE_RETAINED_ROOT")
        try:
            content = candidate.read_bytes()
        except OSError as error:
            raise RuntimeError(f"LEGACY_ARTIFACT_UNREADABLE:{relative_path}") from error
        actual_sha256 = _sha256_bytes(content)
        if len(content) != expected_bytes or actual_sha256 != expected_sha256:
            raise RuntimeError(f"LEGACY_ARTIFACT_HASH_MISMATCH:{relative_path}")
        seen_paths.add(relative_path)
        registered.append({
            "path": relative_path,
            "bytes": expected_bytes,
            "sha256": expected_sha256,
            "verified_sha256": actual_sha256,
        })

    required_paths = {
        path for paths in PRIOR_ARCHITECTURE_EVIDENCE.values() for path in paths
    }
    if not required_paths.issubset(seen_paths):
        raise RuntimeError("LEGACY_ARCHITECTURE_EVIDENCE_UNREGISTERED")
    return tuple(registered)


def build_pending_exclusion_evidence_packet(
    *,
    search_evidence_path: Path,
    search_evidence_sha256: str,
    created_utc: str,
    search_evidence_bytes: bytes | None = None,
) -> dict[str, object]:
    """Build non-attachable offline evidence; it is not a terminal policy event."""
    search_content = (
        search_evidence_path.read_bytes()
        if search_evidence_bytes is None else search_evidence_bytes
    )
    actual_search_sha256 = _sha256_bytes(search_content)
    if actual_search_sha256 != search_evidence_sha256:
        raise RuntimeError("SEARCH_EVIDENCE_HASH_MISMATCH")
    registered = _load_registered_prior_artifacts()
    packet: dict[str, object] = {
        "schema": "clothmorph.padded-position-only-pending-exclusion-evidence",
        "schema_version": 1,
        "attachment_status": "NOT_ATTACHABLE_SOURCE_PROFILE_AND_CANONICAL_BINDING_UNRESOLVED",
        "attachment_blocker": (
            "The current private route label cannot be attached to a verified "
            "canonical release-ledger record or base-game source profile."
        ),
        "mode": "bcb",
        "reason": "NO_SAFE_GEOMETRY_AVAILABLE",
        "scope_statement": (
            "Offline evidence packet for the Padded BG Watch position-only "
            "search; it cannot alter advertised release scope until an exact "
            "source profile and canonical ledger binding are independently verified."
        ),
        "current_search_evidence": {
            "path": str(search_evidence_path),
            "sha256": search_evidence_sha256,
            "claim": "All 160 fixed current position-only cases and their gate results.",
        },
        "prior_artifact_manifest": {
            "path": str(LEGACY_ARTIFACT_MANIFEST_PATH),
            "sha256": LEGACY_ARTIFACT_MANIFEST_SHA256,
            "record_count": len(registered),
        },
        "registered_prior_artifacts": list(registered),
        "prior_architectures": [
            {"name": name, "evidence_paths": list(paths)}
            for name, paths in PRIOR_ARCHITECTURE_EVIDENCE.items()
        ],
        "fixed_acceptance_gates": {
            "source_dae_sha256": "DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262",
            "bcb_body_glb_sha256": "51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C",
            "active_vertex_count": 593,
            "target_clearance_m": 0.001,
            "fixed_cohort_count": 2800,
            "fixed_cohort_coverage_loss_max": 0,
            "flipped_faces_max": 0,
            "new_zero_area_faces_max": 0,
            "published_area_ratio": [0.5, 2.0],
            "internal_area_ratio": [0.51, 1.99],
            "minimum_orientation_cosine": 0.05,
            "parameter_case_count": 160,
            "serialization_decimals": 6,
        },
        "protected_impact": {
            "registry_ids": [],
            "shared_consumers": [
                "Vanilla df79058a-eff5-5714-a2a0-b604ed0e15fb",
                "SBBF e43c7005-ab47-573c-a851-c0f88d82bd90",
                "BCBPak-present 80c1daa4-cecf-5dc1-8c8a-1b7ab599395c",
            ],
            "forbidden_targets": [
                "protected Vanilla route",
                "protected SBBF route",
                "protected BCBPak-present authored route",
            ],
            "result": "NO_PROTECTED_MUTATION",
        },
        "next_project_if_reopened": (
            "separately approved manual-remesh or licensed source-replacement project"
        ),
        "created_utc": created_utc,
    }
    return packet


@dataclass(frozen=True)
class RepeatedClosure:
    prepared: PreparedClosure
    first: SearchResult
    second: SearchResult


def run_real_closure_twice(prepared: PreparedClosure | None = None) -> RepeatedClosure:
    """Execute both complete searches and require byte-identical evidence."""
    prepared = prepared or prepare_real_closure()
    roundtrip = partial(roundtrip_candidate, prepared.verified_source, prepared.source)
    first = run_position_only_search(
        prepared.source, prepared.contract, candidate_roundtrip=roundtrip,
    )
    second = run_position_only_search(
        prepared.source, prepared.contract, candidate_roundtrip=roundtrip,
    )
    if first.json_bytes != second.json_bytes:
        raise RuntimeError("REAL_SEARCH_JSON_NONDETERMINISTIC")
    if first.selected_position_sha256 != second.selected_position_sha256:
        raise RuntimeError("REAL_SEARCH_SELECTION_NONDETERMINISTIC")
    return RepeatedClosure(prepared=prepared, first=first, second=second)


def _validate_repeated_closure(repeated: RepeatedClosure) -> None:
    """Independently enforce the two-run claim immediately before artifact writes."""
    if repeated.first.json_bytes != repeated.second.json_bytes:
        raise RuntimeError("REPEATED_CLOSURE_JSON_MISMATCH")
    if repeated.first.selected_position_sha256 != repeated.second.selected_position_sha256:
        raise RuntimeError("REPEATED_CLOSURE_SELECTION_MISMATCH")
    if repeated.first.status != repeated.second.status:
        raise RuntimeError("REPEATED_CLOSURE_STATUS_MISMATCH")
    _validate_prepared_closure(repeated.prepared)
    _validate_search_result(repeated.first, repeated.prepared)
    _validate_search_result(repeated.second, repeated.prepared)


def _validate_verified_input(value: object, input_id: str, code: str) -> None:
    if not hasattr(value, "input_id") or value.input_id != input_id:
        raise RuntimeError(f"PREPARED_{code}_INPUT_ID_INVALID")
    actual = _sha256_bytes(value.content)
    if value.byte_count != len(value.content) or actual != value.actual_sha256 or actual != value.expected_sha256:
        raise RuntimeError(f"PREPARED_{code}_DIGEST_INVALID")


def _validate_prepared_closure(prepared: PreparedClosure) -> None:
    """Revalidate both verified bytes and the stored BCB normal oracle identity."""
    _validate_verified_input(prepared.verified_source, "pristine_source_dae", "SOURCE")
    _validate_verified_input(prepared.verified_body, "bcb_body_glb", "BODY")
    if prepared.source.content_sha256 != prepared.verified_source.actual_sha256:
        raise RuntimeError("PREPARED_SOURCE_PARSED_DIGEST_MISMATCH")
    normal_sha256 = _sha256_bytes(np.asarray(
        prepared.body.vertex_normals, dtype="<f8",
    ).tobytes(order="C"))
    if normal_sha256 != prepared.body_vertex_normals_sha256:
        raise RuntimeError("PREPARED_BCB_NORMAL_ORACLE_DIGEST_MISMATCH")
    if prepared.contract.constraints.body_mesh is not prepared.body:
        raise RuntimeError("PREPARED_CONSTRAINT_ORACLE_MISMATCH")


def _validate_search_result(result: SearchResult, prepared: PreparedClosure) -> None:
    """Reject hand-constructed search evidence that cannot be a literal 160-case run."""
    grid = build_parameter_grid()
    if len(result.records) != len(grid):
        raise RuntimeError("SEARCH_RESULT_RECORD_COUNT_INVALID")
    if any(record.index != index or record.parameters != parameters for index, (record, parameters) in enumerate(zip(result.records, grid))):
        raise RuntimeError("SEARCH_RESULT_LITERAL_GRID_INVALID")
    actual_passing = tuple(record.index for record in result.records if record.gates.production_passed)
    if result.passing_count != len(actual_passing):
        raise RuntimeError("SEARCH_RESULT_PASSING_COUNT_INVALID")
    expected_bytes = _serialize_result(
        result.status, result.records, result.passing_count,
        result.selected_record_index, result.selected_position_sha256,
    )
    try:
        parsed = json.loads(result.json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("SEARCH_RESULT_JSON_INVALID") from error
    if result.json_bytes != expected_bytes or parsed != json.loads(expected_bytes.decode("utf-8")):
        raise RuntimeError("SEARCH_RESULT_JSON_FIELDS_MISMATCH")
    if result.passing_count == 0:
        if (
            result.status != POSITION_ONLY_UNFIXABLE
            or result.selected_record_index is not None
            or result.selected_position_sha256 is not None
            or result.selected_candidate is not None
        ):
            raise RuntimeError("SEARCH_RESULT_ZERO_BRANCH_INVALID")
        return
    if result.status != OFFLINE_CANDIDATE or result.selected_candidate is None:
        raise RuntimeError("SEARCH_RESULT_PASS_BRANCH_INVALID")
    if result.selected_record_index != actual_passing[0]:
        raise RuntimeError("SEARCH_RESULT_SELECTED_INDEX_INVALID")
    selected_record = result.records[result.selected_record_index]
    actual_sha256 = _position_sha256(result.selected_candidate)
    readback = roundtrip_candidate(prepared.verified_source, prepared.source, result.selected_candidate)
    readback_sha256 = _position_sha256(readback)
    if (
        result.selected_position_sha256 != actual_sha256
        or actual_sha256 != readback_sha256
        or selected_record.candidate_position_sha256 != actual_sha256
    ):
        raise RuntimeError("SEARCH_RESULT_SELECTED_HASH_INVALID")


def _refuse_existing_artifacts(paths: tuple[Path, ...]) -> None:
    """Fail closed instead of deleting or overwriting a previous evidence packet."""
    for path in paths:
        if path.exists():
            raise FileExistsError(f"CLOSURE_ARTIFACT_PATH_ALREADY_EXISTS:{path}")


def _write_new_bytes(path: Path, content: bytes) -> None:
    """Write only a new artifact, leaving any raced/stale artifact untouched."""
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError as error:
        raise FileExistsError(f"CLOSURE_ARTIFACT_PATH_ALREADY_EXISTS:{path}") from error


def write_real_closure_artifacts(
    repeated: RepeatedClosure,
    *,
    workstream_root: Path = WORKSTREAM_ROOT,
    created_utc: str,
    run_id: str | None = None,
) -> dict[str, object]:
    """Write a fresh offline packet only after revalidating determinism and paths."""
    _validate_repeated_closure(repeated)
    generated = generated_output_path(workstream_root, "position_only_search.json").parent
    if run_id is not None:
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", run_id) is None:
            raise ValueError("CLOSURE_RUN_ID_INVALID")
        generated = generated / "runs" / run_id
    search_path = generated / "position_only_search.json"
    search_sha256 = _sha256_bytes(repeated.first.json_bytes)
    candidate_path = generated / "HUM_F_ARM_BG_Watch_Leather_A_Body_CMcover_candidate.dae"
    packet_path = generated / "pending_exclusion_evidence_packet.json"
    manifest_path = generated / "real_closure_manifest.json"
    _refuse_existing_artifacts((search_path, candidate_path, packet_path, manifest_path))

    candidate_bytes: bytes | None = None
    packet_bytes: bytes | None = None
    if repeated.first.status == OFFLINE_CANDIDATE:
        if repeated.first.selected_candidate is None:
            raise RuntimeError("PASS_STATUS_WITHOUT_SELECTED_CANDIDATE")
        candidate_bytes = serialize_collada_positions(
            repeated.prepared.verified_source,
            repeated.prepared.source,
            repeated.first.selected_candidate.positions,
        )
        candidate_sha256 = _sha256_bytes(candidate_bytes)
    elif repeated.first.status == POSITION_ONLY_UNFIXABLE:
        candidate_sha256 = None
        packet = build_pending_exclusion_evidence_packet(
            search_evidence_path=search_path,
            search_evidence_sha256=search_sha256,
            created_utc=created_utc,
            search_evidence_bytes=repeated.first.json_bytes,
        )
        packet_bytes = _canonical_json(packet) + b"\n"
    else:
        raise RuntimeError("CLOSURE_STATUS_UNRECOGNIZED")
    active_digest = _sha256_bytes(np.asarray(
        repeated.prepared.active_ids, dtype="<i8",
    ).tobytes(order="C"))
    cohort_digest = _sha256_bytes(np.asarray(
        repeated.prepared.coverage.body_vertex_ids, dtype="<i8",
    ).tobytes(order="C"))
    manifest = {
        "schema_version": 1,
        "status": repeated.first.status,
        "offline_only": True,
        "search_sha256": search_sha256,
        "candidate_dae_sha256": candidate_sha256,
        "input_sha256": {
            "pristine_source_dae": repeated.prepared.verified_source.actual_sha256,
            "bcb_body_glb": repeated.prepared.verified_body.actual_sha256,
        },
        "bcb_vertex_normals_sha256": repeated.prepared.body_vertex_normals_sha256,
        "source_vertex_count": len(repeated.prepared.source.positions),
        "source_face_count": len(repeated.prepared.source.faces),
        "active_vertex_count": len(repeated.prepared.active_ids),
        "active_vertex_ids_sha256": active_digest,
        "fixed_cohort_count": len(repeated.prepared.coverage.body_vertex_ids),
        "fixed_cohort_ids_sha256": cohort_digest,
        "roi_movable_count": len(repeated.prepared.contract.roi.movable_ids),
        "roi_boundary_count": len(repeated.prepared.contract.roi.boundary_ids),
        "passing_count": repeated.first.passing_count,
        "selected_record_index": repeated.first.selected_record_index,
        "two_run_json_identical": True,
        "two_run_selected_hash_identical": True,
        "pending_exclusion_evidence_packet_sha256": (
            _sha256_bytes(packet_bytes) if packet_bytes is not None else None
        ),
        "created_utc": created_utc,
        "claims_not_established": [
            "GR2", "PAK", "installation", "gameplay", "visual acceptance", "release readiness",
        ],
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True,
    ).encode("utf-8") + b"\n"
    generated.mkdir(parents=True, exist_ok=True)
    _write_new_bytes(search_path, repeated.first.json_bytes)
    if candidate_bytes is not None:
        _write_new_bytes(candidate_path, candidate_bytes)
    if packet_bytes is not None:
        _write_new_bytes(packet_path, packet_bytes)
    _write_new_bytes(manifest_path, manifest_bytes)
    return {**manifest, "manifest_sha256": _sha256_bytes(manifest_bytes)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the hash-locked Padded position-only closure twice")
    parser.add_argument("--created-utc")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    created_utc = args.created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    repeated = run_real_closure_twice()
    manifest = write_real_closure_artifacts(
        repeated, created_utc=created_utc, run_id=args.run_id,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
