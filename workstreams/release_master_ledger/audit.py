"""Fail-closed exact-once and closure audit for reconciled synthetic observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .exclusions import EXCLUSION_MODES, select_current_exclusion
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
    by_identity: dict[tuple[str, str], list[str]] = {}
    for record in result.records:
        by_identity.setdefault((record.canonical_identity, record.identity_sha256), []).append(record.record_id)
    return {
        record_id
        for record_ids in by_identity.values()
        if len(record_ids) > 1
        for record_id in record_ids
    }


def _section_19_summary(gates: Mapping[str, bool]) -> dict[str, bool]:
    return {name: gates.get(name) is True for name in _REQUIRED_SECTION_19_GATES}


def _current_terminal_exclusion(
    record: object,
    events: tuple[Mapping[str, object], ...],
    verified_evidence: Mapping[str, str],
) -> tuple[bool, bool]:
    """Return (valid, claimed) without ever inferring terminality from a state label."""
    record_data = record.to_dict()
    record_id = record_data["record_id"]
    claimed_events = tuple(
        event for event in events if event.get("record_id") == record_id
    )
    terminal_exclusion = record_data.get("terminal_exclusion")
    claimed = (
        bool(claimed_events)
        or terminal_exclusion is not None
        or record_data.get("disposition") == "OUT_OF_SCOPE_WITH_PROOF"
    )
    if not claimed:
        return False, False
    if (
        record_data.get("disposition") != "OUT_OF_SCOPE_WITH_PROOF"
        or record_data.get("release_blocking") is not False
        or not isinstance(terminal_exclusion, Mapping)
        or not isinstance(terminal_exclusion.get("event"), Mapping)
    ):
        return False, True
    attached_event = terminal_exclusion["event"]
    if any(
        not isinstance(event.get("mode"), str) or event["mode"] not in EXCLUSION_MODES
        for event in claimed_events
    ):
        return False, True
    modes = sorted({event["mode"] for event in claimed_events})
    selections = tuple(
        select_current_exclusion(
            events,
            record_id,
            mode,
            ledger_record=record_data,
            evidence_hashes=verified_evidence,
        )
        for mode in modes
    )
    selected = tuple(
        selection.event for selection in selections if selection.event is not None
    )
    return (
        len(selected) == 1
        and not any(selection.errors for selection in selections)
        and selected[0] == attached_event,
        True,
    )


def build_completeness_audit(
    result: ReconciliationResult,
    inventories: InventorySets,
    *,
    exclusion_events: tuple[Mapping[str, object], ...] = (),
    verified_evidence: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Compute exact, sorted audit sets without inferring later gate success."""
    events = tuple(event for event in exclusion_events if isinstance(event, Mapping))
    evidence = verified_evidence if isinstance(verified_evidence, Mapping) else {}
    represented = set(result.observation_to_record)
    record_ids = {record.record_id for record in result.records}
    evidence_paths = {path for record in result.records for path in record.evidence_paths}
    package_ids = record_ids | {
        record.shipped_package_id for record in result.records
        if record.shipped_package_id != "UNKNOWN_SHIPPED_PACKAGE"
    }
    valid_exclusions: set[str] = set()
    exclusion_failures: set[str] = set()
    excluded_but_packaged: set[str] = set()
    for record in result.records:
        valid, claimed = _current_terminal_exclusion(record, events, evidence)
        if claimed and not valid:
            exclusion_failures.add(record.record_id)
        if not valid:
            continue
        if record.shipped_package_id != "UNKNOWN_SHIPPED_PACKAGE":
            excluded_but_packaged.add(record.record_id)
        else:
            valid_exclusions.add(record.record_id)
    nonterminal = {
        record.record_id for record in result.records
        if (
            record.record_id in exclusion_failures
            or record.record_id in excluded_but_packaged
            or (
                record.record_id not in valid_exclusions
                and (
                    record.disposition not in _TERMINAL_DISPOSITIONS
                    or record.release_blocking
                )
            )
        )
    }
    duplicate_identity = _duplicate_observations(result)
    sourced_record_ids = {
        result.observation_to_record[observation_id]
        for observation_id in inventories.source_observations
        if observation_id in result.observation_to_record
    }
    audit_sets = {
        "missing_from_ledger": set(inventories.source_observations) - represented,
        "duplicate_identity": duplicate_identity,
        "unreferenced_prior_evidence": set(inventories.prior_evidence) - evidence_paths,
        "packaged_without_ledger": set(inventories.packaged_records) - package_ids,
        "ledger_without_source": record_ids - sourced_record_ids,
        "in_scope_nonterminal": nonterminal,
        "excluded_with_proof": valid_exclusions,
        "exclusion_validation_failures": exclusion_failures,
        "excluded_but_packaged": excluded_but_packaged,
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
        "required_source_profiles": sorted(inventories.required_source_profiles),
        "complete_source_profiles": sorted(inventories.complete_source_profiles),
        "missing_source_profiles": sorted(
            set(inventories.required_source_profiles) - set(inventories.complete_source_profiles)
        ),
        "unclassified_count": sum(record.disposition == "UNCLASSIFIED" for record in result.records),
        "required_source_profiles_complete": profile_complete,
        "section_19_gates": section_19_gates,
        "source_complete": source_complete,
        "release_complete": release_complete,
    }
