"""Fail-closed exact-once and closure audit for reconciled synthetic observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import re

from .exclusions import RELEASE_MODES, ZERO_CLAIM_MODE_ROUTE, select_current_exclusion
from .identity import canonical_json, sha256_text
from .reconcile import ReconciliationResult


_TERMINAL_DISPOSITIONS = {
    "ACCEPTED_PROTECTED", "SHIPPED_NATIVE_PASSTHROUGH", "SHIPPED_REFIT",
}
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
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


def _has_valid_event_file_provenance(
    terminal_exclusion: Mapping[str, object],
    event: Mapping[str, object],
    discovered_event_files: Mapping[str, str],
) -> bool:
    """Require the selected event's exact immutable file provenance."""
    if set(terminal_exclusion) != {"event", "event_file"}:
        return False
    event_file = terminal_exclusion.get("event_file")
    if not isinstance(event_file, Mapping):
        return False
    if set(event_file) != {
        "relative_path", "sha256", "canonical_event_sha256",
    }:
        return False
    relative_path = event_file.get("relative_path")
    digest = event_file.get("sha256")
    canonical_digest = event_file.get("canonical_event_sha256")
    return (
        isinstance(relative_path, str)
        and bool(relative_path)
        and not relative_path.startswith(("/", "\\"))
        and ".." not in relative_path.replace("\\", "/").split("/")
        and isinstance(digest, str)
        and _SHA256_RE.fullmatch(digest) is not None
        and isinstance(canonical_digest, str)
        and _SHA256_RE.fullmatch(canonical_digest) is not None
        and canonical_digest == sha256_text(canonical_json(event))
        and discovered_event_files.get(relative_path) == digest
    )


def _has_independent_claim(
    claims: Mapping[object, object] | None, record_id: str, mode: str,
) -> bool:
    if not isinstance(claims, Mapping):
        return False
    candidates = (
        claims.get((record_id, mode)),
        claims.get(f"{record_id}:{mode}"),
        claims.get(mode),
    )
    nested = claims.get(record_id)
    if isinstance(nested, Mapping):
        candidates += (nested.get(mode),)
    return any(bool(value) for value in candidates)


def _current_terminal_exclusion(
    record: object,
    events: tuple[Mapping[str, object], ...],
    verified_evidence: Mapping[str, str],
    discovered_event_files: Mapping[str, str],
    independent_provider_claims: Mapping[object, object] | None,
    independent_package_claims: Mapping[object, object] | None,
) -> tuple[set[str], bool, bool, bool, set[str]]:
    """Return valid modes, record closure, claimed, packaged conflict, and codes."""
    record_data = record.to_dict()
    record_id = record_data["record_id"]
    claimed_events = tuple(
        event for event in events if event.get("record_id") == record_id
    )
    terminal_exclusion = record_data.get("terminal_exclusion")
    scopes = record_data.get("mode_scope")
    valid_modes: set[str] = set()
    failure_codes: set[str] = set()
    claimed = bool(claimed_events) or record_data.get("disposition") == "OUT_OF_SCOPE_WITH_PROOF"
    packaged_conflict = False
    for mode in RELEASE_MODES:
        history = tuple(
            event for event in claimed_events if event.get("mode") == mode
        )
        summary = (
            terminal_exclusion.get(mode)
            if isinstance(terminal_exclusion, Mapping) else None
        )
        scope = scopes.get(mode) if isinstance(scopes, Mapping) else None
        mode_claimed = bool(history) or summary is not None or (
            isinstance(scope, Mapping)
            and scope.get("terminal_state") == "OUT_OF_SCOPE_WITH_PROOF"
        )
        claimed = claimed or mode_claimed
        if not mode_claimed:
            continue
        if (
            independent_provider_claims is None
            or independent_package_claims is None
        ):
            failure_codes.add(
                "MISSING_INDEPENDENT_EXCLUSION_CLAIM_CONTEXT:"
                f"{record_id}:{mode}"
            )
            continue
        independent_conflict = False
        if _has_independent_claim(
            independent_provider_claims, record_id, mode,
        ):
            failure_codes.add(
                f"INDEPENDENT_PROVIDER_CLAIM:{record_id}:{mode}"
            )
            independent_conflict = True
        if _has_independent_claim(
            independent_package_claims, record_id, mode,
        ):
            failure_codes.add(
                f"INDEPENDENT_PACKAGE_CLAIM:{record_id}:{mode}"
            )
            packaged_conflict = True
            independent_conflict = True
        if (
            summary is not None
            and record_data.get("shipped_package_id") != "UNKNOWN_SHIPPED_PACKAGE"
        ):
            packaged_conflict = True
        if independent_conflict:
            continue
        selection = select_current_exclusion(
            events,
            record_id,
            mode,
            ledger_record=record_data,
            evidence_hashes=verified_evidence,
        )
        for error in selection.errors:
            failure_codes.add(f"{error}:{record_id}:{mode}")
        if selection.errors:
            continue
        if not isinstance(summary, Mapping) or not isinstance(summary.get("event"), Mapping):
            failure_codes.add(f"EXCLUSION_ATTACHMENT_MISSING:{record_id}:{mode}")
            continue
        attached_event = summary["event"]
        if selection.event != attached_event:
            failure_codes.add(f"EXCLUSION_ATTACHMENT_NOT_CURRENT:{record_id}:{mode}")
            continue
        if not _has_valid_event_file_provenance(
            summary, attached_event, discovered_event_files,
        ):
            failure_codes.add(f"EXCLUSION_EVENT_FILE_INVALID:{record_id}:{mode}")
            continue
        route = record_data.get("mode_routes")
        route = route.get(mode) if isinstance(route, Mapping) else None
        if route != ZERO_CLAIM_MODE_ROUTE:
            failure_codes.add(f"EXCLUDED_MODE_ROUTE_CLAIM:{record_id}:{mode}")
            packaged_conflict = True
            continue
        if record_data.get("shipped_package_id") != "UNKNOWN_SHIPPED_PACKAGE":
            failure_codes.add(f"EXCLUDED_MODE_PACKAGE_CLAIM:{record_id}:{mode}")
            packaged_conflict = True
            continue
        valid_modes.add(mode)
    malformed_modes = [
        event for event in claimed_events
        if not isinstance(event.get("mode"), str)
        or event.get("mode") not in RELEASE_MODES
    ]
    if malformed_modes:
        for event in malformed_modes:
            raw_mode = event.get("mode")
            mode_token = raw_mode if isinstance(raw_mode, str) and raw_mode else "INVALID_MODE"
            failure_codes.add(
                f"INVALID_EXCLUSION_HISTORY_MODE:{record_id}:{mode_token}"
            )
    record_closed = (
        valid_modes == set(RELEASE_MODES)
        and record_data.get("disposition") == "OUT_OF_SCOPE_WITH_PROOF"
        and record_data.get("release_blocking") is False
    )
    if record_data.get("disposition") == "OUT_OF_SCOPE_WITH_PROOF" and not record_closed:
        failure_codes.add(f"EXCLUSION_RECORD_CLOSURE_INCOMPLETE:{record_id}")
    return valid_modes, record_closed, claimed, packaged_conflict, failure_codes


