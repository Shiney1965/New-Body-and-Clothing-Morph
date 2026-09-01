"""Deterministically generate the hash-locked release master ledger."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
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
from .exclusions import EXCLUSION_MODES, select_current_exclusion
from .identity import canonical_json, sha256_text
from .models import LedgerRecord, Observation
from .inventory import (
    IndependentInventories,
    InventoryIntegrityError,
    extract_independent_inventories,
)
from .reconcile import reconcile_observations
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
) -> tuple[LedgerRecord, ...]:
    """Attach only one valid selected event; invalid histories leave records untouched."""
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
            or item.event["mode"] not in EXCLUSION_MODES
            for item in claimed_history
        ):
            attached.append(record)
            continue
        modes = sorted({item.event["mode"] for item in claimed_history})
        selections = [
            select_current_exclusion(
                event_history, record.record_id, mode,
                ledger_record=record_data, evidence_hashes=verified_evidence,
            )
            for mode in modes
        ]
        selected = [selection.event for selection in selections if selection.event is not None]
        if len(selected) != 1 or any(selection.errors for selection in selections):
            attached.append(record)
            continue
        event = selected[0]
        assert event is not None
        selected_files = [item for item in claimed_history if item.event is event]
        if len(selected_files) != 1:
            attached.append(record)
            continue
        attached.append(replace(
            record,
            disposition="OUT_OF_SCOPE_WITH_PROOF",
            blocker_codes=(),
            release_blocking=False,
            next_admissible_action=str(event["next_project_if_reopened"]),
            terminal_exclusion=_terminal_exclusion_summary(selected_files[0]),
        ))
    return tuple(attached)


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
    ):
        values = audit[name]
        assert isinstance(values, list)
        lines.append(f"- **{name}:** {len(values)}")
    lines.extend(("", "This Markdown summary is derived from the generated JSON artifacts.", ""))
    return "\n".join(lines)


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
    observations: list[Observation] = []
    for input_ in verified_inputs:
        for observation in read_observations(input_):
            namespaced = replace(
                observation,
                observation_id=f"{input_.input_id}:{observation.observation_id}",
            )
            if namespaced.observation_kind == "PROTECTED_CONTROL":
                namespaced = _attach_protected_manifest(namespaced, inventories)
            observations.append(namespaced)
    reconciliation = reconcile_observations(observations)
    discovered_events = discover_exclusion_events(config.exclusion_events_dir)
    verified_exclusion_evidence = _local_verified_evidence_registry(config, verified_inputs)
    discovered_event_files = {
        item.relative_path: item.sha256 for item in discovered_events
    }
    records = _attach_terminal_exclusions(
        reconciliation.records,
        discovered_events,
        verified_exclusion_evidence,
    )
    supporting_input_ids = sorted(
        input_.input_id
        for input_ in verified_inputs
        if input_.kind.upper() == "SUPPORTING_EVIDENCE"
    )
    audit = build_completeness_audit(
        replace(reconciliation, records=records), inventories.to_audit_sets()
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
    ):
        audit[name] = sorted(audit[name])
    ledger = _ledger_payload(records, observations, verified_inputs)
    ledger_errors = validate_generated_ledger(
        ledger,
        verified_evidence=verified_exclusion_evidence,
        discovered_event_files=discovered_event_files,
    )
    if ledger_errors:
        raise ValueError("GENERATED_LEDGER_INVALID:" + ",".join(ledger_errors))
    manifest = _manifest_payload(
        verified_inputs,
        discovered_events=discovered_events,
        verified_evidence=verified_exclusion_evidence,
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
