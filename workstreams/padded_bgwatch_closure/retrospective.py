"""Read frozen candidates without reconstructing their historical generators.

The only verdict is an explicitly nonterminal evidence crosswalk. A current
necessary-gate failure concerns these bytes, not all possible implementations.
This module never emits a candidate, a policy event, or a production PASS.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

from . import geometry, solver
from .configuration import VerifiedInput
from .integration import derive_fixed_coverage_contract, derive_original_active_ids
from .surface import exact_closest_points


PROFILE_PATH = Path(__file__).with_name("contracts") / "retrospective_readback_v1.json"
PROFILE_SHA256 = "A5B4DFA883F17105C18712D4087B530F5E68F5811596430157D36E241CB03B7C"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


def _json(content: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    value = json.loads(content, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


@dataclass(frozen=True)
class ReadbackProfile:
    """Immutable LF-normalized contract bytes; detached JSON views cannot mutate it."""

    content: bytes

    def __post_init__(self):
        if type(self.content) is not bytes or _sha(self.content) != PROFILE_SHA256:
            raise ValueError("PROFILE_DIGEST_MISMATCH")

    @property
    def document(self) -> dict:
        return _json(self.content)


def load_profile() -> ReadbackProfile:
    # Git may check a text contract out with CRLF. Its semantic LF byte pin is
    # deliberately portable; source/candidate/manifest bytes are NEVER normalized.
    return ReadbackProfile(PROFILE_PATH.read_bytes().replace(b"\r\n", b"\n"))


@dataclass(frozen=True)
class ManifestLink:
    content: bytes
    expected_sha256: str
    member_path: str

    def __post_init__(self):
        if type(self.content) is not bytes or type(self.member_path) is not str:
            raise TypeError("MANIFEST_IMMUTABLE_BYTES_AND_PATH_REQUIRED")


@dataclass(frozen=True)
class FrozenArtifact:
    content: bytes
    provenance: tuple[ManifestLink, ...]

    def __post_init__(self):
        if type(self.content) is not bytes or type(self.provenance) is not tuple:
            raise TypeError("ARTIFACT_IMMUTABLE_BYTES_AND_TUPLE_REQUIRED")
        if any(type(link) is not ManifestLink for link in self.provenance):
            raise TypeError("ARTIFACT_IMMUTABLE_MANIFEST_LINK_REQUIRED")


def _member(link: ManifestLink) -> dict:
    if _sha(link.content) != link.expected_sha256:
        raise ValueError("MANIFEST_DIGEST_MISMATCH")
    doc = _json(link.content)
    records = doc.get("records")
    if not isinstance(records, list) or doc.get("record_count", len(records)) != len(records):
        raise ValueError("MANIFEST_RECORDS_INVALID")
    paths = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("MANIFEST_RECORD_INVALID")
        path = record.get("relative_path", record.get("path"))
        if (not isinstance(path, str) or not path or path in paths
                or type(record.get("bytes")) is not int or record["bytes"] < 0
                or re.fullmatch(r"[0-9A-F]{64}", str(record.get("sha256"))) is None):
            raise ValueError("MANIFEST_RECORD_INVALID")
        paths.append(path)
    matches = [record for record, path in zip(records, paths) if path == link.member_path]
    if len(matches) != 1:
        raise ValueError("MANIFEST_MEMBER_NOT_UNIQUE")
    return matches[0]


def verify_artifact(artifact: FrozenArtifact) -> str:
    """Verify every parent-selected child, terminating at the exact leaf bytes."""
    if type(artifact) is not FrozenArtifact or not artifact.provenance:
        raise ValueError("ARTIFACT_PROVENANCE_REQUIRED")
    for index, link in enumerate(artifact.provenance):
        record = _member(link)
        child = (artifact.provenance[index + 1].content
                 if index + 1 < len(artifact.provenance) else artifact.content)
        if len(child) != record["bytes"] or _sha(child) != record["sha256"]:
            code = "MANIFEST_CHAIN_MISMATCH" if index + 1 < len(artifact.provenance) else "ARTIFACT_DIGEST_MISMATCH"
            raise ValueError(code)
    return _sha(artifact.content)


def _inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if Path(relative).is_absolute() or root not in candidate.parents:
        raise ValueError("MANIFEST_PATH_OUTSIDE_ROOT")
    return candidate


def read_manifest_artifact(
    corpus_root: Path, artifact_sha256: str, *, expected_manifest_sha256: str | None = None,
) -> FrozenArtifact:
    """Read one exact digest from a verified root or its source/control manifest.

    An alternate manifest digest is useful for portable readers/tests but grants
    no canonical authority: the evaluator separately requires the pinned root.
    No caller-supplied leaf path or filename fallback exists.
    """
    corpus = load_profile().document["corpus"]
    root = Path(corpus_root).resolve(strict=True)
    expected = expected_manifest_sha256 or corpus["artifact_manifest_sha256"]
    content = _inside(root, corpus["artifact_manifest_path"]).read_bytes()
    if _sha(content) != expected:
        raise ValueError("MANIFEST_DIGEST_MISMATCH")
    records = _json(content).get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("MANIFEST_RECORDS_INVALID")
    # Validate every root row without reading unrelated protected source files.
    first_path = records[0].get("relative_path") if isinstance(records[0], dict) else None
    _member(ManifestLink(content, expected, first_path))
    matches = [(record, None) for record in records if record["sha256"] == artifact_sha256]
    control = [record for record in records if record.get("relative_path") == corpus["source_control_path"]]
    child_content = None
    if control:
        parent_link = ManifestLink(content, expected, corpus["source_control_path"])
        child_content = _inside(root, corpus["source_control_path"]).read_bytes()
        verify_artifact(FrozenArtifact(child_content, (parent_link,)))
        child_records = _json(child_content).get("records")
        if not isinstance(child_records, list) or not child_records:
            raise ValueError("MANIFEST_RECORDS_INVALID")
        first_child = child_records[0].get("path") if isinstance(child_records[0], dict) else None
        _member(ManifestLink(child_content, control[0]["sha256"], first_child))
        matches.extend((record, parent_link) for record in child_records if record["sha256"] == artifact_sha256)
    if len(matches) != 1:
        raise ValueError("MANIFEST_DIGEST_MEMBER_NOT_UNIQUE")
    record, parent_link = matches[0]
    if parent_link is None:
        member_path = record["relative_path"]
        path = _inside(root, member_path)
        chain = (ManifestLink(content, expected, member_path),)
    else:
        member_path = record["path"]
        # The source/control manifest intentionally names retained files outside
        # its own directory. Their exact paths and bytes are pinned by the root.
        external = Path(member_path)
        path = external.resolve(strict=True) if external.is_absolute() else _inside(root, member_path)
        chain = (parent_link, ManifestLink(child_content, control[0]["sha256"], member_path))
    artifact = FrozenArtifact(path.read_bytes(), chain)
    verify_artifact(artifact)
    return artifact


@dataclass(frozen=True)
class ReadbackInputs:
    source: FrozenArtifact
    body: FrozenArtifact
    candidate: FrozenArtifact
    candidate_name: str
    geometry_id: str
    evidence_scope: str = "CANONICAL_PADDED"


def _verified(artifact: FrozenArtifact, input_id: str) -> VerifiedInput:
    digest = verify_artifact(artifact)
    return VerifiedInput(input_id, artifact.content, len(artifact.content), digest, digest)


def _geometry_inventory(content: bytes) -> dict:
    root = ET.fromstring(content)
    ids = [node.get("id") for node in root.findall(".//c:library_geometries/c:geometry", geometry.NS)]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("GEOMETRY_SELECTION_NONUNIQUE_IDS")
    return {
        "geometry_ids": ids,
        "controller_ids": [node.get("id") for node in root.findall(".//c:library_controllers/c:controller", geometry.NS)],
        "material_ids": [node.get("id") for node in root.findall(".//c:library_materials/c:material", geometry.NS)],
        "scope": "PRESENT_IN_RETAINED_DAE_ONLY_NOT_COMPLETE_ROUTE_PROOF",
    }


def _parse_selected(artifact: FrozenArtifact, geometry_id: str):
    inventory = _geometry_inventory(artifact.content)
    if not geometry_id or geometry_id not in inventory["geometry_ids"]:
        raise ValueError("GEOMETRY_SELECTION_MISSING")
    parsed = geometry.parse_collada_geometry(_verified(artifact, "pristine_source_dae"))
    # Existing parser chooses the largest geometry. Never silently treat that
    # heuristic as identity: require the actual pinned pristine Mesh ID.
    if parsed.geometry_id != geometry_id:
        raise ValueError("GEOMETRY_SELECTION_MISMATCH")
    return parsed, inventory


def _ids(values) -> list[int]:
    return [int(value) for value in values]


def _ids_hash(values) -> str:
    return _sha(np.asarray(values, dtype="<i8").tobytes())


def _measurement(values, domain: str) -> dict:
    ids = _ids(values)
    return {"count": len(ids), "ids": ids, "id_domain": domain}


def _validate_profile_constants(doc):
    gates = doc["gates"]
    comparisons = (
        (gates["published_area_ratio"], [solver.PUBLISHED_MIN_AREA_RATIO, solver.PUBLISHED_MAX_AREA_RATIO]),
        (gates["current_internal_area_ratio"], [solver.INTERNAL_MIN_AREA_RATIO, solver.INTERNAL_MAX_AREA_RATIO]),
        (gates["minimum_orientation_cosine"], solver.INTERNAL_MIN_ORIENTATION_COSINE),
        (gates["zero_area_epsilon"], solver.ZERO_AREA_EPSILON),
        (gates["target_clearance_m"], geometry.TARGET_CLEARANCE_M),
        (gates["serialization_decimals"], solver.SERIALIZATION_DECIMALS),
    )
    if any(expected != actual for expected, actual in comparisons):
        raise ValueError("PROFILE_IMPLEMENTATION_GATE_MISMATCH")


def _canonical_bindings(inputs, doc, source, body, active, cohort):
    if inputs.evidence_scope == "SYNTHETIC_FIXTURE":
        return
    if inputs.evidence_scope != "CANONICAL_PADDED":
        raise ValueError("EVIDENCE_SCOPE_INVALID")
    pairs = ((inputs.source, doc["source"]["sha256"]),
             (inputs.body, doc["body"]["sha256"]),
             (inputs.candidate, doc["candidates"][inputs.candidate_name]["sha256"]))
    if any(_sha(artifact.content) != expected for artifact, expected in pairs):
        raise ValueError("CANONICAL_ARTIFACT_IDENTITY_MISMATCH")
    root_sha = doc["corpus"]["artifact_manifest_sha256"]
    if any(artifact.provenance[0].expected_sha256 != root_sha for artifact, _ in pairs):
        raise ValueError("CANONICAL_MANIFEST_IDENTITY_MISMATCH")
    if (inputs.geometry_id != doc["source"]["geometry_id"]
            or len(source.positions) != doc["source"]["vertex_count"]
            or len(source.faces) != doc["source"]["face_count"]
            or len(body.positions) != doc["body"]["vertex_count"]
            or len(body.faces) != doc["body"]["face_count"]
            or len(active) != doc["source"]["active_count"]
            or _ids_hash(active) != doc["source"]["active_ids_le_i8_sha256"]
            or len(cohort.body_vertex_ids) != doc["body"]["fixed_cohort_count"]
            or _ids_hash(cohort.body_vertex_ids) != doc["body"]["fixed_cohort_ids_le_i8_sha256"]):
        raise ValueError("CANONICAL_GEOMETRY_COHORT_IDENTITY_MISMATCH")


def _topology_measurements(source, candidate):
    """Add IDs unavailable in the existing count API; cross-check every count."""
    before = source.positions[source.faces]
    after = candidate.positions[source.faces]
    a = np.cross(before[:, 1] - before[:, 0], before[:, 2] - before[:, 0])
    b = np.cross(after[:, 1] - after[:, 0], after[:, 2] - after[:, 0])
    lengths_a, lengths_b = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1)
    ratios = lengths_b / lengths_a
    dot = np.einsum("ij,ij->i", a, b)
    cosine = np.divide(dot, lengths_a * lengths_b, out=np.full_like(dot, -np.inf),
                       where=lengths_b > solver.ZERO_AREA_EPSILON)
    masks = {
        "flipped_faces": dot < 0,
        "new_zero_area_faces": lengths_b <= solver.ZERO_AREA_EPSILON,
        "faces_below_published_area": ratios < solver.PUBLISHED_MIN_AREA_RATIO,
        "faces_above_published_area": ratios > solver.PUBLISHED_MAX_AREA_RATIO,
        "faces_below_internal_area": ratios < solver.INTERNAL_MIN_AREA_RATIO,
        "faces_above_internal_area": ratios > solver.INTERNAL_MAX_AREA_RATIO,
        "faces_below_orientation_cosine": cosine < solver.INTERNAL_MIN_ORIENTATION_COSINE,
    }
    counts = solver._topology_metrics(source.positions, candidate.positions, source.faces)
    measured = {name: _measurement(np.flatnonzero(mask), "selected_source_triangle_index")
                for name, mask in masks.items()}
    if any(value["count"] != getattr(counts, name) for name, value in measured.items()):
        raise ValueError("TOPOLOGY_FAILURE_ID_COUNT_MISMATCH")
    extrema = {name: (float(getattr(counts, name)) if np.isfinite(getattr(counts, name)) else None)
               for name in ("minimum_area_ratio", "maximum_area_ratio", "minimum_orientation_cosine")}
    return measured, extrema


def _clearance_measurements(positions, body, ids, prefix):
    if not ids:
        return {prefix + "_vertices_below_clearance": _measurement([], "selected_source_vertex_index"),
                prefix + "_surface_ambiguities": _measurement([], "selected_source_vertex_index")}
    query = geometry.query_signed_clearance(positions[np.asarray(ids)], body)
    below = (query.signed_clearances < geometry.TARGET_CLEARANCE_M - 1e-12) | query.ambiguous
    return {prefix + "_vertices_below_clearance": _measurement(np.asarray(ids)[below], "selected_source_vertex_index"),
            prefix + "_surface_ambiguities": _measurement(np.asarray(ids)[query.ambiguous], "selected_source_vertex_index")}


_FAILURES = {
    "flipped_faces": "FLIPPED_FACES", "new_zero_area_faces": "NEW_ZERO_AREA_FACES",
    "faces_below_published_area": "PUBLISHED_MINIMUM_AREA_RATIO_FAILED",
    "faces_above_published_area": "PUBLISHED_MAXIMUM_AREA_RATIO_FAILED",
    "faces_below_internal_area": "INTERNAL_MINIMUM_AREA_RATIO_FAILED",
    "faces_above_internal_area": "INTERNAL_MAXIMUM_AREA_RATIO_FAILED",
    "faces_below_orientation_cosine": "INTERNAL_ORIENTATION_COSINE_FAILED",
    "active_vertices_below_clearance": "ACTIVE_CLEARANCE_NOT_MET",
    "active_surface_ambiguities": "ACTIVE_SURFACE_AMBIGUITY",
    "fixed_cohort_coverage_loss": "FIXED_COHORT_COVERAGE_LOSS",
}


def _evaluate_once(inputs: ReadbackInputs, profile: ReadbackProfile) -> dict:
    # Revalidate even when instances have been copied; no trusted caller metrics.
    doc = ReadbackProfile(profile.content).document
    _validate_profile_constants(doc)
    if inputs.candidate_name not in doc["candidates"]:
        raise ValueError("CANDIDATE_NAME_INVALID")
    source, source_inventory = _parse_selected(inputs.source, inputs.geometry_id)
    candidate, candidate_inventory = _parse_selected(inputs.candidate, inputs.geometry_id)
    body = geometry.parse_glb_surface(_verified(inputs.body, "bcb_body_glb"))
    active = derive_original_active_ids(source.positions, body)
    cohort = derive_fixed_coverage_contract(source.positions, source.faces, body)
    _canonical_bindings(inputs, doc, source, body, active, cohort)
    roi = geometry.derive_minimal_roi(source.positions, source.faces, active)
    historical = doc["candidates"][inputs.candidate_name]
    invariants = {
        "face_indices_equal": np.array_equal(source.faces, candidate.faces),
        "position_shape_equal": source.positions.shape == candidate.positions.shape,
        "whole_document_except_selected_position_bytes_equal": source.non_position_sha256 == candidate.non_position_sha256,
        "source_non_position_sha256": source.non_position_sha256,
        "candidate_non_position_sha256": candidate.non_position_sha256,
        "source_document_inventory": source_inventory,
        "candidate_document_inventory": candidate_inventory,
        "scope": doc["preservation_scope"],
    }
    report = {
        "schema": "clothmorph.padded-retrospective-result", "schema_version": 1,
        "profile_kind": doc["profile_kind"], "profile_sha256": PROFILE_SHA256,
        "evidence_scope": inputs.evidence_scope,
        "candidate_name": inputs.candidate_name,
        "identities": {
            "source_sha256": _sha(inputs.source.content), "body_sha256": _sha(inputs.body.content),
            "candidate_sha256": _sha(inputs.candidate.content), "geometry_id": inputs.geometry_id,
            "source_faces_le_i8_sha256": source.face_indices_sha256,
            "body_positions_le_f8_sha256": _sha(np.asarray(body.positions, dtype="<f8").tobytes()),
            "body_faces_le_i8_sha256": _sha(np.asarray(body.faces, dtype="<i8").tobytes()),
            "body_normals_le_f8_sha256": _sha(np.asarray(body.vertex_normals, dtype="<f8").tobytes()),
            "original_active_ids": _ids(active), "active_ids_le_i8_sha256": _ids_hash(active),
            "fixed_cohort_body_vertex_ids": _ids(cohort.body_vertex_ids),
            "fixed_cohort_ids_le_i8_sha256": _ids_hash(cohort.body_vertex_ids),
            "manifest_chains": {
                name: [{"sha256": link.expected_sha256, "member_path": link.member_path}
                       for link in getattr(inputs, name).provenance]
                for name in ("source", "body", "candidate")
            },
        },
        "construction": {
            **{key: value for key, value in historical.items() if key != "sha256"},
            "historical_reference_sha256": historical["sha256"] if inputs.evidence_scope == "CANONICAL_PADDED" else None,
            "gates_governed_by_this_profile": False, "generator_rerun": False,
            "valid_target_exhausted_architecture": False,
            "historical_gate_crosswalk": doc["historical_gate_crosswalk"],
            "historical_selection_and_search_coverage": "NOT_REASSESSED_BY_FROZEN_READBACK",
        },
        "source_invariants": invariants,
        "measurements": {}, "extrema": {}, "current_necessary_gate_failures": [],
        "current_roi_comparison": {
            "historical_domain_applicability": "NOT_ESTABLISHED",
            "scope": "CURRENT_CONNECTED_ROI_COMPARISON_ONLY",
            "movable_ids": _ids(roi.movable_ids), "boundary_ids": _ids(roi.boundary_ids),
        },
        "unavailable_checks": doc["unavailable_checks"],
        "geometry_policy_eligibility": "UNASSESSED_OR_BLOCKED", "event_ready": False,
        "blockers": [
            "SAME_PREDECLARED_GATES_NOT_ESTABLISHED", "PREDECLARED_SILHOUETTE_UNASSESSED",
            "PREDECLARED_NONTRIVIALITY_UNASSESSED", "ATOMIC_COMPONENT_MEMBERSHIP_UNRESOLVED",
            "PANTS_COMPONENT_UNASSESSED", "COMPLETE_ROUTE_SKIN_LOD_MATERIAL_CONTRACT_UNASSESSED",
            "HISTORICAL_GENERATOR_REPEATABILITY_UNASSESSED", "CANONICAL_PROFILE_RECORD_MODE_UNRESOLVED",
            "PROTECTED_REGISTRY_SHARED_CONSUMERS_UNRESOLVED",
        ],
        "proposals": {
            "reason": {"value": "NO_SAFE_GEOMETRY_AVAILABLE", "approved": False},
            "reopening": {"value": "Requires separately reviewed architecture and policy decision; no claim that manual remesh is the only admissible method.", "approved": False},
        },
    }
    if inputs.evidence_scope == "SYNTHETIC_FIXTURE":
        report["blockers"].append("SYNTHETIC_EVIDENCE_NOT_CANONICAL")
        # Synthetic receipts exercise measurement behavior, not historical facts.
        report["construction"]["historical_evidence_scope"] = "FIXTURE_LABEL_ONLY_NO_REAL_CANDIDATE_CLAIM"
    if inputs.candidate_name == "local":
        report["blockers"].append("HISTORICAL_LOCAL_TARGET_NOT_CERTIFIED")
    if not invariants["whole_document_except_selected_position_bytes_equal"]:
        report["current_necessary_gate_failures"].append("NON_POSITION_SEMANTICS_MISMATCH")
    if not invariants["face_indices_equal"] or not invariants["position_shape_equal"]:
        report["blockers"].append("CANDIDATE_TOPOLOGY_OR_SHAPE_CHANGED")
        report["unavailable_checks"]["body_measurements"] = "BLOCKED_CHANGED_TOPOLOGY_OR_SHAPE"
        return report
    measurements, extrema = _topology_measurements(source, candidate)
    measurements.update(_clearance_measurements(candidate.positions, body, active, "active"))
    moved = np.flatnonzero(np.any(candidate.positions != source.positions, axis=1))
    moved_connectors = tuple(sorted(set(_ids(moved)) & set(roi.movable_ids) - set(active)))
    connectors = _clearance_measurements(candidate.positions, body, moved_connectors, "moved_roi")
    closest = exact_closest_points(cohort.contract.points, candidate.positions, source.faces)
    projection = np.einsum("ij,ij->i", closest.closest_points - cohort.contract.points, cohort.contract.normals)
    lost = (projection <= 0) | (closest.distances > cohort.contract.maximum_distance)
    measurements["fixed_cohort_coverage_loss"] = _measurement(
        np.asarray(cohort.body_vertex_ids)[lost], "retained_body_vertex_index")
    # Verify ID expansion has exactly the existing production count semantics.
    if measurements["fixed_cohort_coverage_loss"]["count"] != solver._coverage_loss(
            candidate.positions, source.faces, cohort.contract):
        raise ValueError("COVERAGE_FAILURE_ID_COUNT_MISMATCH")
    report["measurements"], report["extrema"] = measurements, extrema
    report["current_necessary_gate_failures"].extend(
        code for name, code in _FAILURES.items() if measurements[name]["count"])
    report["current_roi_comparison"].update({
        "fixed_vertex_moves": _measurement(sorted(set(_ids(moved)) - set(roi.movable_ids)), "selected_source_vertex_index"),
        "moved_vertex_ids": _ids(moved),
        "moved_position_deltas": [
            {"vertex_id": int(index), "delta_xyz": (candidate.positions[index] - source.positions[index]).tolist()}
            for index in moved
        ],
        "moved_connector_measurements": connectors,
        "not_a_historical_domain_violation": True,
    })
    report["serialization_observation"] = {
        "existing_current_decimals": solver.SERIALIZATION_DECIMALS,
        "candidate_positions_exactly_six_decimal_values": bool(np.array_equal(
            candidate.positions, np.round(candidate.positions, solver.SERIALIZATION_DECIMALS))),
        "candidate_rewritten": False,
    }
    if not report["serialization_observation"]["candidate_positions_exactly_six_decimal_values"]:
        report["blockers"].append("CURRENT_SERIALIZATION_PRECISION_NOT_MET")
    return report


def evaluate_frozen(inputs: ReadbackInputs, profile: ReadbackProfile | None = None) -> dict:
    """Parse and evaluate the same verified bytes twice, without any solver call."""
    profile = profile or load_profile()
    first = _evaluate_once(inputs, profile)
    second = _evaluate_once(inputs, profile)
    serialized = json.dumps(first, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if serialized != json.dumps(second, sort_keys=True, separators=(",", ":"), allow_nan=False).encode():
        raise ValueError("FROZEN_READBACK_NONDETERMINISTIC")
    first["readback"] = {
        "same_frozen_bytes_repeated_equal": True,
        "measurement_report_sha256": _sha(serialized),
        "generator_rerun_performed": False, "generator_determinism": "UNASSESSED",
        "scope": "REPEATED_PARSE_AND_MEASUREMENT_OF_RETAINED_BYTES_ONLY",
    }
    return first
