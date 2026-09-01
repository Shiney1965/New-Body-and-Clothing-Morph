"""Fail-closed, fixture-safe adapters for release-ledger evidence inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Callable

from .configuration import VerifiedInput
from .models import CanonicalIdentityFields, Observation


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
        records = value.get("records")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, Mapping)]
        return [value]
    if isinstance(value, list):
        return [record for record in value if isinstance(record, Mapping)]
    raise ValueError("EVIDENCE_RECORDS_INVALID")


def _text(value: object, unknown: str) -> str:
    return value if isinstance(value, str) and value else unknown


def _text_sequence(value: object, unknown: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        normalized = tuple(item for item in value if isinstance(item, str) and item)
        if normalized:
            return normalized
    return unknown


def _identity_fields(record: Mapping[str, Any]) -> CanonicalIdentityFields:
    identity = record.get("identity")
    source = identity if isinstance(identity, Mapping) else record
    body_tuple = _text_sequence(source.get("body_tuple"), _UNKNOWN_IDENTITY["body_tuple"])
    return CanonicalIdentityFields(
        source_module_uuid=_text(source.get("source_module_uuid"), _UNKNOWN_IDENTITY["source_module_uuid"]),
        source_profile_digest=_text(source.get("source_profile_digest"), _UNKNOWN_IDENTITY["source_profile_digest"]),
        creation_path_kind=_text(source.get("creation_path_kind"), _UNKNOWN_IDENTITY["creation_path_kind"]),
        root_template_uuid=_text(source.get("root_template_uuid"), _UNKNOWN_IDENTITY["root_template_uuid"]),
        stats_entry=_text(source.get("stats_entry"), _UNKNOWN_IDENTITY["stats_entry"]),
        inheritance_digest=_text(source.get("inheritance_digest"), _UNKNOWN_IDENTITY["inheritance_digest"]),
        effective_slot=_text(source.get("effective_slot"), _UNKNOWN_IDENTITY["effective_slot"]),
        body_tuple=body_tuple,
        ordered_source_vrs=_text_sequence(source.get("ordered_source_vrs"), _UNKNOWN_IDENTITY["ordered_source_vrs"]),
        component_contract_digest=_text(source.get("component_contract_digest"), _UNKNOWN_IDENTITY["component_contract_digest"]),
    )


def _blockers(*codes: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(code for code in codes if code))


def _observation(
    record: Mapping[str, Any],
    verified_input: VerifiedInput,
    *,
    index: int,
    kind: str,
    authority: str,
    evidence_status: str,
    disposition: str,
    release_blocking: bool,
    blocker_codes: tuple[str, ...] = (),
    protected_relations: Mapping[str, Any] | None = None,
    classification: Mapping[str, Any] | None = None,
    retain_raw_evidence: bool = False,
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
    if retain_raw_evidence:
        payload["raw_evidence"] = deepcopy(record)
    return Observation(
        observation_id=_text(record.get("observation_id") or record.get("identity"), f"{verified_input.input_id}:{index}"),
        observation_kind=kind,
        identity_fields=identity_fields,
        source_reference=str(verified_input.path),
        evidence_files=tuple(evidence_pointers),
        payload=payload,
        blocker_codes=blocker_codes,
    )


def _protected_relations(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "registry_ids": list(_text_sequence(record.get("registry_ids"), ("UNKNOWN_PROTECTED_REGISTRY",))),
        "route_fingerprint": _text(record.get("route_fingerprint"), "UNKNOWN_ROUTE_FINGERPRINT"),
        "protected_consumers": list(_text_sequence(record.get("protected_consumers"), ("UNKNOWN_PROTECTED_CONSUMER",))),
        "shared_assets": list(_text_sequence(record.get("shared_assets"), ("UNKNOWN_SHARED_ASSET",))),
        "forbidden_targets": list(_text_sequence(record.get("forbidden_targets"), ("UNKNOWN_FORBIDDEN_TARGET",))),
    }


def _adapt_one_protected(
    record: Mapping[str, Any], verified_input: VerifiedInput, *, index: int
) -> Observation:
    """Normalize one protected record without allowing status promotion."""
    status = record.get("status")
    if status not in _PROTECTED_STATUSES:
        return _observation(
            record, verified_input, index=index, kind="PROTECTED_CONTROL", authority="IMMUTABLE_V1",
            evidence_status="PROTECTED_STATUS_UNRESOLVED", disposition="BLOCKED_WITH_CAUSE",
            release_blocking=True, blocker_codes=("PROTECTED_STATUS_UNRESOLVED",),
            protected_relations=_protected_relations(record), retain_raw_evidence=True,
        )
    disposition, evidence_status, release_blocking = _PROTECTED_STATUSES[status]
    blockers = ("GAMEPLAY_UNASSESSED_PACKAGE_ONLY",) if release_blocking else ()
    return _observation(
        record, verified_input, index=index, kind="PROTECTED_CONTROL", authority="IMMUTABLE_V1",
        evidence_status=evidence_status, disposition=disposition, release_blocking=release_blocking,
        blocker_codes=blockers, protected_relations=_protected_relations(record), retain_raw_evidence=True,
    )


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
        ))
    return observations


def adapt_true_underwear(records: object, verified_input: VerifiedInput) -> list[Observation]:
    return [
        _observation(
            record, verified_input, index=index, kind="TRUE_UNDERWEAR_RECORD", authority="WORKSTREAM_EVIDENCE",
            evidence_status="ROUTE_UNASSESSED", disposition="BLOCKED_WITH_CAUSE", release_blocking=True,
            blocker_codes=("TARGET_ROUTE_UNRESOLVED", "GAMEPLAY_UNASSESSED"),
            retain_raw_evidence=bool(record.get("audit_traceability")),
        )
        for index, record in enumerate(_records(records))
    ]


def _section_9_contract_complete(record: Mapping[str, Any]) -> bool:
    contract = record.get("section_9_contract")
    return isinstance(contract, Mapping) and _SECTION_9_FAMILIES <= set(contract)


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
        ))
    return observations


def adapt_permission_manifest(records: object, verified_input: VerifiedInput) -> list[Observation]:
    observations: list[Observation] = []
    for index, manifest in enumerate(_records(records)):
        scopes = _text_sequence(manifest.get("scope_resolved"), ())
        if not scopes:
            scopes = ("UNKNOWN_PERMISSION_SCOPE",)
        for scope_index, mesh_name in enumerate(scopes):
            raw_record = dict(manifest)
            raw_record["scope_mesh"] = mesh_name
            observations.append(_observation(
                raw_record, verified_input, index=index + scope_index, kind="PERMISSION_SCOPE_MESH",
                authority="PERMISSION_EVIDENCE", evidence_status="PERMISSION_SCOPE_RECORDED",
                disposition="DEFERRED_WITH_CAUSE", release_blocking=True,
                blocker_codes=("ITEM_CONTRACT_UNRESOLVED", "CREATION_PATH_UNRESOLVED", "SOURCE_VR_UNRESOLVED"),
                classification={"effective_slot": "AMBIGUOUS_SLOT"}, retain_raw_evidence=True,
            ))
    return observations


def adapt_package_evidence(records: object, verified_input: VerifiedInput) -> list[Observation]:
    return [
        _observation(
            record, verified_input, index=index, kind="PACKAGE_EVIDENCE", authority="PACKAGE_EVIDENCE",
            evidence_status="GAMEPLAY_UNASSESSED_PACKAGE_ONLY", disposition="PACKAGE_READY_GAMEPLAY_UNASSESSED",
            release_blocking=True, blocker_codes=("GAMEPLAY_UNASSESSED_PACKAGE_ONLY",),
            retain_raw_evidence=True,
        )
        for index, record in enumerate(_records(records))
    ]


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
    """Read a previously hash-verified JSON input and route it by bounded kind."""
    if verified_input.actual_sha256 != verified_input.expected_sha256:
        raise ValueError(f"EVIDENCE_INPUT_NOT_VERIFIED:{verified_input.input_id}")
    try:
        records = json.loads(Path(verified_input.path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"EVIDENCE_JSON_INVALID:{verified_input.input_id}") from error
    return _adapter_for(verified_input)(records, verified_input)
