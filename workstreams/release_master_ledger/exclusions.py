"""Fail-closed validation and selection of terminal-exclusion events.

This module intentionally has no filesystem or generation responsibilities.
It validates one append-only event against an already-reconciled ledger record
and deterministically selects an event only when its event history is
unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .identity import canonical_json, sha256_text


EXCLUSION_SCHEMA = "clothmorph.terminal-exclusion"
EXCLUSION_SCHEMA_VERSION = 1
EXCLUSION_REASONS = frozenset({
    "SOURCE_ABSENT_EXACT_PROFILE",
    "NO_RELEASE_PERMISSION",
    "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE",
    "PROTECTED_NATIVE_ONLY",
    "NO_SAFE_GEOMETRY_AVAILABLE",
    "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT",
    "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE",
})
EXCLUSION_MODES = frozenset({"vanilla", "sbbf", "bcb", "external", "source"})
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
RECORD_ID_RE = re.compile(r"^LEDGER_[0-9A-F]{64}$")
TIEFLING_PAK = "ClothMorphTieflingBT1_TEST.pak"
TIEFLING_UUID = "b57bab2c-5679-5445-8fee-ca8c282990a5"
TIEFLING_SHA256 = "01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141"


@dataclass(frozen=True)
class ExclusionSelection:
    """The sole current event for a route, or fail-closed selection errors."""

    event: Mapping[str, object] | None
    errors: tuple[str, ...] = ()


def canonical_exclusion_payload(event: Mapping[str, object]) -> str:
    """Return canonical event JSON with the self-referential event ID omitted."""
    payload = {key: value for key, value in event.items() if key != "event_id"}
    return canonical_json(payload)


def exclusion_event_id(event: Mapping[str, object]) -> str:
    """Return the deterministic ID bound to every event field except event_id."""
    return f"EXCLUSION_{sha256_text(canonical_exclusion_payload(event))}"


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == ()


def _record_mapping(record: object) -> Mapping[str, object] | None:
    if isinstance(record, Mapping):
        return record
    to_dict = getattr(record, "to_dict", None)
    candidate = to_dict() if callable(to_dict) else None
    return candidate if isinstance(candidate, Mapping) else None


def _profile_id(record: Mapping[str, object]) -> object:
    module = record.get("source_module")
    if not isinstance(module, Mapping):
        return None
    return module.get("profile_id", module.get("folder"))


def _known_hashes(evidence_hashes: object) -> set[object]:
    if isinstance(evidence_hashes, Mapping):
        return set(evidence_hashes) | set(evidence_hashes.values())
    if isinstance(evidence_hashes, Iterable) and not isinstance(evidence_hashes, str | bytes):
        return set(evidence_hashes)
    return set()


def _validate_text(event: Mapping[str, object], field: str, errors: list[str]) -> None:
    if field not in event:
        errors.append(f"MISSING:{field}")
    elif _is_blank(event[field]):
        errors.append(f"BLANK:{field}")
    elif not isinstance(event[field], str):
        errors.append(f"INVALID_TYPE:{field}")


def _validate_created_utc(value: object, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append("INVALID_CREATED_UTC")
        return
    try:
        datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        errors.append("INVALID_CREATED_UTC")


def _validate_evidence(event: Mapping[str, object], known_hashes: set[object], errors: list[str]) -> list[str]:
    evidence = event.get("evidence")
    claims: list[str] = []
    if not isinstance(evidence, (list, tuple)):
        errors.append("INVALID:evidence")
        return claims
    if not evidence:
        errors.append("EVIDENCE_REQUIRED")
        return claims
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            errors.append(f"INVALID:evidence[{index}]")
            continue
        for field in ("path", "sha256", "claim"):
            value = item.get(field)
            if _is_blank(value):
                errors.append(f"BLANK:evidence[{index}].{field}")
            elif not isinstance(value, str):
                errors.append(f"INVALID_TYPE:evidence[{index}].{field}")
        digest = item.get("sha256")
        if isinstance(digest, str) and not _is_blank(digest):
            if SHA256_RE.fullmatch(digest) is None:
                errors.append(f"INVALID_SHA256:evidence[{index}].sha256")
            elif digest not in known_hashes:
                errors.append(f"UNREGISTERED_EVIDENCE_SHA256:{index}")
        claim = item.get("claim")
        if isinstance(claim, str) and claim:
            claims.append(claim)
    return claims


def _validate_protected_impact(event: Mapping[str, object], errors: list[str]) -> None:
    impact = event.get("protected_impact")
    if not isinstance(impact, Mapping):
        errors.append("INVALID:protected_impact")
        return
    for field in ("registry_ids", "shared_consumers", "forbidden_targets"):
        value = impact.get(field)
        if not isinstance(value, (list, tuple)):
            errors.append(f"INVALID_TYPE:protected_impact.{field}")
        elif value:
            errors.append(f"PROTECTED_IMPACT_DECLARED:{field}")
    if impact.get("result") != "NO_PROTECTED_MUTATION":
        errors.append("PROTECTED_MUTATION_RESULT")


def _validate_reason_evidence(event: Mapping[str, object], claims: list[str], errors: list[str]) -> None:
    reason = event.get("reason")
    if not isinstance(reason, str) or reason not in EXCLUSION_REASONS:
        return
    combined_claims = "\n".join(claims)
    if reason not in combined_claims:
        errors.append(f"MISSING_REASON_EVIDENCE:{reason}")
    if reason != "NO_SAFE_GEOMETRY_AVAILABLE":
        return
    if "UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING" not in combined_claims:
        errors.append("MISSING_UNFIXABLE_SAFE_TOOLING_FINDING")
    architectures = event.get("attempted_architectures")
    gates = event.get("fixed_acceptance_gates")
    hard_contract = "HARD_CONTRACT_IMPOSSIBILITY" in combined_claims
    enough_architectures = (
        isinstance(architectures, (list, tuple))
        and len(set(architectures)) >= 3
        and all(isinstance(item, str) and item for item in architectures)
        and isinstance(gates, Mapping)
        and bool(gates)
    )
    if not hard_contract and not enough_architectures:
        errors.append("INSUFFICIENT_GEOMETRY_EXHAUSTION_EVIDENCE")


def _is_accepted_tiefling(record: Mapping[str, object]) -> bool:
    module = record.get("source_module")
    if not isinstance(module, Mapping):
        return False
    return any((
        module.get("pak") == TIEFLING_PAK,
        module.get("uuid") == TIEFLING_UUID,
        module.get("pak_sha256") == TIEFLING_SHA256,
    ))


def validate_exclusion_event(
    event: Mapping[str, object], *, ledger_record: object, evidence_hashes: object
) -> list[str]:
    """Return stable validation errors; valid append-only events return ``[]``."""
    if not isinstance(event, Mapping):
        return ["INVALID:event"]
    record = _record_mapping(ledger_record)
    if record is None:
        return ["INVALID:ledger_record"]

    errors: list[str] = []
    if event.get("schema") != EXCLUSION_SCHEMA:
        errors.append("INVALID:schema")
    if event.get("schema_version") != EXCLUSION_SCHEMA_VERSION or isinstance(event.get("schema_version"), bool):
        errors.append("INVALID:schema_version")
    for field in (
        "event_id", "record_id", "identity_sha256", "source_profile_id", "mode", "reason",
        "scope_statement", "next_project_if_reopened", "approved_by", "approved_reason", "created_utc",
    ):
        _validate_text(event, field, errors)

    event_id = event.get("event_id")
    if isinstance(event_id, str) and event_id != exclusion_event_id(event):
        errors.append("EVENT_ID_MISMATCH")
    record_id = event.get("record_id")
    if isinstance(record_id, str) and RECORD_ID_RE.fullmatch(record_id) is None:
        errors.append("INVALID_RECORD_ID")
    identity = event.get("identity_sha256")
    if isinstance(identity, str) and SHA256_RE.fullmatch(identity) is None:
        errors.append("INVALID_SHA256:identity_sha256")
    if isinstance(event.get("created_utc"), str):
        _validate_created_utc(event["created_utc"], errors)

    mode = event.get("mode")
    if isinstance(mode, str) and mode and mode not in EXCLUSION_MODES:
        errors.append(f"INVALID_MODE:{mode}")
    reason = event.get("reason")
    if isinstance(reason, str) and reason and reason not in EXCLUSION_REASONS:
        errors.append(f"INVALID_EXCLUSION_REASON:{reason}")
    if not isinstance(event.get("attempted_architectures"), (list, tuple)):
        errors.append("INVALID:attempted_architectures")
    if not isinstance(event.get("fixed_acceptance_gates"), Mapping):
        errors.append("INVALID:fixed_acceptance_gates")

    claims = _validate_evidence(event, _known_hashes(evidence_hashes), errors)
    _validate_protected_impact(event, errors)
    _validate_reason_evidence(event, claims, errors)

    if event.get("record_id") != record.get("record_id"):
        errors.append("RECORD_ID_MISMATCH")
    if event.get("identity_sha256") != record.get("identity_sha256"):
        errors.append("IDENTITY_SHA256_MISMATCH")
    if event.get("source_profile_id") != _profile_id(record):
        errors.append("SOURCE_PROFILE_ID_MISMATCH")
    if _is_accepted_tiefling(record):
        errors.append("EXCLUSION_FORBIDDEN_ACCEPTED_TIEFLING")
    return errors


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return None


def select_current_exclusion(
    events: Iterable[Mapping[str, object]], record_id: str, mode: str
) -> ExclusionSelection:
    """Select the newest unrevoked event, rejecting ambiguous event histories."""
    relevant = [
        event for event in events
        if isinstance(event, Mapping) and event.get("record_id") == record_id and event.get("mode") == mode
    ]
    dated: list[tuple[datetime, Mapping[str, object]]] = []
    for event in relevant:
        timestamp = _timestamp(event.get("created_utc"))
        if timestamp is None:
            return ExclusionSelection(None, ("INVALID_EVENT_CREATED_UTC",))
        dated.append((timestamp, event))
    dated.sort(key=lambda item: item[0])
    for timestamp in {stamp for stamp, _ in dated}:
        simultaneous = [event for stamp, event in dated if stamp == timestamp]
        if len(simultaneous) > 1 and any(event.get("event_type") == "REVOCATION" for event in simultaneous):
            return ExclusionSelection(None, ("CONFLICTING_EXCLUSION_EVENTS",))

    normal_events = [event for _, event in dated if event.get("event_type", "EXCLUSION") == "EXCLUSION"]
    ids = [event.get("event_id") for event in normal_events]
    if len(ids) != len(set(ids)):
        return ExclusionSelection(None, ("DUPLICATE_EXCLUSION_EVENT_ID",))

    prior_ids: set[object] = set()
    revoked_ids: set[object] = set()
    for _, event in dated:
        if event.get("event_type", "EXCLUSION") == "EXCLUSION":
            prior_ids.add(event.get("event_id"))
            continue
        if event.get("event_type") != "REVOCATION":
            return ExclusionSelection(None, ("INVALID_EVENT_TYPE",))
        target = event.get("revokes_event_id")
        if target not in prior_ids:
            return ExclusionSelection(None, ("REVOCATION_WITHOUT_PRIOR_EVENT",))
        revoked_ids.add(target)

    active = [(stamp, event) for stamp, event in dated if event.get("event_type", "EXCLUSION") == "EXCLUSION" and event.get("event_id") not in revoked_ids]
    if not active:
        return ExclusionSelection(None)
    newest_stamp = active[-1][0]
    newest = [event for stamp, event in active if stamp == newest_stamp]
    if len(newest) != 1:
        return ExclusionSelection(None, ("CONFLICTING_EXCLUSION_EVENTS",))
    return ExclusionSelection(newest[0])
