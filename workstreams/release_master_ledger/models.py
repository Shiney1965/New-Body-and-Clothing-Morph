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
    """A deterministic, emitted ledger record with route and evidence details."""

    identity: str
    identity_fields: CanonicalIdentityFields
    source_module: Mapping[str, Any]
    creation_path: Mapping[str, Any]
    classification: Mapping[str, Any]
    source_visual_resources: tuple[Mapping[str, Any], ...]
    component_contract: Mapping[str, Any]
    mode_routes: Mapping[str, Any]
    disposition: str
    next_action: str
    evidence_files: tuple[str, ...] = ()
    gameplay_results: Mapping[str, Any] = field(default_factory=dict)
    known_defect: Mapping[str, Any] = field(default_factory=dict)
    protected_controls: tuple[str, ...] = ()
    package_ownership: Mapping[str, Any] = field(default_factory=dict)
    blocker_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "identity_fields": self.identity_fields.to_dict(),
            "source_module": _stable_value(self.source_module),
            "creation_path": _stable_value(self.creation_path),
            "classification": _stable_value(self.classification),
            "source_visual_resources": _stable_value(self.source_visual_resources),
            "component_contract": _stable_value(self.component_contract),
            "mode_routes": _stable_value(self.mode_routes),
            "disposition": self.disposition,
            "next_action": self.next_action,
            "evidence_files": list(self.evidence_files),
            "gameplay_results": _stable_value(self.gameplay_results),
            "known_defect": _stable_value(self.known_defect),
            "protected_controls": list(self.protected_controls),
            "package_ownership": _stable_value(self.package_ownership),
            "blocker_codes": list(self.blocker_codes),
        }
