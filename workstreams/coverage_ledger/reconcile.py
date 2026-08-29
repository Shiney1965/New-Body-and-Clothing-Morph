"""Evidence precedence and conflict reporting for existing ClothMorph work."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable

from .models import GarmentRecord


@dataclass(frozen=True)
class Evidence:
    path: str
    kind: str
    date: str
    root_template_uuids: set[str]
    identity: str | None = None
    body_mode: str | None = None
    route_role: str | None = None
    package_profile_identity: dict[str, str] | None = None
    artifact_sha256: str | None = None


@dataclass
class ReconciliationResult:
    records: list[GarmentRecord]
    conflicts: list[dict[str, object]]


OUTCOMES = {
    "GAMEPLAY_PASS": (4, "ACCEPTED / PROTECT"),
    "CONFIRMED_DEFECT": (4, "CONFIRMED DEFECT / CORRECT"),
    "MISSING_ROUTE": (3, "MISSING ROUTE / BUILD"),
    "READY_FOR_TEST": (2, "READY FOR TEST"),
    "DEFERRED": (1, "DEFERRED WITH CAUSE"),
    "OUT_OF_SCOPE": (1, "OUT OF SCOPE"),
}


def reconcile(records: Iterable[GarmentRecord], evidence_sources: Iterable[Evidence]) -> ReconciliationResult:
    evidence = list(evidence_sources)
    output: list[GarmentRecord] = []
    conflicts: list[dict[str, object]] = []
    for original in records:
        record = deepcopy(original)
        root_annotations = [item for item in evidence if record.root_template_uuid in item.root_template_uuids and item.identity is None]
        matched = [item for item in evidence if item.identity == record.identity]
        if not matched:
            if root_annotations:
                record.reconciliation = {"root_annotations": [item.path for item in root_annotations]}
            output.append(record)
            continue
        ranked = sorted(matched, key=lambda item: (OUTCOMES[item.kind][0], item.date), reverse=True)
        top = ranked[0]
        highest = OUTCOMES[top.kind][0]
        contemporaneous = [
            item for item in ranked
            if OUTCOMES[item.kind][0] == highest and item.date == top.date
        ]
        outcomes = {OUTCOMES[item.kind][1] for item in contemporaneous}
        record.evidence.extend(item.path for item in [*root_annotations, *ranked] if item.path not in record.evidence)
        if len(outcomes) > 1:
            record.disposition = "DEFERRED WITH CAUSE"
            record.reconciliation = {
                "controlling_evidence": None,
                "conflict": "same-strength contemporaneous evidence has incompatible outcomes",
                "evidence": [item.path for item in contemporaneous],
            }
            conflicts.append({
                "identity": record.identity,
                "root_template_uuid": record.root_template_uuid,
                "evidence": [item.path for item in contemporaneous],
                "reason": "same-strength contemporaneous evidence has incompatible outcomes",
            })
        else:
            record.disposition = OUTCOMES[top.kind][1]
            record.reconciliation = {
                "controlling_evidence": top.path,
                "kind": top.kind,
                "date": top.date,
                "superseded_evidence": [item.path for item in ranked[1:]],
                "root_annotations": [item.path for item in root_annotations],
            }
        output.append(record)
    return ReconciliationResult(output, conflicts)
