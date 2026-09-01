"""Deterministic, fixture-only reconciliation of canonical release-ledger identities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .identity import build_identity
from .models import CanonicalIdentityFields, LedgerRecord, Observation
from .validation import validate_record

_AUTHORITY_PRECEDENCE = {"IMMUTABLE_V1": 0, "ITEM_GAMEPLAY": 1, "PACKAGE_EVIDENCE": 2, "STATIC_EVIDENCE": 2, "WORKSTREAM_EVIDENCE": 3, "DESIGN_EVIDENCE": 4, "CLASSIFICATION_EVIDENCE": 4, "NAMED_TARGET_EVIDENCE": 5, "OBSERVATION": 5}
_MODES = ("vanilla", "sbbf", "bcb", "external")
_GATES = ("topology", "component", "material", "skin", "clearance", "package", "fresh_extract", "route", "gameplay")


@dataclass(frozen=True)
class ReconciliationResult:
    records: tuple[LedgerRecord, ...]
    observation_to_record: Mapping[str, str]
    conflicts: tuple[str, ...]


def _precedence(item: Observation) -> tuple[int, str, str]:
    return (_AUTHORITY_PRECEDENCE.get(item.authority, 5), item.observation_id, item.source_reference)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _select_mapping(observations: list[Observation], key: str, route: bool = False) -> tuple[dict[str, Any], set[str]]:
    candidates = [item for item in observations if _mapping(item.payload.get(key))]
    if not candidates:
        return {}, set()
    winner, selected = candidates[0], _mapping(candidates[0].payload[key])
    conflicts: set[str] = set()
    for contender in candidates[1:]:
        if _mapping(contender.payload[key]) != selected:
            if winner.authority == "IMMUTABLE_V1" or contender.authority == "IMMUTABLE_V1":
                conflicts.add("PROTECTED_ROUTE_CONFLICT" if route else f"PROTECTED_{key.upper()}_CONFLICT")
            else:
                conflicts.add("ROUTE_CONFLICT" if route else f"{key.upper()}_CONFLICT")
    return selected, conflicts


def _select_hash(observations: list[Observation]) -> tuple[str, set[str]]:
    candidates = [item for item in observations if isinstance(item.payload.get("payload_hash"), str) and item.payload["payload_hash"]]
    if not candidates:
        return "UNKNOWN_PAYLOAD_HASH", set()
    winner, selected = candidates[0], candidates[0].payload["payload_hash"]
    conflicts = {
        "PROTECTED_PAYLOAD_HASH_CONFLICT" if winner.authority == "IMMUTABLE_V1" or contender.authority == "IMMUTABLE_V1" else "PAYLOAD_HASH_CONFLICT"
        for contender in candidates[1:] if contender.payload["payload_hash"] != selected
    }
    return selected, conflicts


def _payload_value(observations: list[Observation], key: str, default: str) -> str:
    for item in observations:
        if isinstance(item.payload.get(key), str) and item.payload[key]:
            return item.payload[key]
    return default


def _unresolved(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(_unresolved(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_unresolved(item) for item in value)
    return isinstance(value, str) and (value.startswith("UNKNOWN_") or value.startswith("AMBIGUOUS_"))


def _provisional_fields(fields: CanonicalIdentityFields, observation_id: str) -> CanonicalIdentityFields:
    values = fields.to_dict()
    suffix = f"__OBSERVATION__{observation_id}"
    for key in ("source_module_uuid", "creation_path_kind", "root_template_uuid", "stats_entry", "effective_slot"):
        if _unresolved(values[key]):
            values[key] = values[key] + suffix
            break
    else:
        values["stats_entry"] = values["stats_entry"] + suffix
    return CanonicalIdentityFields(**values)


def _route_defaults() -> dict[str, Any]:
    return {"behavior": "UNASSESSED_ROUTE_BEHAVIOR", "target_vrs": ["UNKNOWN_TARGET_VR"], "target_paths": ["UNKNOWN_TARGET_PATH"], "payload_hashes": ["UNKNOWN_PAYLOAD_HASH"], "provider_id": "UNASSESSED_PROVIDER", "provenance": "UNASSESSED_PROVENANCE", "static_status": "STATIC_UNASSESSED", "gameplay_status": "GAMEPLAY_UNASSESSED", "save_reload_status": "SAVE_RELOAD_UNASSESSED"}


def _record_for(identity: str, digest: str, fields: CanonicalIdentityFields, observations: list[Observation], unresolved: bool) -> tuple[LedgerRecord, set[str]]:
    ordered = sorted(observations, key=_precedence)
    first = ordered[0]
    selected = {key: _select_mapping(ordered, key) for key in ("source_module", "permission", "creation_path", "source_route", "protected_relations", "transformation", "gates", "classification")}
    route_data, route_conflicts = _select_mapping(ordered, "mode_routes", route=True)
    payload_hash, hash_conflicts = _select_hash(ordered)
    conflicts = set(route_conflicts) | set(hash_conflicts)
    for _, (_, family_conflicts) in selected.items():
        conflicts.update(family_conflicts)
    blockers = set(conflicts) | {code for item in ordered for code in item.blocker_codes}
    if unresolved:
        blockers.add("IDENTITY_FIELDS_UNRESOLVED")
    if not blockers:
        blockers.add("LEDGER_FIELDS_UNASSESSED")
    body = fields.body_tuple
    source_module = {"pak": "UNKNOWN_SOURCE_PAK", "folder": "UNKNOWN_SOURCE_FOLDER", "name": "UNKNOWN_SOURCE_NAME", "uuid": fields.source_module_uuid, "version64": "UNKNOWN_SOURCE_VERSION", "pak_sha256": "UNKNOWN_SOURCE_PAK_SHA256", "profile_digest": fields.source_profile_digest} | selected["source_module"][0]
    permission = {"state": "PERMISSION_UNASSESSED", "evidence_path": "UNKNOWN_PERMISSION_EVIDENCE_PATH", "evidence_sha256": "UNKNOWN_PERMISSION_EVIDENCE_SHA256", "credit": "UNKNOWN_PERMISSION_CREDIT", "distribution_limits": "UNKNOWN_PERMISSION_LIMITS"} | selected["permission"][0]
    creation = {"kind": fields.creation_path_kind, "root_uuid": fields.root_template_uuid, "stats_entry": fields.stats_entry, "inheritance_chain": ["UNKNOWN_INHERITANCE_NODE"], "chain_digest": fields.inheritance_digest} | selected["creation_path"][0]
    classification = {"effective_slot": fields.effective_slot, "body_content": "UNKNOWN_BODY_CONTENT", "garment_family": "UNKNOWN_GARMENT_FAMILY", "class_id": "UNKNOWN_CLASS_ID", "class_contract_digest": "UNKNOWN_CLASS_CONTRACT_DIGEST"} | selected["classification"][0]
    source_route = {"ordered_vrs": list(fields.ordered_source_vrs), "ordered_paths": ["UNKNOWN_SOURCE_PATH"], "ordered_file_hashes": ["UNKNOWN_SOURCE_FILE_HASH"], "component_contract_digest": fields.component_contract_digest} | selected["source_route"][0]
    protected = {"registry_ids": ["UNKNOWN_PROTECTED_REGISTRY"], "protected_consumers": ["UNKNOWN_PROTECTED_CONSUMER"], "shared_assets": ["UNKNOWN_SHARED_ASSET"], "forbidden_targets": ["UNKNOWN_FORBIDDEN_TARGET"]} | selected["protected_relations"][0]
    transformation = {"eligibility": "UNASSESSED_ELIGIBILITY", "strategy": "UNASSESSED_STRATEGY", "allowed_components": ["UNKNOWN_ALLOWED_COMPONENT"], "allowed_channels": ["UNKNOWN_ALLOWED_CHANNEL"], "exception_id": "UNKNOWN_EXCEPTION_ID", **selected["transformation"][0], "payload_hash": payload_hash}
    gates = {name: "UNASSESSED_GATE" for name in _GATES} | selected["gates"][0]
    record = LedgerRecord(
        record_id=f"LEDGER_{digest}", canonical_identity=identity, identity_sha256=digest,
        source_module=source_module, permission=permission, creation_path=creation, classification=classification,
        body_tuple={"race": body[0], "sex": body[1], "body_type": body[2], "body_shape": body[3], "equipment_race": body[4]}, source_route=source_route,
        mode_routes={mode: _route_defaults() | _mapping(route_data.get(mode)) for mode in _MODES}, protected_relations=protected, transformation=transformation, gates=gates,
        evidence_paths=tuple(dict.fromkeys(path for item in ordered for path in item.evidence_pointers)), evidence_hashes=tuple(dict.fromkeys(item.input_sha256 for item in ordered)),
        disposition=first.disposition, blocker_codes=tuple(sorted(blockers)), release_blocking=any(item.release_blocking for item in ordered) or bool(conflicts) or unresolved,
        next_admissible_action=_payload_value(ordered, "next_admissible_action", "Obtain bounded evidence."), acceptance_event_id=_payload_value(ordered, "acceptance_event_id", "UNKNOWN_ACCEPTANCE_EVENT"), shipped_package_id=_payload_value(ordered, "shipped_package_id", "UNKNOWN_SHIPPED_PACKAGE"),
    )
    errors = validate_record(record.to_dict())
    if errors:
        raise ValueError("RECONCILIATION_RECORD_INVALID:" + ",".join(errors))
    return record, conflicts


def reconcile_observations(observations: Iterable[Observation]) -> ReconciliationResult:
    """Join only complete exact identities; unresolved identities stay provisional."""
    grouped: dict[str, tuple[CanonicalIdentityFields, bool, list[Observation]]] = {}
    seen: set[str] = set()
    for observation in observations:
        if observation.observation_id in seen:
            raise ValueError(f"DUPLICATE_OBSERVATION_ID:{observation.observation_id}")
        seen.add(observation.observation_id)
        unresolved = _unresolved(observation.identity_fields.to_dict())
        fields = _provisional_fields(observation.identity_fields, observation.observation_id) if unresolved else observation.identity_fields
        identity, _ = build_identity(fields)
        grouped.setdefault(identity, (fields, unresolved, []))[2].append(observation)
    grouped_items = sorted(grouped.items(), key=lambda item: build_identity(item[1][0])[1])
    results = [_record_for(identity, build_identity(fields)[1], fields, items, unresolved) for identity, (fields, unresolved, items) in grouped_items]
    records = tuple(record for record, _ in results)
    observation_to_record = {item.observation_id: record.record_id for record, _ in results for item in grouped[record.canonical_identity][2]}
    return ReconciliationResult(records, observation_to_record, tuple(sorted({code for _, codes in results for code in codes})))