def build_completeness_audit(
    result: ReconciliationResult,
    inventories: InventorySets,
    *,
    exclusion_events: tuple[Mapping[str, object], ...] = (),
    verified_evidence: Mapping[str, str] | None = None,
    discovered_event_files: Mapping[str, str] | None = None,
    independent_provider_claims: Mapping[object, object] | None = None,
    independent_package_claims: Mapping[object, object] | None = None,
) -> dict[str, object]:
    """Compute exact, sorted audit sets without inferring later gate success."""
    events = tuple(event for event in exclusion_events if isinstance(event, Mapping))
    evidence = verified_evidence if isinstance(verified_evidence, Mapping) else {}
    event_files = discovered_event_files if isinstance(discovered_event_files, Mapping) else {}
    represented = set(result.observation_to_record)
    record_ids = {record.record_id for record in result.records}
    evidence_paths = {path for record in result.records for path in record.evidence_paths}
    package_ids = record_ids | {
        record.shipped_package_id for record in result.records
        if record.shipped_package_id != "UNKNOWN_SHIPPED_PACKAGE"
    }
    valid_exclusions: set[str] = set()
    valid_excluded_modes: set[str] = set()
    exclusion_failures: set[str] = set()
    exclusion_history_failures: set[str] = set()
    excluded_but_packaged: set[str] = set()
    for event in events:
        record_id = event.get("record_id")
        if not isinstance(record_id, str) or record_id not in record_ids:
            token = record_id if isinstance(record_id, str) and record_id else "INVALID_RECORD_ID"
            exclusion_history_failures.add(
                f"UNMATCHED_EXCLUSION_RECORD:{token}"
            )
    for record in result.records:
        (
            valid_modes,
            record_closed,
            claimed,
            packaged_conflict,
            failure_codes,
        ) = _current_terminal_exclusion(
            record, events, evidence, event_files,
            independent_provider_claims, independent_package_claims,
        )
        valid_excluded_modes.update(
            f"{record.record_id}:{mode}" for mode in valid_modes
        )
        exclusion_history_failures.update(failure_codes)
        if claimed and failure_codes:
            exclusion_failures.add(record.record_id)
        if packaged_conflict:
            excluded_but_packaged.add(record.record_id)
        if record_closed and not failure_codes and not packaged_conflict:
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
        "excluded_modes_with_proof": valid_excluded_modes,
        "excluded_with_proof": valid_exclusions,
        "exclusion_validation_failures": exclusion_failures,
        "exclusion_history_failures": exclusion_history_failures,
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
    release_complete = (
        source_complete
        and not audit_sets["in_scope_nonterminal"]
        and not audit_sets["exclusion_validation_failures"]
        and not audit_sets["exclusion_history_failures"]
        and not audit_sets["excluded_but_packaged"]
        and all(section_19_gates.values())
    )
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
