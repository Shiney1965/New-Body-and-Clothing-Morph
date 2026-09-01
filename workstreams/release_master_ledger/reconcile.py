"""Deterministic, fixture-only reconciliation of canonical release-ledger identities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .identity import build_identity
from .models import LedgerRecord, Observation


_AUTHORITY_PRECEDENCE = {
    "IMMUTABLE_V1": 0,
    "ITEM_GAMEPLAY": 1,
    "PACKAGE_EVIDENCE": 2,
    "STATIC_EVIDENCE": 2,
    "WORKSTREAM_EVIDENCE": 3,
    "DESIGN_EVIDENCE": 4,
    "CLASSIFICATION_EVIDENCE": 4,
    "NAMED_TARGET_EVIDENCE": 5,
    "OBSERVATION": 5,
}
_MODES = ("vanilla", "sbbf", "bcb", "external")


@dataclass(frozen=True)
class ReconciliationResult:
    """Canonical records and the complete, deterministic observation mapping."""

    records: tuple[LedgerRecord, ...]
    observation_to_record: Mapping[str, str]
    conflicts: tuple[str, ...]


def _precedence(observation: Observation) -> tuple[int, str, str]:
    return (
        _AUTHORITY_PRECEDENCE.get(observation.authority, 5),
        observation.observation_id,
        observation.source_reference,
    )


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _payload_mapping(observation: Observation, key: str) -> dict[str, Any]:
    return _mapping(observation.payload.get(key))


def _select_mapping(
    observations: list[Observation], key: str, *, route: bool = False
) -> tuple[dict[str, Any], set[str]]:
    candidates = [item for item in observations if _payload_mapping(item, key)]
    if not candidates:
        return {}, set()
    winner = candidates[0]
    selected = _payload_mapping(winner, key)
    conflicts: set[str] = set()
    for contender in candidates[1:]:
        value = _payload_mapping(contender, key)
        if value == selected:
            continue
        if winner.authority == "IMMUTABLE_V1" or contender.authority == "IMMUTABLE_V1":
            conflicts.add("PROTECTED_ROUTE_CONFLICT" if route else f"PROTECTED_{key.upper()}_CONFLICT")
        elif route:
            conflicts.add("ROUTE_CONFLICT")
        else:
            conflicts.add(f"{key.upper()}_CONFLICT")
    return selected, conflicts


def _mode_routes(observations: list[Observation]) -> tuple[dict[str, Any], set[str]]:
    selected, conflicts = _select_mapping(observations, "mode_routes", route=True)
    return {mode: _mapping(selected.get(mode)) for mode in _MODES}, conflicts


def _payload_value(observations: list[Observation], key: str, default: Any) -> Any:
    for observation in observations:
        if key in observation.payload:
            return observation.payload[key]
    return default


def _record_for(identity: str, digest: str, observations: list[Observation]) -> tuple[LedgerRecord, set[str]]:
    ordered = sorted(observations, key=_precedence)
    first = ordered[0]
    source_module, source_module_conflicts = _select_mapping(ordered, "source_module")
    permission, permission_conflicts = _select_mapping(ordered, "permission")
    creation_path, creation_conflicts = _select_mapping(ordered, "creation_path")
    source_route, source_route_conflicts = _select_mapping(ordered, "source_route")
    protected_relations, protected_conflicts = _select_mapping(ordered, "protected_relations")
    transformation, transformation_conflicts = _select_mapping(ordered, "transformation")
    gates, gate_conflicts = _select_mapping(ordered, "gates")
    mode_routes, route_conflicts = _mode_routes(ordered)
    classification, classification_conflicts = _select_mapping(ordered, "classification")
    if not classification:
        classification = dict(first.classification)
    conflicts = set().union(
        source_module_conflicts, permission_conflicts, creation_conflicts,
        source_route_conflicts, protected_conflicts, transformation_conflicts,
        gate_conflicts, route_conflicts, classification_conflicts,
    )
    blockers = set(conflicts)
    for observation in ordered:
        blockers.update(observation.blocker_codes)
    evidence_paths = tuple(dict.fromkeys(path for item in ordered for path in item.evidence_pointers))
    evidence_hashes = tuple(dict.fromkeys(item.input_sha256 for item in ordered))
    body_values = first.identity_fields.body_tuple
    body_tuple = {
        "race": body_values[0], "sex": body_values[1], "body_type": body_values[2],
        "body_shape": body_values[3], "equipment_race": body_values[4],
    }
    record = LedgerRecord(
        record_id=f"LEDGER_{digest}", canonical_identity=identity, identity_sha256=digest,
        source_module=source_module or {"uuid": first.identity_fields.source_module_uuid},
        permission=permission or {"state": "PERMISSION_UNASSESSED"},
        creation_path=creation_path or {
            "kind": first.identity_fields.creation_path_kind,
            "root_template_uuid": first.identity_fields.root_template_uuid,
            "stats_entry": first.identity_fields.stats_entry,
            "inheritance_digest": first.identity_fields.inheritance_digest,
        },
        classification=classification,
        body_tuple=body_tuple,
        source_route=source_route or {"ordered_vrs": list(first.identity_fields.ordered_source_vrs)},
        mode_routes=mode_routes,
        protected_relations=protected_relations or dict(first.protected_relations),
        transformation=transformation or {"payload_hash": _payload_value(ordered, "payload_hash", "UNKNOWN_PAYLOAD_HASH")},
        gates=gates or {"package": False, "gameplay": False, "installer": False},
        evidence_paths=evidence_paths, evidence_hashes=evidence_hashes,
        disposition=first.disposition,
        blocker_codes=tuple(sorted(blockers)),
        release_blocking=any(item.release_blocking for item in ordered) or bool(conflicts),
        next_admissible_action=_payload_value(ordered, "next_admissible_action", "Obtain bounded evidence."),
        acceptance_event_id=_payload_value(ordered, "acceptance_event_id", "UNKNOWN_ACCEPTANCE_EVENT"),
        shipped_package_id=_payload_value(ordered, "shipped_package_id", "UNKNOWN_SHIPPED_PACKAGE"),
    )
    return record, conflicts


def reconcile_observations(observations: Iterable[Observation]) -> ReconciliationResult:
    """Join only observations whose complete canonical identities are identical."""
    grouped: dict[str, list[Observation]] = {}
    digests: dict[str, str] = {}
    for observation in observations:
        identity, digest = build_identity(observation.identity_fields)
        grouped.setdefault(identity, []).append(observation)
        digests[identity] = digest
    records_and_conflicts = [
        _record_for(identity, digests[identity], grouped[identity])
        for identity in sorted(grouped, key=lambda item: digests[item])
    ]
    records = tuple(record for record, _ in records_and_conflicts)
    observation_to_record = {
        observation.observation_id: record.record_id
        for record, _ in records_and_conflicts
        for observation in grouped[record.canonical_identity]
    }
    conflicts = tuple(sorted({code for _, codes in records_and_conflicts for code in codes}))
    return ReconciliationResult(records, observation_to_record, conflicts)
