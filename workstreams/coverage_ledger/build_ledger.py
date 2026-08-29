"""Build a deterministic, read-only SCO/Sindae coverage ledger."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from .models import GarmentRecord
from .configuration import LocalConfiguration, load_local_configuration, validate_generated_outputs
from .reconcile import Evidence, reconcile
from .scan_sources import SourceModule, scan_source


def _route_gaps(record: GarmentRecord) -> list[str]:
    gaps: list[str] = []
    if record.effective_slot == "UNRESOLVED":
        gaps.append("effective equipment slot")
    if record.source_visual_resource_path is None:
        gaps.append("source VisualResource path")
    if record.body_family != "HUM_F":
        gaps.append("supported HUM_F body family")
    if record.topology_family == "UNASSESSED":
        gaps.append("topology/signature family")
    if record.component_contract == "UNASSESSED":
        gaps.append("component contract")
    for mode in ("Vanilla", "SBBF", "BCB"):
        route = record.routes.get(mode)
        if route is None or not route.visual_resource_uuid or not route.path or not route.mesh_sha256 or not route.provenance:
            gaps.append(f"{mode} target VR/path/hash/provenance")
    if not record.protected_controls:
        gaps.append("protected-control evidence")
    if not record.package_ownership:
        gaps.append("candidate package ownership")
    if not record.candidate_profile or not record.candidate_profile.get("profile_id") or not record.candidate_profile.get("dependencies"):
        gaps.append("dependency-compatible profile identity")
    if not record.readiness_evidence:
        gaps.append("source-to-stage-to-fresh-extraction manifest evidence")
    if record.known_defect is None:
        gaps.append("defect/control classification")
    return gaps


def build_master_ledger(raw_records: Iterable[GarmentRecord], evidence: Iterable[Evidence]) -> list[GarmentRecord]:
    reconciled = reconcile(raw_records, evidence).records
    for record in reconciled:
        if record.disposition in {"ACCEPTED / PROTECT", "OUT OF SCOPE"}:
            continue
        if record.effective_slot == "UNRESOLVED":
            record.disposition = "DEFERRED WITH CAUSE"
            record.next_action = "Resolve before queueing: effective equipment slot."
            continue
        if record.effective_slot not in {"Underwear", "VanityBody"}:
            record.disposition = "OUT OF SCOPE"
            record.next_action = "Do not propagate a body-slot correction into this equipment slot."
            continue
        gaps = _route_gaps(record)
        if gaps:
            record.disposition = "DEFERRED WITH CAUSE"
            record.next_action = "Resolve before queueing: " + "; ".join(gaps) + "."
        elif record.disposition == "CONFIRMED DEFECT / CORRECT":
            record.next_action = "Build only the evidenced correction contract; do not place in a gameplay queue."
        else:
            record.disposition = "READY FOR TEST"
            record.next_action = "Place only in the declared candidate-profile queue."
    counts = Counter(record.identity for record in reconciled)
    duplicates = [identity for identity, count in counts.items() if count != 1]
    if duplicates:
        raise ValueError(f"duplicate master identities: {duplicates}")
    if any(record.disposition == "UNCLASSIFIED" for record in reconciled):
        raise ValueError("master ledger contains UNCLASSIFIED records")
    return sorted(reconciled, key=lambda item: item.identity)


def _load_registry(registry_path: Path) -> dict:
    return json.loads(registry_path.read_text(encoding="utf-8"))


def _metadata_values(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    for node in root.iter("node"):
        if node.attrib.get("id") == "ModuleInfo":
            return {
                child.attrib["id"]: child.attrib.get("value", "")
                for child in node
                if child.tag == "attribute" and "id" in child.attrib
            }
    raise ValueError(f"ModuleInfo missing: {path}")


def _source_authority(registry: dict) -> list[dict[str, object]]:
    report: list[dict[str, object]] = []
    for item in registry["source_modules"]:
        meta_path = Path(item["meta_path"])
        values = _metadata_values(meta_path)
        expected = {"Name": item["name"], "Folder": item["folder"], "UUID": item["uuid"], "Version64": item["version64"]}
        mismatch = {key: {"expected": value, "actual": values.get(key)} for key, value in expected.items() if values.get(key) != value}
        if mismatch:
            raise ValueError(f"registered metadata mismatch for {item['name']}: {mismatch}")
        inputs = []
        for raw_path in item["source_manifest_inputs"]:
            path = Path(raw_path)
            if not path.is_file():
                raise ValueError(f"registered manifest input is not a file: {path}")
            inputs.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper()})
        package_identity = dict(item["package_identity"])
        if package_identity.get("evidence_path"):
            evidence_path = Path(package_identity["evidence_path"])
            if not evidence_path.is_file():
                raise ValueError(f"registered package identity evidence is not a file: {evidence_path}")
            package_identity["evidence_sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest().upper()
        report.append({
            "name": item["name"], "metadata": expected, "meta_path": str(meta_path),
            "input_manifest": inputs,
            "package_identity": package_identity,
            "authority_scope": "registry-scoped retained extraction evidence only; global source completeness is not proven",
        })
    return report


def _load_evidence(prior_sources_path: Path) -> tuple[list[Evidence], list[dict[str, object]]]:
    data = json.loads(prior_sources_path.read_text(encoding="utf-8"))
    return (
        [Evidence(item["path"], item["kind"], item["date"], set(item.get("root_template_uuids", [])), item.get("identity"), item.get("body_mode"), item.get("route_role"), item.get("package_profile_identity"), item.get("artifact_sha256")) for item in data["evidence"]],
        data["registered_prior_sources"],
    )


def _prior_evidence_read_report(sources: list[dict[str, object]]) -> list[dict[str, object]]:
    report: list[dict[str, object]] = []
    for source in sources:
        path = Path(str(source["path"]))
        if not path.is_file():
            report.append({**source, "file_status": "MISSING"})
            continue
        payload = path.read_bytes()
        report.append({
            **source,
            "file_status": "READ",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
        })
    return report


def scan_registered_sources(registry_path: Path) -> tuple[list[GarmentRecord], list[dict[str, str]], list[dict[str, object]]]:
    registry = _load_registry(registry_path)
    authority = {item["metadata"]["UUID"]: item for item in _source_authority(registry)}
    shared_stats = Path(registry["shared_stats"])
    raw: list[GarmentRecord] = []
    rejections: list[dict[str, str]] = []
    module_summary: list[dict[str, object]] = []
    for item in registry["source_modules"]:
        if "root_templates" not in item:
            module_summary.append({"name": item["name"], "uuid": item["uuid"], "wearable_creation_paths": 0, "note": item["classification"], "authority": authority[item["uuid"]]["authority_scope"]})
            continue
        module = SourceModule(
            item["name"], item["uuid"], item["folder"], Path(item["root_templates"]),
            [shared_stats, *(Path(path) for path in item["stats_files"])],
            Path(item["visual_resources"]),
            (str(registry_path),),
        )
        records, source_rejections = scan_source(module)
        raw.extend(records)
        rejections.extend(source_rejections)
        module_summary.append({"name": item["name"], "uuid": item["uuid"], "wearable_creation_paths": len(records), "rejections": len(source_rejections), "authority": authority[item["uuid"]]["authority_scope"]})
    identities = Counter(record.identity for record in raw)
    duplicate_identities = [identity for identity, count in identities.items() if count != 1]
    if duplicate_identities:
        raise ValueError(f"scanner produced duplicate concrete identities: {duplicate_identities}")
    return raw, rejections, module_summary


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown(records: list[GarmentRecord], module_summary: list[dict[str, object]], rejections: list[dict[str, str]]) -> str:
    counts = Counter(record.disposition for record in records)
    slots = Counter(record.effective_slot for record in records)
    lines = [
        "# SCO/Sindae Master Garment Ledger",
        "",
        "This is a registry-scoped static inventory. It proves only the retained source roots recorded in SOURCE_AUTHORITY_REPORT.json; global SCO/Sindae completeness is not proven.",
        "`READY FOR TEST` and `CONFIRMED DEFECT / CORRECT` are not gameplay passes.",
        "",
        "## Exact counts",
        "",
        f"- Concrete wearable creation paths: {len(records)}",
        f"- Scanner rejections: {len(rejections)}",
        f"- Duplicate concrete identities: 0",
        f"- UNCLASSIFIED records: 0",
        "",
        "## Module scan",
        "",
        "| Module | UUID | Creation paths | Rejections / note |",
        "|---|---|---:|---|",
    ]
    lines.extend(f"| {item['name']} | {item['uuid']} | {item['wearable_creation_paths']} | {item.get('rejections', item.get('note', ''))} |" for item in module_summary)
    lines.extend(["", "## Dispositions", ""])
    lines.extend(f"- {key}: {counts[key]}" for key in sorted(counts))
    lines.extend(["", "## Effective slots", ""])
    lines.extend(f"- {key}: {slots[key]}" for key in sorted(slots))
    lines.extend(["", "## Records", "", "| Identity | Module | Root template | Stats | Slot | Source VR | Disposition | Next action |", "|---|---|---|---|---|---|---|---|"])
    for record in records:
        lines.append(f"| `{record.identity}` | {record.source_module['name']} | `{record.root_template_uuid}` | `{record.stats_entry}` | {record.effective_slot} | `{record.source_visual_resource_uuid}` | {record.disposition} | {record.next_action} |")
    return "\n".join(lines) + "\n"


def generate_class_queues(records: list[GarmentRecord]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str, str, str, str], list[GarmentRecord]] = defaultdict(list)
    for record in records:
        if record.disposition != "READY FOR TEST":
            continue
        grouped[(
            record.source_module["uuid"], record.effective_slot, record.body_family,
            record.topology_family, record.component_contract,
            json.dumps(record.package_ownership, sort_keys=True),
            json.dumps(record.candidate_profile, sort_keys=True), record.known_defect or "NONE",
        )].append(record)
    queues: list[dict[str, object]] = []
    for index, (group, members) in enumerate(sorted(grouped.items()), 1):
        queues.append({
            "queue_id": f"Q{index:03d}",
            "source_module_uuid": group[0],
            "effective_slot": group[1],
            "body_family": group[2],
            "topology_family": group[3],
            "component_contract": group[4],
            "package_ownership": json.loads(group[5]),
            "candidate_profile": json.loads(group[6]),
            "defect_mechanism": group[7],
            "record_identities": [member.identity for member in sorted(members, key=lambda item: item.identity)],
            "result": "NOT RUN",
            "required_evidence": ["startup/profile gate", "!cm_visdump", "front-side-defect-region screenshots", "save-reload evidence"],
        })
    return queues


def main(configuration: LocalConfiguration | None = None) -> None:
    """Generate local artifacts only after an operator explicitly supplies config."""
    config = validate_generated_outputs(configuration or load_local_configuration())
    config.evidence_dir.mkdir(parents=True, exist_ok=True)
    raw, rejections, module_summary = scan_registered_sources(config.source_registry_path)
    source_authority = _source_authority(_load_registry(config.source_registry_path))
    evidence, registered_sources = _load_evidence(config.prior_sources_path)
    prior_read_report = _prior_evidence_read_report(registered_sources)
    reconciled = reconcile(raw, evidence)
    master = build_master_ledger(raw, evidence)
    queues = generate_class_queues(master)
    _write_json(config.evidence_dir / "RAW_WEARABLE_INVENTORY.json", [record.to_dict() for record in raw])
    _write_json(config.evidence_dir / "SCAN_REJECTIONS.json", rejections)
    _write_json(config.evidence_dir / "SOURCE_AUTHORITY_REPORT.json", source_authority)
    _write_json(config.evidence_dir / "RECONCILIATION_REPORT.json", {"registered_prior_sources": registered_sources, "conflicts": reconciled.conflicts})
    _write_json(config.evidence_dir / "PRIOR_EVIDENCE_READ_REPORT.json", prior_read_report)
    _write_json(config.evidence_dir / "SCO_SINDAE_MASTER_GARMENT_LEDGER.json", [record.to_dict() for record in master])
    (config.evidence_dir / "SCO_SINDAE_MASTER_GARMENT_LEDGER.md").write_text(_markdown(master, module_summary, rejections), encoding="utf-8")
    _write_json(config.evidence_dir / "CLASS_TEST_QUEUES.json", queues)


if __name__ == "__main__":
    main()
