"""Prospective common-gate / eligibility / event_ready adjudication.

This module defines forward-looking policy criteria where historical
same-predeclared-gate authority is missing. It never measures garments,
never attaches terminal exclusions, never invents ledger/event IDs, and
never rewrites historical construction gates.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).with_name("contracts") / "prospective_common_gate_v1.json"
POLICY_SHA256 = "B0B9474C1E712AB992DC45EC75CF64C8AACA8AA1AE5F15CCA6A6869162AA433F"

_COMMON_GATE_KEYS = (
    "nontriviality",
    "silhouette",
    "topology",
    "clearance",
    "coverage",
    "component",
    "material_skin_lod",
    "deterministic_readback",
)

_ELIGIBILITY_REQUIREMENTS = (
    "COMMON_GATES_PREDECLARED",
    "ARCHITECTURE_EXHAUSTION_UNDER_COMMON_GATES",
    "ATOMIC_COMPONENT_MEMBERSHIP_RESOLVED",
    "COMPLETE_ROUTE_SKIN_LOD_MATERIAL_CONTRACT_RESOLVED",
    "NO_RETROSPECTIVE_ONLY_SUBSTITUTION",
)

_EVENT_READY_REQUIREMENTS = (
    "GEOMETRY_POLICY_ELIGIBLE",
    "CANONICAL_SOURCE_PROFILE_RECORD_MODE_BOUND",
    "PROTECTED_REGISTRY_SHARED_CONSUMERS_PROVEN",
    "RECORD_IDENTITY_SOURCE_PROFILE_PRESENT",
    "INDEPENDENT_REVIEW_APPROVED",
    "PROPOSALS_APPROVED",
    "NO_AUTO_ATTACHED_TERMINAL_EXCLUSION",
)


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
class ProspectivePolicy:
    """Immutable LF-normalized policy bytes; detached JSON views cannot mutate it."""

    content: bytes

    def __post_init__(self) -> None:
        if type(self.content) is not bytes or _sha(self.content) != POLICY_SHA256:
            raise ValueError("POLICY_DIGEST_MISMATCH")

    @property
    def document(self) -> dict:
        return _json(self.content)


def load_policy() -> ProspectivePolicy:
    # Git may check a text contract out with CRLF. Semantic pin is LF bytes.
    return ProspectivePolicy(POLICY_PATH.read_bytes().replace(b"\r\n", b"\n"))


def _require_mapping(value: Any, code: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(code)
    return value


def _status(mapping: dict, key: str, default: str = "UNASSESSED") -> str:
    value = mapping.get(key, default)
    if not isinstance(value, str) or not value:
        raise ValueError(f"STATUS_INVALID:{key}")
    return value


def _as_bool(mapping: dict, key: str, default: bool = False) -> bool:
    value = mapping.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"BOOL_REQUIRED:{key}")
    return value


def _identifier_fields(evidence: dict) -> dict[str, Any]:
    fields = {
        "event_id": evidence.get("event_id"),
        "record_id": evidence.get("record_id"),
        "identity_sha256": evidence.get("identity_sha256"),
        "source_profile_id": evidence.get("source_profile_id"),
    }
    for name, value in fields.items():
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"INVENTED_OR_EMPTY_IDENTIFIER:{name}")
        if name == "identity_sha256" and (
            len(value) != 64 or any(ch not in "0123456789ABCDEF" for ch in value)
        ):
            raise ValueError("IDENTITY_SHA256_INVALID")
        if name in {"event_id", "record_id"} and value.startswith("INVENTED_"):
            raise ValueError(f"INVENTED_IDENTIFIER:{name}")
    return fields


def _common_gates_predeclared(evidence: dict, policy: dict) -> tuple[bool, list[str]]:
    declared = _require_mapping(
        evidence.get("common_gates_predeclared", {}), "COMMON_GATES_MAP_REQUIRED"
    )
    blockers: list[str] = []
    for key in _COMMON_GATE_KEYS:
        expected = policy["common_gates"][key]
        if key in {"nontriviality", "silhouette"}:
            status = _status(declared, key)
            if status != "PREDECLARED_NUMERICAL":
                blockers.append(f"PREDECLARED_{key.upper()}_UNASSESSED")
            continue
        if key == "component":
            status = _status(declared, key)
            if status != "RESOLVED":
                blockers.append("ATOMIC_COMPONENT_MEMBERSHIP_UNRESOLVED")
            continue
        if key == "material_skin_lod":
            status = _status(declared, key)
            if status != "RESOLVED":
                blockers.append("COMPLETE_ROUTE_SKIN_LOD_MATERIAL_CONTRACT_UNRESOLVED")
            continue
        if key == "deterministic_readback":
            status = _status(declared, key)
            if status not in {"PROVEN_REAL_RECONSTRUCTIONS", "PREDECLARED_AND_PROVEN"}:
                blockers.append("DETERMINISTIC_READBACK_UNASSESSED")
            continue
        # topology / clearance / coverage are structured gate objects
        supplied = declared.get(key)
        if not isinstance(supplied, dict):
            blockers.append(f"COMMON_GATE_{key.upper()}_NOT_PREDECLARED")
            continue
        for field, wanted in expected.items():
            if field in {"oracle", "note", "notes", "active_ids_authority"}:
                continue
            if supplied.get(field) != wanted:
                blockers.append(f"COMMON_GATE_{key.upper()}_MISMATCH")
                break
    return not blockers, blockers


def _architecture_exhaustion(
    evidence: dict, policy: dict
) -> tuple[bool, int, list[str], list[str]]:
    architectures = evidence.get("architectures", [])
    if not isinstance(architectures, list):
        raise ValueError("ARCHITECTURES_LIST_REQUIRED")
    qual_rules = policy["architecture_qualification"]["declared_architectures"]
    blockers: list[str] = []
    qualifying_names: list[str] = []
    seen_names: set[str] = set()
    for entry in architectures:
        item = _require_mapping(entry, "ARCHITECTURE_ENTRY_INVALID")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("ARCHITECTURE_NAME_REQUIRED")
        if name in seen_names:
            blockers.append("DUPLICATE_ARCHITECTURE_LABEL")
            continue
        seen_names.add(name)
        default = qual_rules.get(name, {}).get("default_qualifying_status", "UNKNOWN")
        status = _status(
            item, "qualifying_status", default if isinstance(default, str) else "UNKNOWN"
        )
        if status == "EXCLUDED_TARGET_NOT_CERTIFIED":
            blockers.append("HISTORICAL_LOCAL_TARGET_NOT_CERTIFIED")
            continue
        if status == "HISTORICAL_DIAGNOSTIC_ONLY":
            continue
        if status == "PARAMETER_RETUNE_OF_EXISTING":
            blockers.append("PARAMETER_TUNING_NOT_DISTINCT_ARCHITECTURE")
            continue
        if status not in {"QUALIFYING", "CANDIDATE_IF_SAME_COMMON_GATES"}:
            blockers.append(f"ARCHITECTURE_STATUS_UNQUALIFIED:{name}")
            continue
        if not _as_bool(item, "used_common_gates", False):
            blockers.append(f"ARCHITECTURE_GATES_NOT_COMMON:{name}")
            continue
        if not _as_bool(item, "gates_identical_to_policy", False):
            blockers.append(f"ARCHITECTURE_GATES_MISMATCH:{name}")
            continue
        if not _as_bool(item, "component_failures_recorded", False):
            blockers.append(f"ARCHITECTURE_COMPONENT_FAILURES_UNRECORDED:{name}")
            continue
        repeatability = _status(item, "generator_repeatability", "UNASSESSED")
        if repeatability in {"UNASSESSED", "SYNTHETIC_ONLY"}:
            blockers.append(f"ARCHITECTURE_GENERATOR_REPEATABILITY_UNASSESSED:{name}")
            continue
        result = _status(item, "result", "UNASSESSED")
        if result != "FAILED_ALL_CASES":
            blockers.append(f"ARCHITECTURE_NOT_EXHAUSTED:{name}")
            continue
        qualifying_names.append(name)

    minimum = int(policy["architecture_qualification"]["minimum_qualifying_architectures"])
    met = len(qualifying_names) >= minimum
    if not met:
        blockers.append("ARCHITECTURE_EXHAUSTION_COUNT_NOT_MET")
    return met, len(qualifying_names), qualifying_names, blockers


def _proposal_flags(packet: dict) -> tuple[dict, bool, bool]:
    raw = packet.get("proposals")
    if raw is None:
        proposals: dict = {}
    else:
        proposals = _require_mapping(raw, "PROPOSALS_OBJECT_REQUIRED")
    reason = proposals.get("reason")
    reopening = proposals.get("reopening")
    if reason is None:
        reason_obj = {
            "value": "NO_SAFE_GEOMETRY_AVAILABLE",
            "approved": False,
        }
    else:
        reason_obj = dict(_require_mapping(reason, "REASON_OBJECT_REQUIRED"))
        reason_obj.setdefault("value", "NO_SAFE_GEOMETRY_AVAILABLE")
        reason_obj["approved"] = _as_bool(reason_obj, "approved", False)
    if reopening is None:
        reopening_obj = {
            "value": (
                "Requires separately reviewed architecture under prospective "
                "common gates; manual remesh is not asserted as the only "
                "admissible method."
            ),
            "approved": False,
        }
    else:
        reopening_obj = dict(_require_mapping(reopening, "REOPENING_OBJECT_REQUIRED"))
        reopening_obj.setdefault(
            "value",
            (
                "Requires separately reviewed architecture under prospective "
                "common gates; manual remesh is not asserted as the only "
                "admissible method."
            ),
        )
        reopening_obj["approved"] = _as_bool(reopening_obj, "approved", False)
    return (
        {"reason": reason_obj, "reopening": reopening_obj},
        bool(reason_obj["approved"]),
        bool(reopening_obj["approved"]),
    )


def adjudicate(
    evidence: dict | None = None, policy: ProspectivePolicy | None = None
) -> dict:
    """Adjudicate prospective common-gate eligibility and event_ready.

    Pure policy consumer. Does not measure geometry, attach exclusions,
    mint PAK/GR2, or mutate protected registries.
    """
    loaded = ProspectivePolicy((policy or load_policy()).content)
    doc = loaded.document
    packet = _require_mapping(evidence or {}, "EVIDENCE_OBJECT_REQUIRED")
    identifiers = _identifier_fields(packet)

    blockers: list[str] = []
    gates_ok, gate_blockers = _common_gates_predeclared(packet, doc)
    blockers.extend(gate_blockers)

    exhausted, qualifying_count, qualifying_names, arch_blockers = _architecture_exhaustion(
        packet, doc
    )
    blockers.extend(arch_blockers)

    retrospective_only = _as_bool(packet, "retrospective_readback_only", False)
    if retrospective_only:
        blockers.append("RETROSPECTIVE_READBACK_ONLY_NOT_COMMON_GATE_PROOF")

    if _as_bool(packet, "measurement_wave_performed", False):
        raise ValueError("MEASUREMENT_WAVE_FORBIDDEN_IN_PROSPECTIVE_ADJUDICATION")
    if _as_bool(packet, "terminal_exclusion_attached", False):
        raise ValueError("AUTO_ATTACH_TERMINAL_EXCLUSION_FORBIDDEN")

    if any(
        identifiers[name] is not None
        for name in ("event_id", "record_id", "identity_sha256", "source_profile_id")
    ):
        if _status(packet, "identifier_authority", "UNRESOLVED") != "INDEPENDENTLY_BOUND":
            blockers.append("INVENTED_OR_UNBOUND_IDENTIFIERS")

    atomic = _status(packet, "atomic_component_membership", "UNRESOLVED")
    if atomic != "RESOLVED":
        blockers.append("ATOMIC_COMPONENT_MEMBERSHIP_UNRESOLVED")

    material = _status(packet, "complete_route_skin_lod_material_contract", "UNRESOLVED")
    if material != "RESOLVED":
        blockers.append("COMPLETE_ROUTE_SKIN_LOD_MATERIAL_CONTRACT_UNRESOLVED")

    ordered_blockers: list[str] = []
    for code in blockers:
        if code not in ordered_blockers:
            ordered_blockers.append(code)

    requirements_met = {
        "COMMON_GATES_PREDECLARED": gates_ok,
        "ARCHITECTURE_EXHAUSTION_UNDER_COMMON_GATES": exhausted,
        "ATOMIC_COMPONENT_MEMBERSHIP_RESOLVED": atomic == "RESOLVED",
        "COMPLETE_ROUTE_SKIN_LOD_MATERIAL_CONTRACT_RESOLVED": material == "RESOLVED",
        "NO_RETROSPECTIVE_ONLY_SUBSTITUTION": not retrospective_only,
    }
    eligibility = (
        "ELIGIBLE"
        if all(requirements_met[key] for key in _ELIGIBILITY_REQUIREMENTS)
        else "UNASSESSED_OR_BLOCKED"
    )
    if "INVENTED_OR_UNBOUND_IDENTIFIERS" in ordered_blockers:
        eligibility = "BLOCKED"

    canonical = _status(packet, "canonical_source_profile_record_mode", "UNRESOLVED")
    protected = _status(packet, "protected_registry_shared_consumers", "UNRESOLVED")
    review_approved = _as_bool(packet, "independent_review_approved", False)
    proposals, reason_approved, reopening_approved = _proposal_flags(packet)

    ids_present = all(
        identifiers[name] is not None
        for name in ("record_id", "identity_sha256", "source_profile_id")
    ) and _status(packet, "identifier_authority", "UNRESOLVED") == "INDEPENDENTLY_BOUND"

    event_requirements = {
        "GEOMETRY_POLICY_ELIGIBLE": eligibility == "ELIGIBLE",
        "CANONICAL_SOURCE_PROFILE_RECORD_MODE_BOUND": canonical == "BOUND",
        "PROTECTED_REGISTRY_SHARED_CONSUMERS_PROVEN": protected == "PROVEN",
        "RECORD_IDENTITY_SOURCE_PROFILE_PRESENT": ids_present,
        "INDEPENDENT_REVIEW_APPROVED": review_approved,
        "PROPOSALS_APPROVED": reason_approved and reopening_approved,
        "NO_AUTO_ATTACHED_TERMINAL_EXCLUSION": True,
    }

    if eligibility != "ELIGIBLE":
        ordered_blockers.append("GEOMETRY_POLICY_NOT_ELIGIBLE")
    if canonical != "BOUND":
        ordered_blockers.append("CANONICAL_PROFILE_RECORD_MODE_UNRESOLVED")
    if protected != "PROVEN":
        ordered_blockers.append("PROTECTED_REGISTRY_SHARED_CONSUMERS_UNRESOLVED")
    if not ids_present:
        ordered_blockers.append("RECORD_IDENTITY_SOURCE_PROFILE_ABSENT")
    if not review_approved:
        ordered_blockers.append("INDEPENDENT_REVIEW_NOT_APPROVED")
    if not (reason_approved and reopening_approved):
        ordered_blockers.append("PROPOSALS_NOT_APPROVED")

    final_blockers: list[str] = []
    for code in ordered_blockers:
        if code not in final_blockers:
            final_blockers.append(code)

    event_ready = all(event_requirements[key] for key in _EVENT_READY_REQUIREMENTS)

    report = {
        "schema": "clothmorph.padded-prospective-common-gate-result",
        "schema_version": 1,
        "policy_kind": doc["policy_kind"],
        "policy_sha256": POLICY_SHA256,
        "historical_predeclaration_rewritten": False,
        "garment_family": doc["garment_family"],
        "qualifying_architecture_count": qualifying_count,
        "qualifying_architectures": list(qualifying_names),
        "architecture_exhaustion": "MET" if exhausted else "NOT_MET",
        "eligibility_requirements": dict(requirements_met),
        "event_ready_requirements": dict(event_requirements),
        "geometry_policy_eligibility": eligibility,
        "event_ready": event_ready,
        "release_blocking": True,
        "terminal_exclusion_attached": False,
        "measurement_wave_performed": False,
        "blockers": final_blockers,
        "proposals": proposals,
        "identifiers": identifiers,
        "accepted_bounded_evidence_pins": doc["accepted_bounded_evidence_pins"],
    }
    return json.loads(json.dumps(report, allow_nan=False))
