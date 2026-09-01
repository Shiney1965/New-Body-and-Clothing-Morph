"""Fail-closed exact-once and closure audit for reconciled synthetic observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .reconcile import ReconciliationResult


_TERMINAL_DISPOSITIONS = {
    "ACCEPTED_PROTECTED", "SHIPPED_NATIVE_PASSTHROUGH", "SHIPPED_REFIT",
}
_REQUIRED_SECTION_19_GATES = (
    "protected_controls", "in_scope_terminal", "in_scope_terminal_modes",
    "package_only_gameplay", "source_observations_exactly_once", "route_ownership",
    "permissions_release_cleared", "package_profile_build_fresh_extract",
    "gameplay_class_random_save_reload", "advertised_combined_profiles", "installer_restore",
)


@dataclass(frozen=True)
class InventorySets:
    """Explicit, caller-supplied audit inventories; empty values never imply success."""

    source_observations: frozenset[str] = frozenset()
    prior_evidence: frozenset[str] = frozenset()
    packaged_records: frozenset[str] = frozenset()
    required_source_profiles: frozenset[str] = frozenset()
    complete_source_profiles: frozenset[str] = frozenset()
    section_19_gates: Mapping[str, bool] = field(default_factory=dict)


def _sorted(values: set[str]) -> list[str]:
    return sorted(values)


def _duplicate_observations(result: ReconciliationResult) -> set[str]:
    by_record: dict[str, list[str]] = {}
    for observation_id, record_id in result.observation_to_record.items():
        by_record.setdefault(record_id, []).append(observation_id)
    return {
        observation_id
        for observation_ids in by_record.values()
        if len(observation_ids) > 1
        for observation_id in observation_ids
    }


def _section_19_summary(gates: Mapping[str, bool]) -> dict[str, bool]:
    return {name: gates.get(name) is True for name in _REQUIRED_SECTION_19_GATES}


def build_completeness_audit(
    result: ReconciliationResult, inventories: InventorySets
) -> dict[str, object]:
    """Compute the six exact, sorted audit sets without inferring later gate success."""
    represented = set(result.observation_to_record)
    record_ids = {record.record_id for record in result.records}
    evidence_paths = {path for record in result.records for path in record.evidence_paths}
    package_ids = record_ids | {
        record.shipped_package_id for record in result.records
        if record.shipped_package_id != "UNKNOWN_SHIPPED_PACKAGE"
    }
    nonterminal = {
        record.record_id for record in result.records
        if record.disposition not in _TERMINAL_DISPOSITIONS or record.release_blocking
    }
    duplicate_identity = _duplicate_observations(result)
    audit_sets = {
        "missing_from_ledger": set(inventories.source_observations) - represented,
        "duplicate_identity": duplicate_identity,
        "unreferenced_prior_evidence": set(inventories.prior_evidence) - evidence_paths,
        "packaged_without_ledger": set(inventories.packaged_records) - package_ids,
        "ledger_without_source": {
            record_id for observation_id, record_id in result.observation_to_record.items()
            if observation_id not in inventories.source_observations
        },
        "in_scope_nonterminal": nonterminal,
    }
    profile_complete = set(inventories.required_source_profiles) <= set(inventories.complete_source_profiles)
    source_complete = (
        all(not audit_sets[name] for name in (
            "missing_from_ledger", "duplicate_identity", "unreferenced_prior_evidence",
            "packaged_without_ledger", "ledger_without_source",
        ))
        and profile_complete
    )
    section_19_gates = _section_19_summary(inventories.section_19_gates)
    release_complete = source_complete and not audit_sets["in_scope_nonterminal"] and all(section_19_gates.values())
    return {
        **{name: _sorted(values) for name, values in audit_sets.items()},
        "unclassified_count": sum(record.disposition == "UNCLASSIFIED" for record in result.records),
        "required_source_profiles_complete": profile_complete,
        "section_19_gates": section_19_gates,
        "source_complete": source_complete,
        "release_complete": release_complete,
    }
