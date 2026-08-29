"""Read-only scanner for concrete SCO/Sindae wearable creation routes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import xml.etree.ElementTree as ET

from .models import GarmentRecord, RouteRecord


@dataclass(frozen=True)
class SourceModule:
    name: str
    uuid: str
    folder: str
    root_templates: Path
    stats_files: list[Path]
    visual_resources: Path | None
    evidence: tuple[str, ...] = ()


ENTRY_RE = re.compile(r'^new entry "([^"]+)"$', re.MULTILINE)
USING_RE = re.compile(r'^using "([^"]+)"$', re.MULTILINE)
DATA_RE = re.compile(r'^data "([^"]+)" "([^"]*)"$', re.MULTILINE)


def _attrs(node: ET.Element) -> dict[str, str]:
    return {
        child.attrib["id"]: child.attrib.get("value", "")
        for child in node
        if child.tag == "attribute" and "id" in child.attrib
    }


def _read_stats(paths: list[Path]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = list(ENTRY_RE.finditer(text))
        for index, match in enumerate(matches):
            body = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
            data = dict(DATA_RE.findall(body))
            using = USING_RE.search(body)
            entries[match.group(1)] = {
                "using": using.group(1) if using else None,
                "data": data,
            }
    return entries


def _resolve_slot(entry_name: str, entries: dict[str, dict[str, Any]]) -> tuple[str | None, list[str]]:
    chain: list[str] = []
    current = entry_name
    while current and current not in chain:
        chain.append(current)
        entry = entries.get(current)
        if entry is None:
            return None, chain
        slot = entry["data"].get("Slot")
        if slot:
            return slot, chain
        current = entry["using"]
    return None, chain


def _visual_paths(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    root = ET.parse(path).getroot()
    result: dict[str, str] = {}
    for node in root.iter("node"):
        if node.attrib.get("id") != "Resource":
            continue
        attrs = _attrs(node)
        if attrs.get("ID") and attrs.get("SourceFile"):
            result[attrs["ID"]] = attrs["SourceFile"]
    return result


def _visual_ids(item: ET.Element) -> list[str]:
    ids: list[str] = []
    attrs = _attrs(item)
    if attrs.get("VisualTemplate"):
        ids.append(attrs["VisualTemplate"])
    for node in item.iter("node"):
        if node.attrib.get("id") != "MapValue":
            continue
        attrs = _attrs(node)
        if attrs.get("Object"):
            ids.append(attrs["Object"])
    return list(dict.fromkeys(ids))


def _body_family(name: str) -> str:
    if name.startswith("HUM_F_"):
        return "HUM_F"
    if name.startswith("HUM_M_"):
        return "HUM_M"
    if name.startswith("GTY_"):
        return "GTY"
    return "UNSPECIFIED"


def _garment_family(name: str) -> str:
    return name.removeprefix("HUM_F_").removeprefix("HUM_M_").removeprefix("GTY_")


def _stats_paths_for_root(root_uuid: str, root_stats: str, entries: dict[str, dict[str, Any]]) -> list[str]:
    paths = [root_stats]
    for name, entry in entries.items():
        if entry["data"].get("RootTemplate") == root_uuid and name not in paths:
            paths.append(name)
    return paths


def scan_source(module: SourceModule) -> tuple[list[GarmentRecord], list[dict[str, str]]]:
    """Return one record per concrete root/stats/VR/body identity, without mutation."""
    stats = _read_stats(module.stats_files)
    visual_paths = _visual_paths(module.visual_resources)
    root = ET.parse(module.root_templates).getroot()
    records: list[GarmentRecord] = []
    rejections: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in root.iter("node"):
        if item.attrib.get("id") != "GameObjects":
            continue
        attrs = _attrs(item)
        if attrs.get("Type") != "item" or not attrs.get("MapKey") or not attrs.get("Stats"):
            continue
        visual_ids = _visual_ids(item)
        if not visual_ids:
            continue
        for stats_entry in _stats_paths_for_root(attrs["MapKey"], attrs["Stats"], stats):
            slot, chain = _resolve_slot(stats_entry, stats)
            for visual_id in visual_ids:
                path = visual_paths.get(visual_id)
                if path is None:
                    rejections.append({
                        "source_module_uuid": module.uuid,
                        "root_template_uuid": attrs["MapKey"],
                        "stats_entry": stats_entry,
                        "visual_resource_uuid": visual_id,
                        "reason": "visual_resource_unresolved",
                    })
                if slot is None:
                    rejections.append({
                        "source_module_uuid": module.uuid,
                        "root_template_uuid": attrs["MapKey"],
                        "stats_entry": stats_entry,
                        "visual_resource_uuid": visual_id,
                        "reason": "equipment_slot_unresolved",
                    })
                family = _body_family(attrs.get("Name", ""))
                effective_slot = slot or "UNRESOLVED"
                identity = "|".join((module.uuid, attrs["MapKey"], stats_entry, effective_slot, visual_id, family))
                if identity in seen:
                    continue
                seen.add(identity)
                records.append(GarmentRecord(
                    identity=identity,
                    source_module={"name": module.name, "uuid": module.uuid, "folder": module.folder},
                    root_template_uuid=attrs["MapKey"],
                    stats_entry=stats_entry,
                    effective_slot=effective_slot,
                    inheritance_chain=chain,
                    source_visual_resource_uuid=visual_id,
                    source_visual_resource_path=path,
                    body_family=family,
                    garment_family=_garment_family(attrs.get("Name", "")),
                    topology_family="UNASSESSED",
                    component_contract="UNASSESSED",
                    routes={
                        "source_native": RouteRecord("source_native", visual_id, path, "source root-template route"),
                        "Vanilla": RouteRecord("Vanilla", None, None, "UNRESOLVED TARGET ROUTE"),
                        "SBBF": RouteRecord("SBBF", None, None, "UNRESOLVED TARGET ROUTE"),
                        "BCB": RouteRecord("BCB", None, None, "UNRESOLVED TARGET ROUTE"),
                    },
                    evidence=list(module.evidence),
                ))
    return records, rejections
