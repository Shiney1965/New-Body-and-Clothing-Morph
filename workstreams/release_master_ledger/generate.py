"""Deterministically generate the hash-locked release master ledger."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .adapters import read_observations
from .audit import InventorySets, build_completeness_audit
from .configuration import (
    LocalConfiguration,
    VerifiedInput,
    load_local_configuration,
    verify_evidence_inputs,
)
from .models import LedgerRecord, Observation
from .reconcile import reconcile_observations


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


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest().upper()


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
            "input_observation_counts": _count(
                observation.input_id for observation in observations
            ),
            "observation_kind_counts": _count(
                observation.observation_kind for observation in observations
            ),
        },
        "blockers": _blockers(records),
        "records": [record.to_dict() for record in records],
    }
    return _stable_evidence_references(payload, verified_inputs)


def _manifest_payload(verified_inputs: list[VerifiedInput]) -> dict[str, object]:
    return {
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


def generate(config: LocalConfiguration) -> GenerationResult:
    """Hash inputs, adapt observations, reconcile, audit, and write all artifacts."""
    verified_inputs = verify_evidence_inputs(config)
    observations = [
        replace(
            observation,
            observation_id=f"{input_.input_id}:{observation.observation_id}",
        )
        for input_ in verified_inputs
        for observation in read_observations(input_)
    ]
    reconciliation = reconcile_observations(observations)
    supporting_input_ids = sorted(
        input_.input_id
        for input_ in verified_inputs
        if input_.kind.upper() == "SUPPORTING_EVIDENCE"
    )
    prior_evidence = frozenset(
        str(input_.path)
        for input_ in verified_inputs
        if input_.kind.upper() == "SUPPORTING_EVIDENCE"
    )
    packaged_records = frozenset(
        package_id
        for observation in observations
        if observation.observation_kind == "PACKAGE_EVIDENCE"
        for package_id in (observation.payload.get("shipped_package_id"),)
        if isinstance(package_id, str) and package_id != "UNKNOWN_SHIPPED_PACKAGE"
    )
    inventories = InventorySets(
        source_observations=frozenset(
            observation.observation_id for observation in observations
        ),
        prior_evidence=prior_evidence,
        packaged_records=packaged_records,
        required_source_profiles=frozenset(
            input_.input_id for input_ in verified_inputs
        ),
        complete_source_profiles=frozenset(),
    )
    audit = build_completeness_audit(reconciliation, inventories)
    audit["registered_inventories"] = {
        "packaged_records": sorted(packaged_records),
        "prior_evidence": [f"input:{input_id}" for input_id in supporting_input_ids],
    }
    audit = _stable_evidence_references(audit, verified_inputs)
    ledger = _ledger_payload(reconciliation.records, observations, verified_inputs)
    manifest = _manifest_payload(verified_inputs)

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
