"""Fail-closed, fixture-safe adapters for release-ledger evidence inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .configuration import VerifiedInput
from .identity import canonical_json, sha256_text
from .inventory import is_claim_authority
from .models import CanonicalIdentityFields, Observation
from .validation import validate_record


_UNKNOWN_IDENTITY = {
    "source_module_uuid": "UNKNOWN_SOURCE_MODULE_UUID",
    "source_profile_digest": "UNKNOWN_SOURCE_PROFILE_DIGEST",
    "creation_path_kind": "UNKNOWN_CREATION_PATH",
    "root_template_uuid": "UNKNOWN_ROOT_TEMPLATE_UUID",
    "stats_entry": "UNKNOWN_STATS_ENTRY",
    "inheritance_digest": "UNKNOWN_INHERITANCE_DIGEST",
    "effective_slot": "AMBIGUOUS_SLOT",
    "body_tuple": ("UNKNOWN_RACE", "UNKNOWN_SEX", "UNKNOWN_BODY_TYPE", "UNKNOWN_BODY_SHAPE", "UNKNOWN_EQUIPMENT_RACE"),
    "ordered_source_vrs": ("UNKNOWN_SOURCE_VR",),
    "component_contract_digest": "UNKNOWN_COMPONENT_CONTRACT_DIGEST",
}

_COVERAGE_DISPOSITIONS = {
    "READY FOR OFFLINE CORRECTION": "READY_FOR_OFFLINE_CORRECTION",
    "OFFLINE CANDIDATE PASS": "OFFLINE_CANDIDATE_PASS",
    "PACKAGE READY / GAMEPLAY UNASSESSED": "PACKAGE_READY_GAMEPLAY_UNASSESSED",
    "CLASS GAMEPLAY ACCEPTED": "CLASS_GAMEPLAY_ACCEPTED",
    "ITEM GAMEPLAY ACCEPTED": "ITEM_GAMEPLAY_ACCEPTED",
    "SHIPPED NATIVE PASSTHROUGH": "SHIPPED_NATIVE_PASSTHROUGH",
    "SHIPPED REFIT": "SHIPPED_REFIT",
    "OUT OF SCOPE WITH PROOF": "OUT_OF_SCOPE_WITH_PROOF",
    "BLOCKED WITH CAUSE": "BLOCKED_WITH_CAUSE",
    "DEFERRED WITH CAUSE": "DEFERRED_WITH_CAUSE",
}

_PROTECTED_STATUSES = {
    "GAMEPLAY_PASS": ("ACCEPTED_PROTECTED", "GAMEPLAY_ACCEPTED", False),
    "USER_ACCEPTED_RESIDUAL": ("ACCEPTED_PROTECTED", "USER_ACCEPTED_RESIDUAL", False),
    "PROTECTED_SOURCE_NATIVE": ("SOURCE_NATIVE_PROTECTED", "SOURCE_NATIVE", False),
    "PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY": (
        "PACKAGE_ONLY_PROTECTED", "GAMEPLAY_UNASSESSED_PACKAGE_ONLY", True,
    ),
}

_SECTION_9_FAMILIES = {
    "source_module", "permission", "creation_path", "classification", "body_tuple",
    "source_route", "mode_routes", "protected_relations", "transformation", "gates",
}


def _records(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        container_key = next(
            (key for key in ("records", "entries", "files", "audits", "items") if key in value),
            None,
        )
        if container_key is None:
            return [value]
        records = value[container_key]
        if not isinstance(records, list):
            raise ValueError("EVIDENCE_RECORDS_NOT_LIST")
        value = records
    if isinstance(value, list):
        normalized: list[Mapping[str, Any]] = []
        for index, record in enumerate(value):
            if not isinstance(record, Mapping):
                raise ValueError(f"EVIDENCE_RECORD_INVALID:{index}")
            normalized.append(record)
        return normalized
    raise ValueError("EVIDENCE_RECORDS_INVALID")


def _text(value: object, unknown: str) -> str:
    return value if isinstance(value, str) and value else unknown


def _text_sequence(value: object, unknown: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        normalized = tuple(item for item in value if isinstance(item, str) and item)
        if normalized:
            return normalized
    return unknown


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _digest_value(value: object, unknown: str) -> str:
    if value in (None, "", [], {}, "UNASSESSED", "UNKNOWN"):
        return unknown
    if isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value):
        return value.upper()
    return sha256_text(canonical_json(value))


def _body_tuple(source: Mapping[str, Any]) -> tuple[str, ...]:
    explicit = _text_sequence(source.get("body_tuple"), ())
    if explicit:
        return explicit
    family = _text(source.get("body_family"), "UNKNOWN_EQUIPMENT_RACE")
    sex = "Female" if family.endswith("_F") else "UNKNOWN_SEX"
    return ("UNKNOWN_RACE", sex, "UNKNOWN_BODY_TYPE", "UNKNOWN_BODY_SHAPE", family)


def _source_vrs(source: Mapping[str, Any]) -> tuple[str, ...]:
    explicit = _text_sequence(source.get("ordered_source_vrs"), ())
    if explicit:
        return explicit
    direct = source.get("source_visual_resource_uuid") or source.get("source_vr")
    if isinstance(direct, str) and direct:
        return (direct,)
    route_contracts = source.get("route_contracts")
    if isinstance(route_contracts, list) and len(route_contracts) == 1:
        route = _mapping(route_contracts[0])
        routed = _text_sequence(route.get("ordered_visual_resource_uuids"), ())
        if routed:
            return routed
    route = _mapping(source.get("route"))
    routed = route.get("source_visual_resource")
    if isinstance(routed, str) and routed:
        return (routed,)
    return _UNKNOWN_IDENTITY["ordered_source_vrs"]


def _identity_fields(record: Mapping[str, Any]) -> CanonicalIdentityFields:
    identity = record.get("identity")
    source = identity if isinstance(identity, Mapping) else record
    source_module = _mapping(source.get("source_module"))
    item_contract = _mapping(source.get("item_contract"))
    inheritance = source.get("inheritance_chain") or source.get("inheritance") or source.get("named_stats_using")
    component_contract = source.get("component_contract") or source.get("component_topology_contract")
    source_profile = (
        source.get("source_profile_digest")
        or source_module.get("version_identity")
        or source.get("source_mod_version")
    )
    if source_profile is None and source_module:
        source_profile = source_module
    return CanonicalIdentityFields(
        source_module_uuid=_text(
            source.get("source_module_uuid") or source.get("module_uuid") or source.get("source_mod_uuid") or source_module.get("uuid"),
            _UNKNOWN_IDENTITY["source_module_uuid"],
        ),
        source_profile_digest=_digest_value(source_profile, _UNKNOWN_IDENTITY["source_profile_digest"]),
        creation_path_kind=_text(
            source.get("creation_path_kind") or source.get("creation_path") or ("root_template" if source.get("root_template_uuid") or source.get("root_uuid") or item_contract.get("root_template") else None),
            _UNKNOWN_IDENTITY["creation_path_kind"],
        ),
        root_template_uuid=_text(
            source.get("root_template_uuid") or source.get("root_uuid") or source.get("item_uuid") or item_contract.get("root_template"),
            _UNKNOWN_IDENTITY["root_template_uuid"],
        ),
        stats_entry=_text(
            source.get("stats_entry") or source.get("named_stats_entry") or item_contract.get("stats"),
            _UNKNOWN_IDENTITY["stats_entry"],
        ),
        inheritance_digest=_digest_value(
            source.get("inheritance_digest") or inheritance,
            _UNKNOWN_IDENTITY["inheritance_digest"],
        ),
        effective_slot=_text(
            source.get("effective_slot") or source.get("equipment_slot") or item_contract.get("slot"),
            _UNKNOWN_IDENTITY["effective_slot"],
        ),
        body_tuple=_body_tuple(source),
        ordered_source_vrs=_source_vrs(source),
        component_contract_digest=_digest_value(
            source.get("component_contract_digest") or component_contract,
            _UNKNOWN_IDENTITY["component_contract_digest"],
        ),
    )


def _blockers(*codes: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(code for code in codes if code))


def _observation(
    record: Mapping[str, Any],
    verified_input: VerifiedInput,
    *,
    index: int | str,
    kind: str,
    authority: str,
    evidence_status: str,
    disposition: str,
    release_blocking: bool,
    blocker_codes: tuple[str, ...] = (),
    protected_relations: Mapping[str, Any] | None = None,
    classification: Mapping[str, Any] | None = None,
    retain_raw_evidence: bool = False,
    normalized_payload: Mapping[str, Any] | None = None,
) -> Observation:
    identity_fields = _identity_fields(record)
    evidence_pointers = [str(verified_input.path)]
    pointer = record.get("evidence_pointer")
    if isinstance(pointer, str) and pointer:
        evidence_pointers.append(pointer)
    payload: dict[str, Any] = {
        "input_id": verified_input.input_id,
        "input_sha256": verified_input.actual_sha256,
        "authority": authority,
        "evidence_status": evidence_status,
        "disposition": disposition,
        "release_blocking": release_blocking,
        "protected_relations": dict(protected_relations or {}),
        "classification": dict(classification or {"effective_slot": identity_fields.effective_slot}),
        "evidence_pointers": tuple(evidence_pointers),
    }
    payload.update(dict(normalized_payload or {}))
    if retain_raw_evidence:
        payload["raw_evidence"] = deepcopy(record)
    return Observation(
        observation_id=_text(
            record.get("observation_id") or record.get("identity") or record.get("id") or record.get("item_uuid"),
            f"{verified_input.input_id}:{index}",
        ),
        observation_kind=kind,
        identity_fields=identity_fields,
        source_reference=str(verified_input.path),
        evidence_files=tuple(evidence_pointers),
        payload=payload,
        blocker_codes=blocker_codes,
    )


def _protected_relations(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "registry_ids": list(_text_sequence(record.get("registry_ids") or ([record["id"]] if isinstance(record.get("id"), str) else None), ("UNKNOWN_PROTECTED_REGISTRY",))),
        "route_fingerprint": _text(record.get("route_fingerprint") or record.get("route_fingerprint_sha256"), "UNKNOWN_ROUTE_FINGERPRINT"),
        "protected_consumers": list(_text_sequence(record.get("protected_consumers") or record.get("shared_consumers"), ("UNKNOWN_PROTECTED_CONSUMER",))),
        "shared_assets": list(_text_sequence(record.get("shared_assets"), ("UNKNOWN_SHARED_ASSET",))),
        "forbidden_targets": list(_text_sequence(record.get("forbidden_targets"), ("UNKNOWN_FORBIDDEN_TARGET",))),
    }


def _adapt_one_protected(
    record: Mapping[str, Any], verified_input: VerifiedInput, *, index: int
) -> Observation:
    """Normalize one protected record without allowing status promotion."""
    status = record.get("status") or record.get("acceptance_status")
    if status not in _PROTECTED_STATUSES:
        return _observation(
            record, verified_input, index=index, kind="PROTECTED_CONTROL", authority="IMMUTABLE_V1",
            evidence_status="PROTECTED_STATUS_UNRESOLVED", disposition="BLOCKED_WITH_CAUSE",
            release_blocking=True, blocker_codes=("PROTECTED_STATUS_UNRESOLVED",),
            protected_relations=_protected_relations(record), retain_raw_evidence=True,
        )
    disposition, evidence_status, release_blocking = _PROTECTED_STATUSES[status]
    blockers = ("GAMEPLAY_UNASSESSED_PACKAGE_ONLY",) if release_blocking else ()
    route = _mapping(record.get("route"))
    protected_file = _mapping(record.get("protected_file"))
    mode = str(route.get("mode", "")).lower()
    mode_routes = {}
    if mode in {"vanilla", "sbbf", "bcb", "external"}:
        mode_routes[mode] = {}
        if isinstance(route.get("target_visual_resource"), str) and route["target_visual_resource"]:
            mode_routes[mode]["target_vrs"] = [route["target_visual_resource"]]
        if isinstance(route.get("target_path"), str) and route["target_path"]:
            mode_routes[mode]["target_paths"] = [route["target_path"]]
        if isinstance(protected_file.get("sha256"), str) and protected_file["sha256"]:
            mode_routes[mode]["payload_hashes"] = [protected_file["sha256"]]
    normalized_payload = {
        "source_module": dict(_mapping(record.get("source_module"))),
        "source_route": {
            "ordered_vrs": list(_source_vrs(record)),
            "ordered_paths": [route["source_path"]] if isinstance(route.get("source_path"), str) and route["source_path"] else ["UNKNOWN_SOURCE_PATH"],
            "ordered_file_hashes": ["UNKNOWN_SOURCE_FILE_HASH"],
        },
        "mode_routes": mode_routes,
        "payload_hash": protected_file.get("sha256", "UNKNOWN_PAYLOAD_HASH"),
        "next_admissible_action": _text(record.get("permitted_future_action"), "Obtain bounded evidence."),
        "acceptance_event_id": _text(record.get("id"), "UNKNOWN_ACCEPTANCE_EVENT"),
    }
    return _observation(
        record, verified_input, index=index, kind="PROTECTED_CONTROL", authority="IMMUTABLE_V1",
        evidence_status=evidence_status, disposition=disposition, release_blocking=release_blocking,
        blocker_codes=blockers, protected_relations=_protected_relations(record), retain_raw_evidence=True,
        normalized_payload=normalized_payload,
    )


def _normalized_workstream_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    fields = _identity_fields(record)
    source_module = dict(_mapping(record.get("source_module")))
    if not source_module and isinstance(record.get("module_uuid"), str):
        source_module = {
            "uuid": record["module_uuid"],
            "folder": record.get("module_folder", "UNKNOWN_SOURCE_FOLDER"),
            "name": record.get("module_name", "UNKNOWN_SOURCE_NAME"),
            "version64": record.get("version64", "UNKNOWN_SOURCE_VERSION"),
        }
    source_path = record.get("source_visual_resource_path") or record.get("source_visual_path") or record.get("source_file")
    source_route = {
        "ordered_vrs": list(fields.ordered_source_vrs),
        "ordered_paths": [source_path] if isinstance(source_path, str) and source_path else ["UNKNOWN_SOURCE_PATH"],
        "ordered_file_hashes": ["UNKNOWN_SOURCE_FILE_HASH"],
        "component_contract_digest": fields.component_contract_digest,
    }
    mode_routes: dict[str, dict[str, list[str]]] = {}
    routes = _mapping(record.get("routes"))
    for raw_mode, raw_route in routes.items():
        mode = str(raw_mode).lower()
        if mode not in {"vanilla", "sbbf", "bcb", "external"}:
            continue
        route = _mapping(raw_route)
        mode_routes[mode] = {}
        if isinstance(route.get("visual_resource_uuid"), str) and route["visual_resource_uuid"]:
            mode_routes[mode]["target_vrs"] = [route["visual_resource_uuid"]]
        if isinstance(route.get("path"), str) and route["path"]:
            mode_routes[mode]["target_paths"] = [route["path"]]
        if isinstance(route.get("mesh_sha256"), str) and route["mesh_sha256"]:
            mode_routes[mode]["payload_hashes"] = [route["mesh_sha256"]]
    normalized = {
        "source_module": source_module,
        "creation_path": {
            "kind": fields.creation_path_kind,
            "root_uuid": fields.root_template_uuid,
            "stats_entry": fields.stats_entry,
            "inheritance_chain": list(record.get("inheritance_chain") or record.get("inheritance") or ["UNKNOWN_INHERITANCE_NODE"]),
            "chain_digest": fields.inheritance_digest,
        },
        "classification": {
            "effective_slot": fields.effective_slot,
            "garment_family": record.get("garment_family") or record.get("root_name") or record.get("name") or "UNKNOWN_GARMENT_FAMILY",
        },
        "source_route": source_route,
        "mode_routes": mode_routes,
        "next_admissible_action": _text(record.get("next_action"), "Obtain bounded evidence."),
    }
    protected_relations = record.get("protected_relations")
    if isinstance(protected_relations, Mapping):
        normalized["protected_relations"] = dict(protected_relations)
    return normalized


def adapt_one_protected(record: Mapping[str, Any], verified_input: VerifiedInput) -> Observation:
    """Normalize one protected record without allowing status promotion."""
    return _adapt_one_protected(record, verified_input, index=0)


def adapt_protected_registry(records: object, verified_input: VerifiedInput) -> list[Observation]:
    return [
        _adapt_one_protected(record, verified_input, index=index)
        for index, record in enumerate(_records(records))
    ]


def adapt_protected_manifest(records: object, verified_input: VerifiedInput) -> list[Observation]:
    return [
        _adapt_one_protected(record, verified_input, index=index)
        for index, record in enumerate(_records(records))
    ]


def adapt_hash_manifest(records: object, verified_input: VerifiedInput) -> list[Observation]:
    """Retain immutable hash facts as protected observations, never acceptance events."""
    return [
        _observation(
            record, verified_input, index=index, kind="PROTECTED_HASH_MANIFEST",
            authority="IMMUTABLE_V1", evidence_status="HASH_MANIFEST_VERIFIED",
            disposition="DEFERRED_WITH_CAUSE", release_blocking=True,
            blocker_codes=("GAMEPLAY_UNASSESSED",), protected_relations=_protected_relations(record),
            retain_raw_evidence=True,
        )
        for index, record in enumerate(_records(records))
    ]


def adapt_coverage(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, record in enumerate(_records(records)):
        disposition = _COVERAGE_DISPOSITIONS.get(record.get("disposition"))
        if disposition is None:
            disposition, evidence_status, blocking, blockers = (
                "BLOCKED_WITH_CAUSE", "COVERAGE_DISPOSITION_UNRESOLVED", True,
                ("COVERAGE_DISPOSITION_UNRESOLVED",),
            )
        elif disposition == "PACKAGE_READY_GAMEPLAY_UNASSESSED":
            evidence_status, blocking, blockers = "GAMEPLAY_UNASSESSED_PACKAGE_ONLY", True, ("GAMEPLAY_UNASSESSED_PACKAGE_ONLY",)
        elif disposition in {"CLASS_GAMEPLAY_ACCEPTED", "ITEM_GAMEPLAY_ACCEPTED"}:
            evidence_status, blocking, blockers = "GAMEPLAY_ACCEPTED", False, ()
        elif disposition in {"SHIPPED_NATIVE_PASSTHROUGH", "SHIPPED_REFIT", "OUT_OF_SCOPE_WITH_PROOF"}:
            evidence_status, blocking, blockers = "EVIDENCE_RECORDED", False, ()
        else:
            evidence_status, blocking, blockers = "GAMEPLAY_UNASSESSED", True, ("GAMEPLAY_UNASSESSED",)
        observations.append(_observation(
            record, verified_input, index=index, kind="COVERAGE_RECORD", authority="WORKSTREAM_EVIDENCE",
            evidence_status=evidence_status, disposition=disposition, release_blocking=blocking,
            blocker_codes=blockers, retain_raw_evidence=bool(record.get("audit_traceability")),
            normalized_payload=_normalized_workstream_payload(record),
        ))
    return observations


def adapt_true_underwear(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, record in enumerate(_records(records)):
        if _section_9_contract_complete(record):
            disposition, status, blockers = (
                "READY_FOR_OFFLINE_CORRECTION", "GAMEPLAY_UNASSESSED", ("GAMEPLAY_UNASSESSED",)
            )
        else:
            disposition, status, blockers = (
                "BLOCKED_WITH_CAUSE", "ROUTE_UNASSESSED",
                ("TARGET_ROUTE_UNRESOLVED", "GAMEPLAY_UNASSESSED"),
            )
        observations.append(_observation(
            record, verified_input, index=index, kind="TRUE_UNDERWEAR_RECORD", authority="WORKSTREAM_EVIDENCE",
            evidence_status=status, disposition=disposition, release_blocking=True,
            blocker_codes=blockers, retain_raw_evidence=bool(record.get("audit_traceability")),
            normalized_payload=_normalized_workstream_payload(record),
        ))
    return observations


def _section_9_contract_complete(record: Mapping[str, Any]) -> bool:
    contract = record.get("section_9_contract")
    return isinstance(contract, dict) and _SECTION_9_FAMILIES <= set(contract) and not validate_record(contract)


def adapt_vanitybody(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, record in enumerate(_records(records)):
        ready_for_test = record.get("disposition") == "READY FOR TEST"
        if ready_for_test and not _section_9_contract_complete(record):
            disposition, status, blockers = "DEFERRED_WITH_CAUSE", "SECTION_9_CONTRACT_UNRESOLVED", ("SECTION_9_CONTRACT_UNRESOLVED",)
        elif ready_for_test:
            disposition, status, blockers = "READY_FOR_OFFLINE_CORRECTION", "GAMEPLAY_UNASSESSED", ("GAMEPLAY_UNASSESSED",)
        else:
            disposition, status, blockers = "DEFERRED_WITH_CAUSE", "VANITYBODY_EVIDENCE_UNASSESSED", ("VANITYBODY_EVIDENCE_UNASSESSED",)
        observations.append(_observation(
            record, verified_input, index=index, kind="VANITYBODY_RECORD", authority="WORKSTREAM_EVIDENCE",
            evidence_status=status, disposition=disposition, release_blocking=True, blocker_codes=blockers,
            retain_raw_evidence=bool(record.get("audit_traceability")),
            normalized_payload=_normalized_workstream_payload(record),
        ))
    return observations


def adapt_bcbscantily(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, record in enumerate(_records(records)):
        blockers: list[str] = []
        if not isinstance(record.get("source_visual_resource_uuid"), str) or not record["source_visual_resource_uuid"]:
            blockers.append("SOURCE_VR_UNRESOLVED")
        component = record.get("component_contract")
        if not isinstance(component, str) or component in {"", "UNASSESSED", "UNKNOWN"}:
            blockers.append("COMPONENT_CONTRACT_UNRESOLVED")
        if not blockers:
            blockers.append("GAMEPLAY_UNASSESSED")
        observations.append(_observation(
            record, verified_input, index=index, kind="BCBSCANTILY_RECORD", authority="WORKSTREAM_EVIDENCE",
            evidence_status="COMPONENT_OR_ROUTE_UNASSESSED", disposition="BLOCKED_WITH_CAUSE", release_blocking=True,
            blocker_codes=tuple(blockers), retain_raw_evidence=bool(record.get("audit_traceability")),
            normalized_payload=_normalized_workstream_payload(record),
        ))
    return observations


def adapt_permission_manifest(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, manifest in enumerate(_records(records)):
        scopes = _text_sequence(manifest.get("scope_resolved"), ())
        if not scopes:
            scopes = ("UNKNOWN_PERMISSION_SCOPE",)
        for scope_index, mesh_name in enumerate(scopes):
            observations.append(_observation(
                manifest, verified_input, index=f"{index}:{scope_index}", kind="PERMISSION_SCOPE_MESH",
                authority="PERMISSION_EVIDENCE", evidence_status="PERMISSION_SCOPE_RECORDED",
                disposition="DEFERRED_WITH_CAUSE", release_blocking=True,
                blocker_codes=("ITEM_CONTRACT_UNRESOLVED", "CREATION_PATH_UNRESOLVED", "SOURCE_VR_UNRESOLVED"),
                classification={"effective_slot": "AMBIGUOUS_SLOT", "scope_mesh": mesh_name}, retain_raw_evidence=True,
            ))
    return observations


def adapt_package_evidence(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, record in enumerate(_records(records)):
        candidate_sha = record.get("candidate_pak_sha256")
        package_sha = (
            candidate_sha.upper()
            if isinstance(candidate_sha, str)
            and len(candidate_sha) == 64
            and all(character in "0123456789abcdefABCDEF" for character in candidate_sha)
            else None
        )
        package_id = f"PACKAGE_SHA256:{package_sha}" if package_sha else "UNKNOWN_SHIPPED_PACKAGE"
        source_module: dict[str, Any] = {}
        if package_sha:
            source_module = {
                "name": _text(record.get("source_name"), "UNKNOWN_SOURCE_NAME"),
                "pak": package_id,
                "pak_sha256": package_sha,
                "uuid": _text(record.get("source_mod_uuid"), "UNKNOWN_SOURCE_MODULE_UUID"),
                "version64": _text(record.get("source_mod_version"), "UNKNOWN_SOURCE_VERSION"),
            }
        normalized_payload: dict[str, Any] = {
            "source_module": source_module,
            "shipped_package_id": package_id,
            "transformation": {
                "package_id": package_id,
                "candidate_pak_sha256": package_sha or "UNKNOWN_PAYLOAD_HASH",
                "live_registration_contract": _text(
                    record.get("live_registration_contract"), "GAMEPLAY_UNASSESSED"
                ),
            },
        }
        if package_sha:
            normalized_payload["payload_hash"] = package_sha
        observations.append(_observation(
            record, verified_input, index=index, kind="PACKAGE_EVIDENCE", authority="PACKAGE_EVIDENCE",
            evidence_status="GAMEPLAY_UNASSESSED_PACKAGE_ONLY", disposition="PACKAGE_READY_GAMEPLAY_UNASSESSED",
            release_blocking=True, blocker_codes=("GAMEPLAY_UNASSESSED_PACKAGE_ONLY",),
            retain_raw_evidence=True, normalized_payload=normalized_payload,
        ))
    return observations


def adapt_named_target(records: object, verified_input: VerifiedInput) -> list[Observation]:
    return [
        _observation(
            record, verified_input, index=index, kind="NAMED_TARGET_EVIDENCE", authority="NAMED_TARGET_EVIDENCE",
            evidence_status="IDENTITY_UNRESOLVED", disposition="DEFERRED_WITH_CAUSE", release_blocking=True,
            blocker_codes=("NAMED_TARGET_UNRESOLVED", "ITEM_CONTRACT_UNRESOLVED"),
            classification={"effective_slot": "AMBIGUOUS_SLOT"}, retain_raw_evidence=True,
        )
        for index, record in enumerate(_records(records))
    ]


def _adapter_for(verified_input: VerifiedInput) -> Callable[[object, VerifiedInput], list[Observation]]:
    key = verified_input.kind.upper()
    adapters: dict[str, Callable[[object, VerifiedInput], list[Observation]]] = {
        "PROTECTED_REGISTRY": adapt_protected_registry,
        "PROTECTED_MANIFEST": adapt_protected_manifest,
        "HASH_MANIFEST": adapt_hash_manifest,
        "COVERAGE": adapt_coverage,
        "TRUE_UNDERWEAR": adapt_true_underwear,
        "VANITYBODY": adapt_vanitybody,
        "BCBSCANTILY": adapt_bcbscantily,
        "PERMISSION": adapt_permission_manifest,
        "PACKAGE": adapt_package_evidence,
        "NAMED_TARGET": adapt_named_target,
    }
    if key in adapters:
        return adapters[key]
    input_id = verified_input.input_id.lower()
    if "protected_registry" in input_id:
        return adapt_protected_registry
    if "protected_hash_manifest" in input_id:
        return adapt_hash_manifest
    if "coverage" in input_id:
        return adapt_coverage
    if "underwear" in input_id:
        return adapt_true_underwear
    if "vanitybody" in input_id:
        return adapt_vanitybody
    if "bcbscantily" in input_id:
        return adapt_bcbscantily
    if "permission" in input_id:
        return adapt_permission_manifest
    if any(fragment in input_id for fragment in ("recluse", "package", "provider")):
        return adapt_package_evidence
    return adapt_named_target


def read_observations(verified_input: VerifiedInput) -> list[Observation]:
    """Read a previously hash-verified input and route it by bounded kind."""
    try:
        content = Path(verified_input.path).read_bytes()
    except OSError as error:
        raise ValueError(f"EVIDENCE_INPUT_UNREADABLE:{verified_input.input_id}") from error
    content_sha256 = hashlib.sha256(content).hexdigest().upper()
    if (
        len(content) != verified_input.bytes
        or content_sha256 != verified_input.expected_sha256
        or content_sha256 != verified_input.actual_sha256
    ):
        raise ValueError(f"EVIDENCE_INPUT_HASH_MISMATCH:{verified_input.input_id}")
    if (
        verified_input.kind.upper() == "SUPPORTING_EVIDENCE"
        or is_claim_authority(verified_input, None)
    ):
        return []
    if verified_input.kind.upper() == "NAMED_TARGET" and verified_input.path.suffix.lower() == ".md":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"EVIDENCE_TEXT_INVALID:{verified_input.input_id}") from error
        return adapt_named_target({
            "observation_id": verified_input.input_id,
            "evidence_pointer": str(verified_input.path),
            "document_sha256": verified_input.actual_sha256,
        }, verified_input)
    try:
        records = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"EVIDENCE_JSON_INVALID:{verified_input.input_id}") from error
    if is_claim_authority(verified_input, records):
        return []
    return _adapter_for(verified_input)(records, verified_input)
