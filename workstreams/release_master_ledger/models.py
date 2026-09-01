"""Deterministic public data structures for release-ledger evidence."""

from dataclasses import dataclass, field
from typing import Any, Mapping


def _stable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _stable_value(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_stable_value(item) for item in value]
    return value


@dataclass(frozen=True)
class CanonicalIdentityFields:
    """Every spec-bound field used to construct a concrete ledger identity."""

    source_module_uuid: str
    source_profile_digest: str
    creation_path_kind: str
    root_template_uuid: str
    stats_entry: str
    inheritance_digest: str
    effective_slot: str
    body_tuple: tuple[str, ...]
    ordered_source_vrs: tuple[str, ...]
    component_contract_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source_module_uuid": self.source_module_uuid,
            "source_profile_digest": self.source_profile_digest,
            "creation_path_kind": self.creation_path_kind,
            "root_template_uuid": self.root_template_uuid,
            "stats_entry": self.stats_entry,
            "inheritance_digest": self.inheritance_digest,
            "effective_slot": self.effective_slot,
            "body_tuple": list(self.body_tuple),
            "ordered_source_vrs": list(self.ordered_source_vrs),
            "component_contract_digest": self.component_contract_digest,
        }


@dataclass(frozen=True)
class Observation:
    """One source-bounded observation before it is reconciled into a ledger row."""

    observation_id: str
    observation_kind: str
    identity_fields: CanonicalIdentityFields
    source_reference: str
    evidence_files: tuple[str, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    blocker_codes: tuple[str, ...] = ()

    def _adapter_value(self, key: str, default: Any) -> Any:
        """Expose adapter metadata without changing the base observation wire shape."""
        if isinstance(self.payload, Mapping):
            return self.payload.get(key, default)
        return default

    @property
    def input_id(self) -> str:
        return self._adapter_value("input_id", "UNKNOWN_INPUT_ID")

    @property
    def input_sha256(self) -> str:
        return self._adapter_value("input_sha256", "UNKNOWN_INPUT_SHA256")

    @property
    def authority(self) -> str:
        return self._adapter_value("authority", "OBSERVATION")

    @property
    def evidence_status(self) -> str:
        return self._adapter_value("evidence_status", "EVIDENCE_UNASSESSED")

    @property
    def disposition(self) -> str:
        return self._adapter_value("disposition", "DEFERRED_WITH_CAUSE")

    @property
    def release_blocking(self) -> bool:
        return self._adapter_value("release_blocking", True)

    @property
    def protected_relations(self) -> Mapping[str, Any]:
        return self._adapter_value("protected_relations", {})

    @property
    def classification(self) -> Mapping[str, Any]:
        return self._adapter_value("classification", {"effective_slot": "AMBIGUOUS_SLOT"})

    @property
    def evidence_pointers(self) -> tuple[str, ...]:
        return tuple(self._adapter_value("evidence_pointers", self.evidence_files))

    @property
    def raw_evidence(self) -> Mapping[str, Any]:
        return self._adapter_value("raw_evidence", {})

    def to_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "observation_kind": self.observation_kind,
            "identity_fields": self.identity_fields.to_dict(),
            "source_reference": self.source_reference,
            "evidence_files": list(self.evidence_files),
            "payload": _stable_value(self.payload),
            "blocker_codes": list(self.blocker_codes),
        }


@dataclass(frozen=True)
class LedgerRecord:
    """A deterministic emitted record containing every section-9.2 field family."""

    record_id: str
    canonical_identity: str
    identity_sha256: str
    source_module: Mapping[str, Any]
    permission: Mapping[str, Any]
    creation_path: Mapping[str, Any]
    classification: Mapping[str, Any]
    body_tuple: Mapping[str, Any]
    source_route: Mapping[str, Any]
    mode_routes: Mapping[str, Any]
    protected_relations: Mapping[str, Any]
    transformation: Mapping[str, Any]
    gates: Mapping[str, Any]
    evidence_paths: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    disposition: str
    blocker_codes: tuple[str, ...]
    release_blocking: bool
    next_admissible_action: str
    acceptance_event_id: str
    shipped_package_id: str
    terminal_exclusion: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "canonical_identity": self.canonical_identity,
            "identity_sha256": self.identity_sha256,
            "source_module": _stable_value(self.source_module),
            "permission": _stable_value(self.permission),
            "creation_path": _stable_value(self.creation_path),
            "classification": _stable_value(self.classification),
            "body_tuple": _stable_value(self.body_tuple),
            "source_route": _stable_value(self.source_route),
            "mode_routes": _stable_value(self.mode_routes),
            "protected_relations": _stable_value(self.protected_relations),
            "transformation": _stable_value(self.transformation),
            "gates": _stable_value(self.gates),
            "evidence_paths": list(self.evidence_paths),
            "evidence_hashes": list(self.evidence_hashes),
            "disposition": self.disposition,
            "blocker_codes": list(self.blocker_codes),
            "release_blocking": self.release_blocking,
            "next_admissible_action": self.next_admissible_action,
            "acceptance_event_id": self.acceptance_event_id,
            "shipped_package_id": self.shipped_package_id,
            "terminal_exclusion": _stable_value(self.terminal_exclusion),
        }
