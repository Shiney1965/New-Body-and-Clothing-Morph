"""Real two-run offline closure and ignored evidence emission."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
from pathlib import Path

import numpy as np

from .configuration import WORKSTREAM_ROOT, generated_output_path
from .geometry import serialize_collada_positions
from .integration import PreparedClosure, prepare_real_closure, roundtrip_candidate
from .search import OFFLINE_CANDIDATE, SearchResult, run_position_only_search


LEGACY_FINDINGS_PATH = Path(
    r"C:\Claude Projects\BG3 Mods\ChatGPT Work Files"
    r"\Padded_BGWatch_TopologyRecovery_20260826\TOPOLOGY_RECOVERY_FINDINGS.md"
)
LEGACY_FINDINGS_SHA256 = "CDD5CBAE21FC88BABAFC1893F5D7BA1B4B5C34FDECDAD64671D45B5EEC96ADA8"
ROUTE_IDENTITY = {
    "source_profile_id": "LARIAN_PADDED_DAE_DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262",
    "mode": "bcb",
    "base_visual_uuid": "a2edea05-8d9d-4d60-c128-6484fec0727c",
    "component": "HUM_F_ARM_BG_Watch_Leather_A_Body",
    "behavior": "BCB-mode no-BCBPak covering fallback",
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def build_terminal_exclusion_event(
    *,
    search_evidence_path: Path,
    search_evidence_sha256: str,
    created_utc: str,
) -> dict[str, object]:
    """Build one canonical policy event for bounded safe-architecture exhaustion."""
    identity_sha256 = _sha256_bytes(_canonical_json(ROUTE_IDENTITY))
    event: dict[str, object] = {
        "schema": "clothmorph.terminal-exclusion",
        "schema_version": 1,
        "record_id": f"LEDGER_{identity_sha256}",
        "identity_sha256": identity_sha256,
        "source_profile_id": ROUTE_IDENTITY["source_profile_id"],
        "mode": "bcb",
        "reason": "NO_SAFE_GEOMETRY_AVAILABLE",
        "scope_statement": (
            "Remove the BCB-mode, BCBPak-absent automatic covering fallback for "
            "HUM_F_ARM_BG_Watch_Leather_A_Body from the advertised release."
        ),
        "attempted_architectures": [
            "smooth nearest-vertex body transfer",
            "global nearest-target-vertex-normal clipping",
            "strict global alpha interpolation",
            "confident-penetration per-vertex incident-face backtracking",
            "connected-per-component ROI Laplacian position-only 160-case search",
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
        "evidence": [
            {
                "path": str(search_evidence_path),
                "sha256": search_evidence_sha256,
                "claim": "All 160 fixed position-only cases and every fixed gate result.",
            },
            {
                "path": str(LEGACY_FINDINGS_PATH),
                "sha256": LEGACY_FINDINGS_SHA256,
                "claim": "Retained prior architecture outcomes and protected-route boundary.",
            },
        ],
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
        "approved_by": "Alan",
        "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
        "created_utc": created_utc,
    }
    event["event_id"] = f"EXCLUSION_{_sha256_bytes(_canonical_json(event))}"
    return event


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


def write_real_closure_artifacts(
    repeated: RepeatedClosure,
    *,
    workstream_root: Path = WORKSTREAM_ROOT,
    created_utc: str,
) -> dict[str, object]:
    """Write only ignored offline evidence and an optional passing DAE."""
    generated = generated_output_path(workstream_root, "position_only_search.json").parent
    generated.mkdir(parents=True, exist_ok=True)
    search_path = generated / "position_only_search.json"
    search_path.write_bytes(repeated.first.json_bytes)
    search_sha256 = _sha256_bytes(repeated.first.json_bytes)
    candidate_path = generated / "HUM_F_ARM_BG_Watch_Leather_A_Body_CMcover_candidate.dae"
    event_path = generated / "terminal_exclusion_event_input.json"
    if repeated.first.status == OFFLINE_CANDIDATE:
        if repeated.first.selected_candidate is None:
            raise RuntimeError("PASS_STATUS_WITHOUT_SELECTED_CANDIDATE")
        candidate_bytes = serialize_collada_positions(
            repeated.prepared.verified_source,
            repeated.prepared.source,
            repeated.first.selected_candidate.positions,
        )
        candidate_path.write_bytes(candidate_bytes)
        candidate_sha256 = _sha256_bytes(candidate_bytes)
        if event_path.exists():
            event_path.unlink()
    else:
        candidate_sha256 = None
        if candidate_path.exists():
            candidate_path.unlink()
        event = build_terminal_exclusion_event(
            search_evidence_path=search_path,
            search_evidence_sha256=search_sha256,
            created_utc=created_utc,
        )
        event_path.write_bytes(_canonical_json(event) + b"\n")
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
            "bcb_body_glb": repeated.prepared.body and "51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C",
        },
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
        "created_utc": created_utc,
        "claims_not_established": [
            "GR2", "PAK", "installation", "gameplay", "visual acceptance", "release readiness",
        ],
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True,
    ).encode("utf-8") + b"\n"
    manifest_path = generated / "real_closure_manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    return {**manifest, "manifest_sha256": _sha256_bytes(manifest_bytes)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the hash-locked Padded position-only closure twice")
    parser.add_argument("--created-utc")
    args = parser.parse_args()
    created_utc = args.created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    repeated = run_real_closure_twice()
    manifest = write_real_closure_artifacts(repeated, created_utc=created_utc)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
