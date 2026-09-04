"""Deterministically generate the hash-locked release master ledger."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import re
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .adapters import read_observations
from .audit import build_completeness_audit
from .configuration import (
    LocalConfiguration,
    VerifiedInput,
    load_local_configuration,
    verify_evidence_inputs,
)
from .exclusions import (
    RELEASE_MODES,
    ZERO_CLAIM_MODE_ROUTE,
    has_independent_claim,
    select_current_exclusion,
)
from .identity import canonical_json, sha256_text
from .models import LedgerRecord, Observation
from .inventory import (
    IndependentInventories,
    InventoryIntegrityError,
    extract_independent_inventories,
)
from .reconcile import ReconciliationResult, reconcile_observations
from .validation import validate_generated_ledger


LEDGER_NAME = "REMAINING_TARGET_MASTER_LEDGER.json"
MARKDOWN_NAME = "REMAINING_TARGET_MASTER_LEDGER.md"
AUDIT_NAME = "RELEASE_LEDGER_COMPLETENESS_AUDIT.json"
MANIFEST_NAME = "EVIDENCE_INPUT_MANIFEST.json"


@dataclass(frozen=True)
class GenerationResult:
    """Paths and exact byte hashes for one complete generation."""

    ledger_path: Path
    markdown_path: Path
    audit_path: Path
    manifest_path: Path
    ledger_sha256: str
    markdown_sha256: str
    audit_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class DiscoveredExclusionEvent:
    """One hash-locked event file parsed only after its bytes are digested."""

    relative_path: str
    sha256: str
    event: Mapping[str, object]


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


def discover_exclusion_events(directory: Path | None) -> tuple[DiscoveredExclusionEvent, ...]:
    """Read a local event history in normalized-path order without mutation."""
    if directory is None or not directory.is_dir():
        return ()
    root = directory.resolve(strict=True)
    candidates: list[tuple[str, Path]] = []
    for candidate in directory.rglob("*"):
        if not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        if root not in resolved.parents:
            raise ValueError(f"EXCLUSION_EVENT_OUTSIDE_CONFIGURED_DIRECTORY:{candidate}")
        relative = resolved.relative_to(root).as_posix()
        candidates.append((relative, resolved))
    discovered: list[DiscoveredExclusionEvent] = []
    for relative, path in sorted(candidates):
        content = path.read_bytes()
        digest = _sha256(content)
        try:
            event = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"EXCLUSION_EVENT_INVALID_JSON:{relative}:{digest}") from error
        if not isinstance(event, Mapping):
            raise ValueError(f"EXCLUSION_EVENT_INVALID_ROOT:{relative}:{digest}")
        discovered.append(DiscoveredExclusionEvent(relative, digest, event))
    return tuple(discovered)


def _local_verified_evidence_registry(
    config: LocalConfiguration, verified_inputs: Iterable[VerifiedInput],
) -> dict[str, str]:
    """Expose only configured, already-hashed local evidence by exact relative path."""
    if config.exclusion_events_dir is None:
        return {}
    local_root = config.exclusion_events_dir.parent.resolve(strict=False)
    registry: dict[str, str] = {}
    for input_ in verified_inputs:
        try:
            relative = input_.path.resolve(strict=False).relative_to(local_root).as_posix()
        except ValueError:
            continue
        registry[relative] = input_.actual_sha256
    return dict(sorted(registry.items()))


def _terminal_exclusion_summary(event_file: DiscoveredExclusionEvent) -> dict[str, object]:
    """Retain the full selected event and its immutable-file provenance."""
    event = event_file.event
    return {
        "event": event,
        "event_file": {
            "relative_path": event_file.relative_path,
            "sha256": event_file.sha256,
            "canonical_event_sha256": sha256_text(canonical_json(event)),
        },
    }


def _attach_terminal_exclusions(
    records: tuple[LedgerRecord, ...],
    events: Iterable[DiscoveredExclusionEvent],
    verified_evidence: Mapping[str, str],
    *,
    independent_provider_claims: Mapping[object, object],
    independent_package_claims: Mapping[object, object],
    provider_authority_present: bool,
    provider_authority_complete: bool,
    package_authority_present: bool,
    package_authority_complete: bool,
) -> tuple[LedgerRecord, ...]:
    """Attach valid per-mode events; any invalid sibling leaves the record untouched."""
    history = tuple(events)
    event_history = tuple(item.event for item in history)
    attached: list[LedgerRecord] = []
    for record in records:
        record_data = record.to_dict()
        claimed_history = tuple(
            item for item in history if item.event.get("record_id") == record.record_id
        )
        if any(
            not isinstance(item.event.get("mode"), str)
            or item.event["mode"] not in RELEASE_MODES
            for item in claimed_history
        ):
            attached.append(record)
            continue
        modes = tuple(
            mode for mode in RELEASE_MODES
            if any(item.event["mode"] == mode for item in claimed_history)
        )
        selections = {
            mode: select_current_exclusion(
                event_history, record.record_id, mode,
                ledger_record=record_data, evidence_hashes=verified_evidence,
                lifecycle="pre_attachment",
                independent_provider_claims=independent_provider_claims,
                independent_package_claims=independent_package_claims,
                provider_authority_present=provider_authority_present,
                provider_authority_complete=provider_authority_complete,
                package_authority_present=package_authority_present,
                package_authority_complete=package_authority_complete,
            )
            for mode in modes
        }
        if any(selection.errors for selection in selections.values()):
            attached.append(record)
            continue
        selected_events = {
            mode: selection.event
            for mode, selection in selections.items()
            if selection.event is not None
        }
        if set(selected_events) != set(modes):
            attached.append(record)
            continue
        selected_files: dict[str, DiscoveredExclusionEvent] = {}
        ambiguous = False
        for mode, event in selected_events.items():
            matches = [item for item in claimed_history if item.event is event]
            if len(matches) != 1:
                ambiguous = True
                break
            selected_files[mode] = matches[0]
        if ambiguous:
            attached.append(record)
            continue
        mode_scope = {
            mode: dict(record.mode_scope[mode]) for mode in RELEASE_MODES
        }
        terminal_exclusion = {
            mode: record.terminal_exclusion.get(mode) for mode in RELEASE_MODES
        }
        mode_routes = {
            mode: dict(record.mode_routes[mode]) for mode in RELEASE_MODES
        }
        for mode, event in selected_events.items():
            mode_scope[mode] = {
                "advertised": False,
                "terminal_state": "OUT_OF_SCOPE_WITH_PROOF",
            }
            terminal_exclusion[mode] = _terminal_exclusion_summary(
                selected_files[mode]
            )
            mode_routes[mode] = dict(ZERO_CLAIM_MODE_ROUTE)
        record_closed = all(
            mode_scope[mode]["terminal_state"] == "OUT_OF_SCOPE_WITH_PROOF"
            and terminal_exclusion[mode] is not None
            for mode in RELEASE_MODES
        )
        next_action = record.next_admissible_action
        if record_closed:
            next_action = str(selected_events[RELEASE_MODES[0]]["next_project_if_reopened"])
        attached.append(replace(
            record,
            mode_scope=mode_scope,
            mode_routes=mode_routes,
            terminal_exclusion=terminal_exclusion,
            disposition=(
                "OUT_OF_SCOPE_WITH_PROOF" if record_closed else record.disposition
            ),
            blocker_codes=() if record_closed else record.blocker_codes,
            release_blocking=False if record_closed else record.release_blocking,
            next_admissible_action=next_action,
        ))
    return tuple(attached)


def _resolve_independent_claims(
    claims: Mapping[object, object], reconciliation: ReconciliationResult,
) -> dict[object, object]:
    """Resolve raw observation source keys without reading reconciled route data."""
    resolved: dict[object, object] = {}
    record_ids = {record.record_id for record in reconciliation.records}
    for key, value in claims.items():
        resolved_key = key
        if (
            isinstance(key, tuple)
            and len(key) == 2
            and isinstance(key[0], str)
            and key[0].startswith("OBSERVATION:")
        ):
            observation_id = key[0].removeprefix("OBSERVATION:")
            record_id = reconciliation.observation_to_record.get(observation_id)
            resolved_key = (
                (record_id, key[1]) if record_id is not None else key[1]
            )
        elif (
            isinstance(key, tuple)
            and len(key) == 2
            and isinstance(key[0], str)
            and key[0].startswith("LEDGER_")
            and key[0] not in record_ids
        ):
            resolved_key = key[1]
        existing = resolved.get(resolved_key)
        if isinstance(existing, tuple) and isinstance(value, tuple):
            resolved[resolved_key] = tuple(sorted(set(existing) | set(value)))
        else:
            resolved[resolved_key] = value
    return resolved


def _write(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _sha256(content)


def _replace_evidence_references(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _replace_evidence_references(value[key], replacements)
            for key in sorted(value)
        }
    if isinstance(value, list | tuple):
        return [_replace_evidence_references(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def _stable_evidence_references(
    value: Any, verified_inputs: Iterable[VerifiedInput]
) -> Any:
    inputs = tuple(verified_inputs)
    replacements = {
        str(input_.path): f"input:{input_.input_id}" for input_ in inputs
    }
    replacements.update({
        str(input_.path.resolve()): f"input:{input_.input_id}"
        for input_ in inputs
    })
    return _replace_evidence_references(value, replacements)


def _count(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _blocker_owner(code: str) -> str:
    if "PERMISSION" in code:
        return "PERMISSION_REVIEW_OWNER"
    if "GAMEPLAY" in code:
        return "GAMEPLAY_ACCEPTANCE_OWNER"
    if "ROUTE" in code or "VR_" in code or "COMPONENT" in code:
        return "SOURCE_ROUTE_OWNER"
    if "IDENTITY" in code or "SOURCE_" in code:
        return "SOURCE_INVENTORY_OWNER"
    return "RELEASE_LEDGER_OWNER"


def _blockers(records: Iterable[LedgerRecord]) -> list[dict[str, object]]:
    by_code: dict[str, list[LedgerRecord]] = {}
    for record in records:
        for code in record.blocker_codes:
            by_code.setdefault(code, []).append(record)
    return [
        {
            "code": code,
            "evidence_pointers": sorted({
                path for record in by_code[code] for path in record.evidence_paths
            }),
            "next_admissible_action": sorted({
                record.next_admissible_action for record in by_code[code]
            })[0],
            "owner": _blocker_owner(code),
            "record_ids": sorted(record.record_id for record in by_code[code]),
            "release_blocking": any(record.release_blocking for record in by_code[code]),
        }
        for code in sorted(by_code)
    ]


def _ledger_payload(
    records: tuple[LedgerRecord, ...],
    observations: list[Observation],
    verified_inputs: list[VerifiedInput],
) -> dict[str, object]:
    input_observation_counts = {input_.input_id: 0 for input_ in verified_inputs}
    input_observation_counts.update(_count(
        observation.input_id for observation in observations
    ))
    payload = {
        "schema_version": 1,
        "summary": {
            "input_count": len(verified_inputs),
            "observation_count": len(observations),
            "record_count": len(records),
            "release_blocking_record_count": sum(
                record.release_blocking for record in records
            ),
            "disposition_counts": _count(record.disposition for record in records),
            "input_observation_counts": dict(sorted(input_observation_counts.items())),
            "input_kind_counts": _count(input_.kind for input_ in verified_inputs),
            "observation_kind_counts": _count(
                observation.observation_kind for observation in observations
            ),
        },
        "blockers": _blockers(records),
        "records": [record.to_dict() for record in records],
    }
    return _stable_evidence_references(payload, verified_inputs)


def _manifest_payload(
    verified_inputs: list[VerifiedInput], *,
    discovered_events: Iterable[DiscoveredExclusionEvent] = (),
    verified_evidence: Mapping[str, str] = {},
    independent_provider_claims: Mapping[object, object] | None = None,
    independent_package_claims: Mapping[object, object] | None = None,
    provider_authority_present: bool | None = None,
    provider_authority_complete: bool | None = None,
    package_authority_present: bool | None = None,
    package_authority_complete: bool | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "inputs": [
            {
                "actual_sha256": input_.actual_sha256,
                "bytes": input_.bytes,
                "expected_sha256": input_.expected_sha256,
                "input_id": input_.input_id,
                "kind": input_.kind,
                "path": str(input_.path.resolve()),
            }
            for input_ in sorted(verified_inputs, key=lambda item: item.input_id)
        ]
    }
    events = tuple(discovered_events)
    if events:
        event_files = [
            {"relative_path": item.relative_path, "sha256": item.sha256}
            for item in events
        ]
        payload["exclusion_event_files"] = event_files
        payload["terminal_exclusion_validation_trace"] = {
            "discovered_event_files": {
                item["relative_path"]: item["sha256"] for item in event_files
            },
            "verified_evidence": dict(sorted(verified_evidence.items())),
            "verified_zero_claim_modes": sorted({
                f"{item.event['record_id']}:{item.event['mode']}"
                for item in events
                if isinstance(item.event.get("record_id"), str)
                and item.event.get("mode") in RELEASE_MODES
                and isinstance(independent_provider_claims, Mapping)
                and isinstance(independent_package_claims, Mapping)
                and provider_authority_present is True
                and provider_authority_complete is True
                and package_authority_present is True
                and package_authority_complete is True
                and not has_independent_claim(
                    independent_provider_claims,
                    str(item.event["record_id"]), str(item.event["mode"]),
                )
                and not has_independent_claim(
                    independent_package_claims,
                    str(item.event["record_id"]), str(item.event["mode"]),
                )
            }),
        }
    return payload


def _markdown(ledger: Mapping[str, object], audit: Mapping[str, object]) -> str:
    summary = ledger["summary"]
    assert isinstance(summary, Mapping)
    lines = [
        "# Remaining Target Master Ledger",
        "",
        f"- **Ledger records:** {summary['record_count']}",
        f"- **Source observations:** {summary['observation_count']}",
        f"- **Release-blocking records:** {summary['release_blocking_record_count']}",
        f"- **Source complete:** `{str(audit['source_complete']).lower()}`",
        f"- **Release complete:** `{str(audit['release_complete']).lower()}`",
        "",
        "## Anti-omission audit",
        "",
    ]
    for name in (
        "missing_from_ledger",
        "duplicate_identity",
        "unreferenced_prior_evidence",
        "packaged_without_ledger",
        "ledger_without_source",
        "in_scope_nonterminal",
        "excluded_with_proof",
        "exclusion_validation_failures",
        "excluded_but_packaged",
    ):
        values = audit[name]
        assert isinstance(values, list)
        lines.append(f"- **{name}:** {len(values)}")
    lines.extend(("", "This Markdown summary is derived from the generated JSON artifacts.", ""))
    return "\n".join(lines)




_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_GR2_RE = re.compile(r"[A-Za-z0-9_.-]+\.GR2")
_GARMENT_RECORD_KINDS = frozenset({
    "COVERAGE_RECORD",
    "TRUE_UNDERWEAR_RECORD",
    "VANITYBODY_RECORD",
    "BCBSCANTILY_RECORD",
})


def _named_target_join_tokens(observation: Observation) -> set[str]:
    """Extract exact, evidence-present join tokens; never invent meshes."""
    tokens: set[str] = set()
    raw = observation.raw_evidence if isinstance(observation.raw_evidence, Mapping) else {}
    for key in ("item", "item_uuid", "stats_entry", "garment_family", "name", "display_name"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            tokens.add(value)
            tokens.add(value.lower())
    required_route = raw.get("required_route")
    if isinstance(required_route, Mapping):
        for key in ("original_vr", "target_vr", "source_file"):
            value = required_route.get(key)
            if isinstance(value, str) and value:
                tokens.add(value)
                tokens.add(value.lower())
                normalized = value.replace("\\", "/")
                if "/" in normalized:
                    tokens.add(normalized.rsplit("/", 1)[-1])
    root = observation.identity_fields.root_template_uuid
    if isinstance(root, str) and root and not root.startswith("UNKNOWN_"):
        tokens.add(root)
        tokens.add(root.lower())
    text_blobs: list[str] = []
    for value in raw.values():
        if isinstance(value, str):
            text_blobs.append(value)
    pointer = raw.get("evidence_pointer")
    if isinstance(pointer, str) and pointer:
        try:
            text_blobs.append(Path(pointer).read_text(encoding="utf-8"))
        except OSError:
            pass
    for blob in text_blobs:
        for match in _UUID_RE.findall(blob):
            tokens.add(match)
            tokens.add(match.lower())
        for match in _GR2_RE.findall(blob):
            tokens.add(match)
    return {token for token in tokens if token}


def _garment_join_tokens(observation: Observation) -> set[str]:
    tokens: set[str] = set()
    fields = observation.identity_fields
    for value in (
        fields.root_template_uuid,
        fields.stats_entry,
        *fields.ordered_source_vrs,
    ):
        if isinstance(value, str) and value and not value.startswith("UNKNOWN_"):
            tokens.add(value)
            tokens.add(value.lower())
    classification = observation.classification if isinstance(observation.classification, Mapping) else {}
    family = classification.get("garment_family")
    if isinstance(family, str) and family and family != "UNKNOWN_GARMENT_FAMILY":
        tokens.add(family)
        tokens.add(family.lower())
    payload = observation.payload if isinstance(observation.payload, Mapping) else {}
    source_route = payload.get("source_route") if isinstance(payload.get("source_route"), Mapping) else {}
    for path_value in source_route.get("ordered_paths") or ():
        if isinstance(path_value, str) and path_value and not path_value.startswith("UNKNOWN_"):
            tokens.add(path_value)
            tokens.add(path_value.replace("\\", "/").rsplit("/", 1)[-1])
    raw = observation.raw_evidence if isinstance(observation.raw_evidence, Mapping) else {}
    path_value = raw.get("source_visual_resource_path")
    if isinstance(path_value, str) and path_value:
        tokens.add(path_value)
        tokens.add(path_value.replace("\\", "/").rsplit("/", 1)[-1])
    vr = raw.get("source_visual_resource_uuid")
    if isinstance(vr, str) and vr:
        tokens.add(vr)
        tokens.add(vr.lower())
    return tokens


def attach_named_target_evidence(
    records: tuple[LedgerRecord, ...],
    observations: list[Observation],
    observation_to_record: Mapping[str, str],
) -> tuple[tuple[LedgerRecord, ...], dict[str, str]]:
    """Join named-target evidence onto existing garment records without inventing meshes.

    Hard garments stay in-scope outstanding: this only attaches evidence paths/hashes and
    maps the named-target observation onto matched garment records for audit sourcing.
    Unmatched named targets remain provisional ledger rows (still independently inventoried).
    """
    named = [
        observation for observation in observations
        if observation.observation_kind == "NAMED_TARGET_EVIDENCE"
    ]
    if not named:
        return records, dict(observation_to_record)

    garments_by_record: dict[str, list[Observation]] = {}
    for observation in observations:
        if observation.observation_kind not in _GARMENT_RECORD_KINDS:
            continue
        record_id = observation_to_record.get(observation.observation_id)
        if record_id is None:
            continue
        garments_by_record.setdefault(record_id, []).append(observation)

    mapping = dict(observation_to_record)
    attachments: dict[str, list[Observation]] = {}
    joined_named_ids: set[str] = set()
    for named_observation in named:
        tokens = _named_target_join_tokens(named_observation)
        if not tokens:
            continue
        item_names = {
            token for token in tokens
            if isinstance(token, str)
            and not _UUID_RE.fullmatch(token)
            and not token.endswith(".GR2")
            and not token.startswith("UNKNOWN_")
            and "/" not in token
            and "\\" not in token
        }
        matched_record_ids: list[str] = []
        for record_id, garment_observations in garments_by_record.items():
            garment_tokens: set[str] = set()
            garment_stats: set[str] = set()
            garment_families: set[str] = set()
            garment_roots: set[str] = set()
            garment_vrs: set[str] = set()
            for garment in garment_observations:
                garment_tokens.update(_garment_join_tokens(garment))
                garment_stats.add(garment.identity_fields.stats_entry)
                family = (
                    garment.classification.get("garment_family")
                    if isinstance(garment.classification, Mapping) else None
                )
                if isinstance(family, str):
                    garment_families.add(family)
                root = garment.identity_fields.root_template_uuid
                if isinstance(root, str) and root:
                    garment_roots.add(root.lower())
                for vr in garment.identity_fields.ordered_source_vrs:
                    if isinstance(vr, str) and vr:
                        garment_vrs.add(vr.lower())
                raw = garment.raw_evidence if isinstance(garment.raw_evidence, Mapping) else {}
                raw_vr = raw.get("source_visual_resource_uuid")
                if isinstance(raw_vr, str) and raw_vr:
                    garment_vrs.add(raw_vr.lower())
            overlap = tokens & garment_tokens
            if not overlap:
                continue
            name_hit = bool(item_names & garment_stats) or bool(item_names & garment_families)
            vr_or_mesh_hit = any(
                (token.endswith(".GR2") or (_UUID_RE.fullmatch(token) and token.lower() in garment_vrs))
                for token in overlap
            )
            root_only = bool(overlap) and all(
                _UUID_RE.fullmatch(token) and token.lower() in garment_roots
                for token in overlap
            )
            if root_only and not name_hit and not vr_or_mesh_hit:
                continue
            if item_names and not (name_hit or vr_or_mesh_hit or not root_only):
                # Keep exact garment-name preference when present.
                if not name_hit and not vr_or_mesh_hit:
                    continue
            matched_record_ids.append(record_id)
        if not matched_record_ids:
            continue
        joined_named_ids.add(named_observation.observation_id)
        for record_id in matched_record_ids:
            attachments.setdefault(record_id, []).append(named_observation)
            mapping[named_observation.observation_id] = record_id

    if not attachments:
        return records, mapping

    updated: list[LedgerRecord] = []
    for record in records:
        mapped_obs = [
            observation_id for observation_id, record_id in mapping.items()
            if record_id == record.record_id
        ]
        original_obs = [
            observation_id for observation_id, record_id in observation_to_record.items()
            if record_id == record.record_id
        ]
        # Drop provisional named-target-only records once their observation joined elsewhere.
        if (
            original_obs
            and set(original_obs) <= joined_named_ids
            and record.record_id not in attachments
        ):
            continue
        named_list = attachments.get(record.record_id)
        if not named_list:
            updated.append(record)
            continue
        evidence_paths = tuple(dict.fromkeys((
            *record.evidence_paths,
            *(path for named_obs in named_list for path in named_obs.evidence_pointers),
        )))
        evidence_hashes = tuple(dict.fromkeys((
            *record.evidence_hashes,
            *(named_obs.input_sha256 for named_obs in named_list),
        )))
        updated.append(replace(
            record,
            evidence_paths=evidence_paths,
            evidence_hashes=evidence_hashes,
        ))
    return tuple(updated), mapping



@dataclass(frozen=True)
class SupportingEvidenceIndex:
    input_id: str
    evidence_path: str
    wearable_identities: frozenset[str] = frozenset()
    underwear_keys: frozenset[tuple[str, str, str]] = frozenset()
    root_uuids: frozenset[str] = frozenset()
    item_uuids: frozenset[str] = frozenset()
    module_uuids: frozenset[str] = frozenset()


def _records_payload(payload: object, *keys: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def _class_ledger_item_uuids(payload: object) -> set[str]:
    values: set[str] = set()
    if not isinstance(payload, Mapping):
        return values
    for key in ("protected_item_uuids", "negative_item_uuids", "deferred_item_uuids"):
        raw = payload.get(key)
        if isinstance(raw, list):
            values.update(item for item in raw if isinstance(item, str) and item)
    for row in _records_payload(payload, "random_test_queue", "resolved_additional_protections"):
        item_uuid = row.get("item_uuid")
        if isinstance(item_uuid, str) and item_uuid:
            values.add(item_uuid)
    for cls in _records_payload(payload, "classes"):
        for member in cls.get("members") or []:
            if isinstance(member, str) and member:
                values.add(member)
            elif isinstance(member, Mapping):
                item_uuid = member.get("item_uuid")
                if isinstance(item_uuid, str) and item_uuid:
                    values.add(item_uuid)
        for key in ("positive_gameplay_anchor", "protected_same_class_control"):
            node = cls.get(key)
            if isinstance(node, Mapping):
                item_uuid = node.get("item_uuid")
                if isinstance(item_uuid, str) and item_uuid:
                    values.add(item_uuid)
    bard = payload.get("bard_evidence")
    if isinstance(bard, Mapping):
        item_uuid = bard.get("item_uuid")
        if isinstance(item_uuid, str) and item_uuid:
            values.add(item_uuid)
    return values


def _module_uuids_from_payload(input_id: str, payload: object) -> set[str]:
    values: set[str] = set()
    if input_id == "source_profile_inventory" and isinstance(payload, Mapping):
        for module in payload.get("modules") or []:
            if isinstance(module, Mapping):
                uuid = module.get("uuid")
                if isinstance(uuid, str) and uuid:
                    values.add(uuid)
        return values
    for row in _records_payload(payload):
        contract = row.get("contract") if isinstance(row.get("contract"), Mapping) else row
        if not isinstance(contract, Mapping):
            continue
        module = contract.get("module")
        if isinstance(module, Mapping):
            uuid = module.get("uuid")
            if isinstance(uuid, str) and uuid:
                values.add(uuid)
    return values


def _build_supporting_evidence_indexes(
    verified_inputs: list[VerifiedInput],
) -> list[SupportingEvidenceIndex]:
    """Index SUPPORTING_EVIDENCE inputs by exact wearable/item/module/route identity."""
    indexes: list[SupportingEvidenceIndex] = []
    for input_ in verified_inputs:
        if input_.kind.upper() != "SUPPORTING_EVIDENCE":
            continue
        if "protected_hash_manifest" in input_.input_id.lower():
            continue  # attached via protected-manifest relations
        try:
            payload = json.loads(Path(input_.path).read_bytes().decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InventoryIntegrityError(f"SUPPORTING_EVIDENCE_UNREADABLE:{input_.input_id}") from error
        wearable_identities: set[str] = set()
        underwear_keys: set[tuple[str, str, str]] = set()
        root_uuids: set[str] = set()
        item_uuids: set[str] = set()
        module_uuids: set[str] = set()
        input_id = input_.input_id
        if input_id == "coverage_raw_registry_scoped":
            for row in _records_payload(payload):
                identity = row.get("identity")
                if isinstance(identity, str) and identity:
                    wearable_identities.add(identity)
        elif input_id == "true_underwear_route_audit":
            for row in _records_payload(payload, "audits"):
                stats = row.get("stats_entry")
                root = row.get("root_template_uuid")
                source_vr = row.get("source_vr") or row.get("source_visual_resource_uuid") or "MISSING"
                if isinstance(stats, str) and isinstance(root, str) and isinstance(source_vr, str):
                    underwear_keys.add((stats, root, source_vr))
        elif input_id == "vanitybody_route_protection":
            for row in _records_payload(payload, "records"):
                root = row.get("root_uuid") or row.get("root_template_uuid")
                if isinstance(root, str) and root:
                    root_uuids.add(root)
        elif input_id == "bcbscantily_class_ledger":
            item_uuids = _class_ledger_item_uuids(payload)
        elif input_id in {"source_profile_census_candidates", "source_profile_inventory", "base_game_aggregate_census"}:
            module_uuids = _module_uuids_from_payload(input_id, payload)
        else:
            continue
        indexes.append(SupportingEvidenceIndex(
            input_id=input_id,
            evidence_path=str(input_.path),
            wearable_identities=frozenset(wearable_identities),
            underwear_keys=frozenset(underwear_keys),
            root_uuids=frozenset(root_uuids),
            item_uuids=frozenset(item_uuids),
            module_uuids=frozenset(module_uuids),
        ))
    return indexes


def _observation_module_uuid(observation: Observation) -> str | None:
    module_uuid = observation.identity_fields.source_module_uuid
    if isinstance(module_uuid, str) and module_uuid and not module_uuid.startswith("UNKNOWN"):
        return module_uuid
    payload_module = observation.payload.get("source_module") if isinstance(observation.payload, Mapping) else None
    if isinstance(payload_module, Mapping):
        uuid = payload_module.get("uuid")
        if isinstance(uuid, str) and uuid and not uuid.startswith("UNKNOWN"):
            return uuid
    raw = observation.raw_evidence if isinstance(observation.raw_evidence, Mapping) else {}
    for key in ("mod_uuid", "module_uuid", "uuid"):
        uuid = raw.get(key)
        if isinstance(uuid, str) and uuid and not uuid.startswith("UNKNOWN"):
            return uuid
    flag = raw.get("flag")
    if isinstance(flag, Mapping):
        uuid = flag.get("mod_uuid")
        if isinstance(uuid, str) and uuid:
            return uuid
    return None


def _observation_wearable_identity(observation: Observation) -> str | None:
    if observation.observation_kind != "COVERAGE_RECORD":
        return None
    # namespaced id is "{input_id}:{identity}"
    oid = observation.observation_id
    prefix = f"{observation.input_id}:"
    if oid.startswith(prefix):
        return oid[len(prefix):]
    raw = observation.raw_evidence if isinstance(observation.raw_evidence, Mapping) else {}
    identity = raw.get("identity")
    if isinstance(identity, str) and identity:
        return identity
    return None


def _observation_underwear_key(observation: Observation) -> tuple[str, str, str] | None:
    if observation.observation_kind != "TRUE_UNDERWEAR_RECORD":
        return None
    stats = observation.identity_fields.stats_entry
    root = observation.identity_fields.root_template_uuid
    vrs = observation.identity_fields.ordered_source_vrs
    source_vr = vrs[0] if vrs else "MISSING"
    # Strip observation namespacing suffixes from stats if present.
    if "__OBSERVATION__" in stats:
        stats = stats.split("__OBSERVATION__", 1)[0]
    if isinstance(stats, str) and isinstance(root, str) and isinstance(source_vr, str):
        return (stats, root, source_vr)
    return None


def _observation_matches_supporting(observation: Observation, index: SupportingEvidenceIndex) -> bool:
    if index.wearable_identities:
        identity = _observation_wearable_identity(observation)
        return bool(identity and identity in index.wearable_identities)
    if index.underwear_keys:
        key = _observation_underwear_key(observation)
        return bool(key and key in index.underwear_keys)
    if index.root_uuids:
        if observation.observation_kind != "VANITYBODY_RECORD":
            return False
        return observation.identity_fields.root_template_uuid in index.root_uuids
    if index.item_uuids:
        if observation.observation_kind != "BCBSCANTILY_RECORD":
            return False
        candidates = {
            observation.identity_fields.root_template_uuid,
            observation.observation_id.split(":", 1)[-1],
        }
        raw = observation.raw_evidence if isinstance(observation.raw_evidence, Mapping) else {}
        item_uuid = raw.get("item_uuid")
        if isinstance(item_uuid, str):
            candidates.add(item_uuid)
        return bool(candidates & index.item_uuids)
    if index.module_uuids:
        # Module supporting evidence attaches to garment/permission/package rows only ?
        # never blind-fan onto protected controls or provisional named targets.
        if observation.observation_kind in {
            "PROTECTED_CONTROL",
            "NAMED_TARGET_EVIDENCE",
            "PROTECTED_HASH_MANIFEST",
        }:
            return False
        module_uuid = _observation_module_uuid(observation)
        return bool(module_uuid and module_uuid in index.module_uuids)
    return False


def _attach_supporting_evidence(
    observation: Observation, indexes: list[SupportingEvidenceIndex]
) -> Observation:
    """Attach supporting evidence_path by exact wearable/item/module/route identity only."""
    matched_paths = [
        index.evidence_path
        for index in indexes
        if _observation_matches_supporting(observation, index)
    ]
    if not matched_paths:
        return observation
    evidence_pointers = tuple(dict.fromkeys((*observation.evidence_pointers, *matched_paths)))
    payload = dict(observation.payload)
    payload["evidence_pointers"] = evidence_pointers
    return replace(
        observation,
        evidence_files=evidence_pointers,
        payload=payload,
    )


def _attach_protected_manifest(
    observation: Observation, inventories: IndependentInventories
) -> Observation:
    registry_ids = observation.protected_relations.get("registry_ids")
    if not isinstance(registry_ids, list) or len(registry_ids) != 1:
        raise InventoryIntegrityError("PROTECTED_OBSERVATION_REGISTRY_ID_INVALID")
    registry_id = registry_ids[0]
    if not isinstance(registry_id, str) or registry_id not in inventories.protected_manifest_relations:
        raise InventoryIntegrityError(f"PROTECTED_OBSERVATION_MANIFEST_RELATION_MISSING:{registry_id}")
    relation = inventories.protected_manifest_relations[registry_id]
    payload = dict(observation.payload)
    protected_relations = dict(observation.protected_relations)
    protected_relations["hash_manifest_entries"] = [{
        "bytes": relation.bytes,
        "input_id": relation.manifest_input_id,
        "input_sha256": relation.manifest_input_sha256,
        "protected_path": relation.protected_path,
        "registry_id": relation.registry_id,
        "sha256": relation.sha256,
    }]
    evidence_pointers = tuple(dict.fromkeys((
        *observation.evidence_pointers,
        relation.manifest_evidence_path,
    )))
    payload["protected_relations"] = protected_relations
    payload["evidence_pointers"] = evidence_pointers
    return replace(
        observation,
        evidence_files=evidence_pointers,
        payload=payload,
    )


def generate(config: LocalConfiguration) -> GenerationResult:
    """Hash inputs, adapt observations, reconcile, audit, and write all artifacts."""
    verified_inputs = verify_evidence_inputs(config)
    inventories = extract_independent_inventories(verified_inputs)
    supporting_indexes = _build_supporting_evidence_indexes(verified_inputs)
    observations: list[Observation] = []
    for input_ in verified_inputs:
        for observation in read_observations(input_):
            namespaced = replace(
                observation,
                observation_id=f"{input_.input_id}:{observation.observation_id}",
            )
            if namespaced.observation_kind == "PROTECTED_CONTROL":
                namespaced = _attach_protected_manifest(namespaced, inventories)
            namespaced = _attach_supporting_evidence(namespaced, supporting_indexes)
            observations.append(namespaced)
    reconciliation = reconcile_observations(observations)
    joined_records, joined_observation_to_record = attach_named_target_evidence(
        reconciliation.records, observations, reconciliation.observation_to_record,
    )
    reconciliation = replace(
        reconciliation,
        records=joined_records,
        observation_to_record=joined_observation_to_record,
    )
    discovered_events = discover_exclusion_events(config.exclusion_events_dir)
    verified_exclusion_evidence = _local_verified_evidence_registry(config, verified_inputs)
    discovered_event_files = {
        item.relative_path: item.sha256 for item in discovered_events
    }
    independent_provider_claims = _resolve_independent_claims(
        inventories.provider_claims, reconciliation,
    )
    independent_package_claims = _resolve_independent_claims(
        inventories.package_claims, reconciliation,
    )
    records = _attach_terminal_exclusions(
        reconciliation.records,
        discovered_events,
        verified_exclusion_evidence,
        independent_provider_claims=independent_provider_claims,
        independent_package_claims=independent_package_claims,
        provider_authority_present=inventories.provider_authority_present,
        provider_authority_complete=inventories.provider_authority_complete,
        package_authority_present=inventories.package_authority_present,
        package_authority_complete=inventories.package_authority_complete,
    )
    supporting_input_ids = sorted(
        input_.input_id
        for input_ in verified_inputs
        if str(input_.path) in inventories.prior_evidence
    )
    audit = build_completeness_audit(
        replace(reconciliation, records=records),
        inventories.to_audit_sets(),
        exclusion_events=tuple(item.event for item in discovered_events),
        verified_evidence=verified_exclusion_evidence,
        discovered_event_files=discovered_event_files,
        independent_provider_claims=independent_provider_claims,
        independent_package_claims=independent_package_claims,
        provider_authority_present=inventories.provider_authority_present,
        provider_authority_complete=inventories.provider_authority_complete,
        package_authority_present=inventories.package_authority_present,
        package_authority_complete=inventories.package_authority_complete,
    )
    audit["registered_inventories"] = {
        "packaged_records": sorted(inventories.packaged_records),
        "prior_evidence": [f"input:{input_id}" for input_id in supporting_input_ids],
        "source_observations": sorted(inventories.source_observations),
    }
    audit = _stable_evidence_references(audit, verified_inputs)
    for name in (
        "missing_from_ledger", "duplicate_identity", "unreferenced_prior_evidence",
        "packaged_without_ledger", "ledger_without_source", "in_scope_nonterminal",
        "excluded_modes_with_proof", "excluded_with_proof",
        "exclusion_validation_failures", "exclusion_history_failures",
        "excluded_but_packaged",
    ):
        audit[name] = sorted(audit[name])
    ledger = _ledger_payload(records, observations, verified_inputs)
    ledger_errors = validate_generated_ledger(
        ledger,
        verified_evidence=verified_exclusion_evidence,
        discovered_event_files=discovered_event_files,
        independent_provider_claims=independent_provider_claims,
        independent_package_claims=independent_package_claims,
        provider_authority_present=inventories.provider_authority_present,
        provider_authority_complete=inventories.provider_authority_complete,
        package_authority_present=inventories.package_authority_present,
        package_authority_complete=inventories.package_authority_complete,
    )
    if ledger_errors:
        raise ValueError("GENERATED_LEDGER_INVALID:" + ",".join(ledger_errors))
    manifest = _manifest_payload(
        verified_inputs,
        discovered_events=discovered_events,
        verified_evidence=verified_exclusion_evidence,
        independent_provider_claims=independent_provider_claims,
        independent_package_claims=independent_package_claims,
        provider_authority_present=inventories.provider_authority_present,
        provider_authority_complete=inventories.provider_authority_complete,
        package_authority_present=inventories.package_authority_present,
        package_authority_complete=inventories.package_authority_complete,
    )

    output_dir = config.output_path.parent
    ledger_path = output_dir / LEDGER_NAME
    markdown_path = output_dir / MARKDOWN_NAME
    audit_path = output_dir / AUDIT_NAME
    manifest_path = output_dir / MANIFEST_NAME
    ledger_sha256 = _write(ledger_path, _json_bytes(ledger))
    audit_sha256 = _write(audit_path, _json_bytes(audit))
    manifest_sha256 = _write(manifest_path, _json_bytes(manifest))
    markdown_sha256 = _write(markdown_path, _markdown(ledger, audit).encode("utf-8"))
    return GenerationResult(
        ledger_path=ledger_path,
        markdown_path=markdown_path,
        audit_path=audit_path,
        manifest_path=manifest_path,
        ledger_sha256=ledger_sha256,
        markdown_sha256=markdown_sha256,
        audit_sha256=audit_sha256,
        manifest_sha256=manifest_sha256,
    )


def main() -> int:
    result = generate(load_local_configuration())
    print(f"ledger={result.ledger_path} sha256={result.ledger_sha256}")
    print(f"audit={result.audit_path} sha256={result.audit_sha256}")
    print(f"manifest={result.manifest_path} sha256={result.manifest_sha256}")
    print(f"markdown={result.markdown_path} sha256={result.markdown_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
