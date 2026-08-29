from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from .models import SlotResolution, StatRecord
    from .slot_resolver import parse_stats, resolve_slot
except ImportError:  # Direct script execution from this directory only.
    from models import SlotResolution, StatRecord
    from slot_resolver import parse_stats, resolve_slot


ENTRY_PATTERN = re.compile(r'^new entry "([^"]+)"$')
TYPE_PATTERN = re.compile(r'^type "([^"]+)"$')
ROOT_PATTERN = re.compile(r'^data "RootTemplate" "([^"]+)"$')


@dataclass(frozen=True)
class SourceInput:
    source: str
    module_folder: str
    module_name: str
    module_uuid: str
    version64: str
    stats: tuple[Path, ...]
    roots: tuple[Path, ...]
    meta_path: Path | None = None
    original_pak: Path | None = None
    dependency_stats: tuple[Path, ...] = ()


@dataclass(frozen=True)
class SourceRoots:
    shared_stats: tuple[Path, ...]
    sources: tuple[SourceInput, ...]
    rejections_path: Path


@dataclass(frozen=True)
class GarmentRecord:
    source: str
    module_folder: str
    module_name: str
    module_uuid: str
    version64: str
    display_name: str
    root_template_uuid: str
    stats_entry: str
    root_stats_entry: str
    creation_path: str
    effective_slot: str
    inheritance: tuple[str, ...]
    source_visual_resource_uuid: str = "MISSING"
    source_visual_path: str = "MISSING: VisualBank join not yet performed"
    native_body_form: str = "UNASSESSED: no decoded body-form proof"
    vanilla_route: str = "UNASSESSED: no target provenance"
    sbbf_route: str = "UNASSESSED: no target provenance"
    bcb_route: str = "UNASSESSED: no target provenance"
    disposition: str = "MISSING ROUTE / BUILD"
    gameplay_status: str = "NOT RUN"


@dataclass(frozen=True)
class ClassificationResult:
    """Pure classification output; persistence is the canonical ledger writer's job."""

    records: tuple[GarmentRecord, ...]
    rejections: tuple[dict[str, object], ...]


def _parse_armor_root_templates(path: Path) -> dict[str, str]:
    """Return declared RootTemplate UUIDs for Armor entries only."""

    result: dict[str, str] = {}
    current_name: str | None = None
    current_type: str | None = None
    current_root = ""

    def save_current() -> None:
        if current_name is not None and current_type == "Armor":
            result[current_name] = current_root.lower()

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        entry_match = ENTRY_PATTERN.match(line)
        if entry_match:
            save_current()
            current_name = entry_match.group(1)
            current_type = None
            current_root = ""
            continue
        if current_name is None:
            continue
        type_match = TYPE_PATTERN.match(line)
        if type_match:
            current_type = type_match.group(1)
            continue
        root_match = ROOT_PATTERN.match(line)
        if root_match:
            current_root = root_match.group(1)
    save_current()
    return result


def _parse_root_templates(paths: tuple[Path, ...]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for path in paths:
        document = ET.fromstring(path.read_text(encoding="utf-8-sig"))
        for node in document.findall(".//node[@id='GameObjects']"):
            attributes = {
                attribute.get("id", ""): attribute.get("value", "")
                for attribute in node.findall("./attribute")
            }
            root_uuid = attributes.get("MapKey", "").lower()
            if root_uuid:
                records[root_uuid] = {
                    "name": attributes.get("Name", ""),
                    "stats": attributes.get("Stats", ""),
                    "type": attributes.get("Type", ""),
                }
    return records


def _load_stats(paths: tuple[Path, ...]) -> dict[str, StatRecord]:
    records: dict[str, StatRecord] = {}
    for path in paths:
        records.update(parse_stats(path))
    return records


def _to_record(
    source: SourceInput,
    *,
    display_name: str,
    root_template_uuid: str,
    stats_entry: str,
    root_stats_entry: str,
    creation_path: str,
    resolution: SlotResolution,
) -> GarmentRecord:
    if resolution.slot is None:
        raise ValueError("unresolved stats cannot become a garment record")
    return GarmentRecord(
        source=source.source,
        module_folder=source.module_folder,
        module_name=source.module_name,
        module_uuid=source.module_uuid,
        version64=source.version64,
        display_name=display_name or stats_entry,
        root_template_uuid=root_template_uuid,
        stats_entry=stats_entry,
        root_stats_entry=root_stats_entry,
        creation_path=creation_path,
        effective_slot=resolution.slot,
        inheritance=resolution.inheritance,
    )


def classify_creation_paths(source_roots: SourceRoots) -> ClassificationResult:
    """Resolve named-stat and disagreeing root-template creation paths.

    Failure to resolve inheritance is material evidence returned to the caller,
    never persisted through a caller-selected path.
    """

    all_records: list[GarmentRecord] = []
    rejections: list[dict[str, object]] = []
    shared_stats = _load_stats(source_roots.shared_stats)

    for source in source_roots.sources:
        source_stats = _load_stats((*source.stats, *source.dependency_stats))
        stats = dict(shared_stats)
        stats.update(source_stats)
        armor_roots: dict[str, str] = {}
        for path in source.stats:
            armor_roots.update(_parse_armor_root_templates(path))
        roots = _parse_root_templates(source.roots)
        named_by_root: dict[str, list[tuple[str, SlotResolution]]] = {}

        for stats_entry, root_uuid in armor_roots.items():
            if not root_uuid:
                continue
            root = roots.get(root_uuid)
            if root is None or root.get("type") != "item":
                rejections.append(
                    {
                        "source": source.source,
                        "category": "NOT_A_WEARABLE" if root else "MISSING_ROOT_TEMPLATE",
                        "creation_path": "named_stats",
                        "stats_entry": stats_entry,
                        "root_template_uuid": root_uuid,
                    }
                )
                continue
            resolution = resolve_slot(stats_entry, stats)
            if resolution.slot is None:
                rejections.append(
                    {
                        "source": source.source,
                        "creation_path": "named_stats",
                        "stats_entry": stats_entry,
                        "root_template_uuid": root_uuid,
                        "inheritance": resolution.inheritance,
                        "cycle": resolution.cycle,
                        "missing_parent": resolution.missing_parent,
                    }
                )
                continue
            named_by_root.setdefault(root_uuid, []).append((stats_entry, resolution))
            all_records.append(
                _to_record(
                    source,
                    display_name=root.get("name", stats_entry),
                    root_template_uuid=root_uuid,
                    stats_entry=stats_entry,
                    root_stats_entry=root.get("stats", ""),
                    creation_path="named_stats",
                    resolution=resolution,
                )
            )

        for root_uuid, root in roots.items():
            root_stats = root.get("stats", "")
            if not root_stats:
                continue
            if root.get("type") != "item":
                rejections.append(
                    {
                        "source": source.source,
                        "category": "NOT_A_WEARABLE",
                        "creation_path": "root_template",
                        "stats_entry": root_stats,
                        "root_template_uuid": root_uuid,
                    }
                )
                continue
            root_resolution = resolve_slot(root_stats, stats)
            if root_resolution.slot is None:
                non_wearable_prefixes = ("OBJ_", "ALCH_", "WPN_", "MAG_", "FOOD_", "BOOK_", "QUEST_", "CONS_", "UNI_", "Tool_")
                if root.get("type") != "item" or root_stats.startswith(non_wearable_prefixes):
                    category = "NOT_A_WEARABLE"
                elif root_resolution.missing_parent and root_stats not in stats:
                    category = "MISSING_DEPENDENCY_STATS"
                else:
                    category = "UNRESOLVED_WEARABLE"
                rejections.append(
                    {
                        "source": source.source,
                        "category": category,
                        "creation_path": "root_template",
                        "stats_entry": root_stats,
                        "root_template_uuid": root_uuid,
                        "inheritance": root_resolution.inheritance,
                        "cycle": root_resolution.cycle,
                        "missing_parent": root_resolution.missing_parent,
                    }
                )
                continue
            named = named_by_root.get(root_uuid, [])
            differs_from_named = any(
                resolution.slot != root_resolution.slot
                for _, resolution in named
                if root_resolution.slot is not None
            )
            direct_underwear_root = not named and root_resolution.slot == "Underwear"
            if not differs_from_named and not direct_underwear_root:
                continue
            all_records.append(
                _to_record(
                    source,
                    display_name=root.get("name", root_stats),
                    root_template_uuid=root_uuid,
                    stats_entry=root_stats,
                    root_stats_entry=root_stats,
                    creation_path="root_template",
                    resolution=root_resolution,
                )
            )

    return ClassificationResult(tuple(all_records), tuple(rejections))


def build_all_creation_paths(source_roots: SourceRoots) -> list[GarmentRecord]:
    """Compatibility view of pure classification records; this function never writes."""

    return list(classify_creation_paths(source_roots).records)


def build_inventory(source_roots: SourceRoots) -> list[GarmentRecord]:
    """Return only routes whose resolved, effective equipment slot is Underwear."""

    return [
        record
        for record in classify_creation_paths(source_roots).records
        if record.effective_slot == "Underwear"
    ]


def records_to_json(records: list[GarmentRecord]) -> list[dict[str, object]]:
    return [asdict(record) for record in records]


def _read_module_identity(path: Path) -> tuple[str, str, str, str]:
    document = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    node = document.find(".//node[@id='ModuleInfo']")
    if node is None:
        raise ValueError(f"ModuleInfo missing from {path}")
    attributes = {item.get("id", ""): item.get("value", "") for item in node.findall("./attribute")}
    values = tuple(attributes.get(field, "") for field in ("Folder", "Name", "UUID", "Version64"))
    if not all(values):
        raise ValueError(f"incomplete module identity in {path}")
    return values


def workspace_source_roots(workspace_root: Path) -> SourceRoots:
    """Compatibility entry point for the one canonical ignored local config."""

    try:
        from .source_config import load_source_roots
        from .local_boundary import CANONICAL_SOURCE_CONFIG
    except ImportError:  # Direct script execution from this directory only.
        from source_config import load_source_roots
        from local_boundary import CANONICAL_SOURCE_CONFIG

    del workspace_root
    return load_source_roots(CANONICAL_SOURCE_CONFIG)
