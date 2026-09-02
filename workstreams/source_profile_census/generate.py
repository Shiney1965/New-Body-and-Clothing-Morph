"""Deterministic exact-source discovery; never a release authority validator.

Configured snapshot IDs are discovery labels, not canonical ledger/profile IDs.
All emitted profiles remain candidates: this stage has no independently approved
permission, canonical body-map or precedence authority validator. A hash-pinned
supplied contract is retained and checked, but cannot promote itself to authority.
No converter, network, installer, live profile or existing ledger is operated.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import UUID
import xml.etree.ElementTree as ET

from . import snapshot as boundary
from .snapshot import FileSnapshot, load_snapshot
from .resources import parse_resources
from .creation_paths import resolve_creation_paths


@dataclass(frozen=True)
class CensusConfiguration:
    sources: tuple[Mapping, ...]
    output_directory: Path
    profile_contracts: Mapping = field(default_factory=dict)
    evidence_inputs: tuple[Mapping, ...] = ()
    legacy_comparisons: tuple[Mapping, ...] = ()
    unresolved_inputs: tuple[str, ...] = ("BASE_GAME_SOURCE_PROFILE_UNRESOLVED",)


@dataclass(frozen=True)
class CensusResult:
    output_directory: Path
    candidates: tuple[dict, ...]
    audit: dict
    artifact_hashes: dict


def _plain(value):
    if isinstance(value, FileSnapshot):
        return {"relative_path": value.relative_path, "locator": value.locator,
                "sha256": value.sha256, "bytes": value.size}
    if is_dataclass(value):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _bytes(value):
    return (json.dumps(_plain(value), sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _hash(value):
    return sha256(_bytes(value)).hexdigest().upper()


def audit_coverage(discovered, emitted):
    """Multiset-aware, bidirectional raw discovery accounting (no exclusions)."""
    source, census = Counter(discovered), Counter(emitted)
    result = {"missing_from_census": sorted((source - census).elements()),
              "census_without_source": sorted((census - source).elements()),
              "duplicate_source_rows": sorted(k for k, n in source.items() if n > 1),
              "duplicate_census_rows": sorted(k for k, n in census.items() if n > 1)}
    result["complete"] = not any(result.values())
    return result


def compare_legacy_entries(old, fresh):
    """Compare all retained rows, without choosing winners or dropping duplicates."""
    def grouped(rows):
        groups = defaultdict(list)
        for row in rows:
            groups[(row["kind"], row["resource_id"])].append(row)
        return groups

    before, after = grouped(old), grouped(fresh)
    order = lambda keys: sorted(keys, key=lambda k: (k[0], k[1] or ""))
    changed = []
    for key in order(before.keys() & after.keys()):
        a, b = ([{"attributes": r["relationships"], "structure": r.get("structure")} for r in side[key]] for side in (before, after))
        if a != b:
            kinds = []
            if len(a) != len(b):
                kinds.append("ENTRY_MULTIPLICITY")
            if {_hash(r) for r in a} != {_hash(r) for r in b}:
                kinds.append("RELATIONSHIP_CONTENT")
            if not kinds:
                kinds.append("ORDER_OR_OCCURRENCE")
            changed.append({"kind": key[0], "resource_id": key[1], "old": a, "fresh": b, "change_kinds": kinds})
    return {"old_entries": old, "fresh_entries": fresh,
            "added_ids": [list(k) for k in order(after.keys() - before.keys())],
            "missing_fresh_ids": [list(k) for k in order(before.keys() - after.keys())],
            "changed_relationships": changed,
            "duplicate_old_ids": [list(k) for k in order(k for k in before if len(before[k]) > 1)],
            "duplicate_fresh_ids": [list(k) for k in order(k for k in after if len(after[k]) > 1)],
            "legacy_authoritative": False}


def _read_evidence(descriptor):
    root = Path(descriptor["root"])
    if not root.is_absolute():
        raise ValueError("CONFIG_INVALID: evidence root must be absolute")
    for component in (*reversed(root.parents), root):
        boundary._check_link(component)
    return boundary._read(root.resolve(strict=True), descriptor)


def _input(file, role, profile=None):
    return {"role": role, "discovery_profile_id": profile, **_plain(file)}


def _output_path(configuration):
    output = Path(configuration.output_directory)
    if not output.is_absolute():
        raise ValueError("CONFIG_INVALID: output_directory must be absolute")
    # Never follow junctions, even above an otherwise ordinary output leaf.
    for component in (*reversed(output.parents), output):
        if component.exists() or component.is_symlink():
            boundary._check_link(component)
    if output.exists():
        raise FileExistsError(output)
    output = output.resolve()
    for source in configuration.sources:
        root = Path(source["root"])
        guarded = [root / source["extract_root"]["path"]]
        guarded.extend(root / c["inspection_root"]["path"] for c in source["conversions"])
        for path in guarded:
            target = path.resolve()
            if output == target or output.is_relative_to(target) or target.is_relative_to(output):
                raise ValueError("OUTPUT_INPUT_OVERLAP: " + str(output))
    return output


def _dependencies(source, censuses):
    # Follow UUID declarations even when versions differ, so the resolver retains
    # the exact-version mismatch. Equality is evidence policy, not engine policy.
    reached, pending = [], list(source.snapshot.module.dependencies)
    seen = {source.snapshot.profile_id}
    while pending:
        declaration = pending.pop(0)
        for other in censuses:
            if other.snapshot.module.uuid.lower() == declaration.uuid.lower() and other.snapshot.profile_id not in seen:
                seen.add(other.snapshot.profile_id)
                reached.append(other)
                pending.extend(other.snapshot.module.dependencies)
    return tuple(reached)


def _contract_structure(value):
    """Section-7.1 syntax only, never semantic permission/body-map approval."""
    text = lambda v: isinstance(v, str) and bool(v.strip())
    digest = lambda v: isinstance(v, str) and re.fullmatch(r"[0-9A-F]{64}", v) is not None
    if not isinstance(value, dict):
        return False
    try:
        module, permission = value["module"], value["permission"]
        return (value["schema"] == "clothmorph.source-profile" and type(value["schema_version"]) is int
            and value["schema_version"] == 1 and text(value["profile_id"])
            and isinstance(module, dict) and all(text(module[k]) for k in ("pak_filename", "folder", "name", "uuid", "version64"))
            and str(UUID(module["uuid"])) == module["uuid"].lower()
            and re.fullmatch(r"[0-9]+", module["version64"]) is not None
            and digest(module["pak_sha256"])
            and all(digest(value[k]) for k in ("content_manifest_sha256", "root_stats_visualbank_digest", "route_partition_digest"))
            and all(isinstance(value[k], list) for k in ("required_dependencies", "forbidden_modules", "supported_body_tuples"))
            and isinstance(permission, dict) and permission["state"] in ("private_test_only", "release_cleared", "blocked")
            and digest(permission["evidence_sha256"]) and text(permission["credit_line"])
            and isinstance(permission["distribution_limits"], list)
            and all(isinstance(v, str) for v in permission["distribution_limits"]))
    except (KeyError, TypeError, ValueError):
        return False


def _candidate(census, creation, supplied):
    snapshot = census.snapshot
    contract = {"schema": "clothmorph.source-profile", "schema_version": 1, "profile_id": None,
        "module": {"pak_filename": Path(snapshot.package.locator).name,
                   **{k: getattr(snapshot.module, k) for k in ("uuid", "folder", "name", "version64")},
                   "pak_sha256": snapshot.package.sha256},
        "content_manifest_sha256": snapshot.content_manifest.sha256,
        "root_stats_visualbank_digest": _hash([d for d in census.definitions if d.kind in ("RootTemplate", "Stats", "VisualBank")]),
        "required_dependencies": _plain(snapshot.module.dependencies), "forbidden_modules": None,
        "supported_body_tuples": None,
        "permission": {"state": None, "evidence_sha256": None, "credit_line": None, "distribution_limits": None},
        "route_partition_digest": None}
    blockers = {"CANONICAL_PROFILE_ID_UNRESOLVED", "PERMISSION_EVIDENCE_MISSING",
                "BODY_MAP_AUTHORITY_UNRESOLVED", "PRECEDENCE_AUTHORITY_UNRESOLVED",
                "FORBIDDEN_MODULES_AUTHORITY_UNRESOLVED", "ROUTE_PARTITION_UNRESOLVED",
                "PROFILE_AUTHORITY_VALIDATOR_UNAVAILABLE"}
    blockers.update(i.code for i in census.issues)
    blockers.update(i.code for i in creation.issues)
    if snapshot.unconverted_binary_paths:
        blockers.add("BINARY_CONVERSION_INCOMPLETE")
    supplied_value = None
    structurally_complete = False
    if supplied:
        supplied_value = json.loads(supplied.data.decode("utf-8-sig"))
        # Structural/binding checks are diagnostic only; no authority validator
        # has been approved here, even for a fully self-consistent document.
        structurally_complete = _contract_structure(supplied_value)
        if not structurally_complete:
            blockers.add("SUPPLIED_CONTRACT_INCOMPLETE")
        for key in ("schema", "schema_version", "module", "content_manifest_sha256", "root_stats_visualbank_digest", "required_dependencies"):
            if not isinstance(supplied_value, dict) or supplied_value.get(key) != contract[key]:
                blockers.add("SUPPLIED_CONTRACT_BINDING_MISMATCH")
        blockers.add("SUPPLIED_PERMISSION_SCOPE_UNVALIDATED")
    return {"discovery_profile_id": snapshot.profile_id, "role": snapshot.role,
        "contract": contract, "supplied_contract": supplied_value,
        "supplied_contract_structurally_complete": structurally_complete,
        "admissible_contract": None, "release_profile_complete": False,
        "definition_parse_complete": census.definition_parse_complete,
        "creation_paths_complete": creation.creation_paths_complete,
        "observed_creation_paths_digest": _hash(creation.observations),
        "blockers": sorted(blockers)}


def _legacy_entries(file, kind):
    text = file.data.decode("utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("LEGACY_XML_UNSUPPORTED: DTD/entity")
    tree = ET.fromstring(text)
    region, record, identity = ("Templates", "GameObjects", "MapKey") if kind == "RootTemplate" else ("VisualBank", "Resource", "ID")
    rows = []
    for index, node in enumerate(tree.findall(f".//region[@id='{region}']//node[@id='{record}']")):
        ids = [a.get("value") for a in node.findall(f"attribute[@id='{identity}']")]
        rows.append({"kind": kind, "resource_id": ids[0] if len(ids) == 1 else None,
            "legacy_row": index, "input_sha256": file.sha256,
            "relationships": [[a.get("id"), a.get("value")] for a in node.iter("attribute")],
            "structure": _xml_shape(node)})
    return rows


def _xml_shape(node):
    if isinstance(node, ET.Element):
        return [node.tag, sorted(node.attrib.items()), [_xml_shape(child) for child in node]]
    return [node.tag, sorted(node.attributes), [_xml_shape(child) for child in node.children
                                               if not child.tag.startswith("#")]]


def _relationships(node):
    if node is None:
        return []
    values = []
    if node.tag == "attribute":
        attrs = dict(node.attributes)
        values.append([attrs.get("id"), attrs.get("value")])
    for child in node.children:
        values.extend(_relationships(child))
    return values


def _counts(census, creation):
    meshes = [f.relative_path for f in census.snapshot.files if f.relative_path.lower().endswith(".gr2")]
    references = {value.replace("\\", "/").casefold() for d in census.definitions if d.kind == "VisualBank"
                  for key, value in _relationships(d.node) if key == "SourceFile" and value}
    shared = [o for o in creation.observations if o.kind == "CHARACTER_CREATION_SHARED_VISUAL"]
    return {"input_file_count": len(census.snapshot.files),
        "binary_bank_file_count": sum(f.relative_path.lower().endswith(".lsf") for f in census.snapshot.files),
        "verified_conversion_count": len(census.snapshot.conversions),
        "unconverted_binary_paths": list(census.snapshot.unconverted_binary_paths),
        "definition_count": len(census.definitions), "definitions_by_kind": dict(sorted(Counter(d.kind for d in census.definitions).items())),
        "creation_observation_count": len(creation.observations),
        "creation_by_kind": dict(sorted(Counter(o.kind for o in creation.observations).items())),
        "shared_visual_resolved_join_count": sum(len(o.routes) == 1 and len(o.routes[0].components) == 1
            and o.routes[0].components[0].mesh is not None for o in shared),
        "distinct_gr2_name_count": len({Path(p).name for p in meshes}),
        "unreferenced_mesh_paths": sorted(p for p in meshes if p.casefold() not in references),
        # Names and paths are distinct controls: a duplicate packed path with
        # the same referenced basename is not an unreferenced mesh NAME.
        "unreferenced_mesh_names": sorted({Path(p).name for p in meshes
            if Path(p).name.casefold() not in {Path(r).name for r in references}}),
        "resource_issues": dict(sorted(Counter(i.code for i in census.issues).items())),
        "creation_issues": dict(sorted(Counter(i.code for i in creation.issues).items()))}


def generate_census(config: CensusConfiguration) -> CensusResult:
    """Verify inputs, assemble deterministic artifacts, publish only to a new leaf."""
    if type(config) is not CensusConfiguration or not config.sources:
        raise ValueError("CONFIG_INVALID: nonempty CensusConfiguration required")
    output = _output_path(config)
    ids = [s["profile_id"] for s in config.sources]
    if len(set(ids)) != len(ids):
        raise ValueError("SOURCE_DUPLICATE: discovery profile IDs")
    if set(config.profile_contracts) - set(ids):
        raise ValueError("CONFIG_INVALID: contract without configured source")
    snapshots = tuple(load_snapshot(s) for s in config.sources)
    censuses = tuple(parse_resources(s) for s in snapshots)
    paths = tuple(resolve_creation_paths(c, _dependencies(c, censuses)) for c in censuses)
    inputs, candidates, profiles = [], [], []
    raw_files, definitions, observations = [], [], []
    discovered = []
    for census, creation in zip(censuses, paths):
        snap = census.snapshot
        profile = snap.profile_id
        inputs.append({"role": "package", "discovery_profile_id": profile,
                       "locator": snap.package.locator, "sha256": snap.package.sha256, "bytes": snap.package.size})
        for role, fileset in (("content_manifest", (snap.content_manifest,)), ("listing", (snap.listing,)),
                             ("source_file", snap.files), ("conversion_manifest", snap.conversion_manifests),
                             ("conversion_inspection", tuple(c.inspection for c in snap.conversions))):
            inputs.extend(_input(f, role, profile) for f in fileset)
        supplied = _read_evidence(config.profile_contracts[profile]) if profile in config.profile_contracts else None
        if supplied:
            inputs.append(_input(supplied, "supplied_contract", profile))
        candidates.append(_candidate(census, creation, supplied))
        profiles.append({"discovery_profile_id": profile, "module": _plain(snap.module), "package": _plain(snap.package),
                         "counts": _counts(census, creation)})
        discovered.extend(f"file:{profile}:{f.relative_path}" for f in snap.files)
        discovered.extend("definition:" + d.observation_id for d in census.definitions)
        discovered.extend("creation:" + o.observation_id for o in creation.observations)
        raw_files.extend({"row_id": f"file:{profile}:{f.source.original.relative_path}", **_plain(f)} for f in census.files)
        definitions.extend({"row_id": "definition:" + d.observation_id, **_plain(d)} for d in census.definitions)
        observations.extend({"row_id": "creation:" + o.observation_id, **_plain(o)} for o in creation.observations)
    for descriptor in config.evidence_inputs:
        inputs.append(_input(_read_evidence(descriptor), "supporting_evidence"))
    comparisons = []
    by_profile = {c.snapshot.profile_id: c for c in censuses}
    for comparison in config.legacy_comparisons:
        census = by_profile[comparison["profile_id"]]
        old = []
        for key, kind in (("root_templates", "RootTemplate"), ("visual_resources", "VisualBank")):
            artifact = _read_evidence(comparison[key])
            inputs.append(_input(artifact, "legacy_comparison", census.snapshot.profile_id))
            old.extend(_legacy_entries(artifact, kind))
        fresh = [{"kind": d.kind, "resource_id": d.resource_id, "observation_id": d.observation_id,
                  "relationships": _relationships(d.node), "structure": _xml_shape(d.node)}
                 for d in census.definitions if d.kind in ("RootTemplate", "VisualBank")]
        comparisons.append({"discovery_profile_id": census.snapshot.profile_id, **compare_legacy_entries(old, fresh)})
    for name in ("__init__.py", "snapshot.py", "resources.py", "creation_paths.py", "generate.py"):
        path = Path(__file__).with_name(name)
        data = path.read_bytes()
        inputs.append({"role": "code", "locator": str(path), "sha256": sha256(data).hexdigest().upper(), "bytes": len(data)})
    # The normalized configuration binds all pins and unresolved-input declarations,
    # but deliberately excludes the output leaf so repeat runs can be identical.
    normalized_config = _plain(config)
    del normalized_config["output_directory"]
    artifacts = {"SOURCE_SNAPSHOTS.json": _plain(snapshots), "RAW_FILES.json": raw_files,
        "RAW_DEFINITIONS.json": definitions, "RAW_CREATION_PATHS.json": observations,
        "SOURCE_PROFILE_CANDIDATES.json": candidates, "LEGACY_COMPARISONS.json": comparisons,
        "INPUT_MANIFEST.json": {"configuration": normalized_config, "configuration_sha256": _hash(normalized_config), "inputs": inputs}}
    emitted = [r["row_id"] for rows in (raw_files, definitions, observations) for r in rows]
    audit = {"schema": "clothmorph.source-profile-census-audit", "schema_version": 1,
        "configured_source_count": len(snapshots), "profiles": profiles,
        "raw_coverage": audit_coverage(discovered, emitted), "unresolved_inputs": list(config.unresolved_inputs),
        "release_profile_complete": False, "release_complete": False, "canonical_ledger_integrated": False,
        "next_integration_requirements": ["independent census review", "accepted section-7.1 authority validators",
            "old-observation-to-new-identity migration", "canonical scope events and anti-omission reconciliation",
            "remaining exact source profiles", "Runtime 1.4", "mesh correction", "package validation", "gameplay acceptance"]}
    artifacts["CENSUS_AUDIT.json"] = audit
    # Issues/conflicts remain explicit original objects, not just aggregate counts.
    artifacts["UNRESOLVED_EVIDENCE.json"] = [{"discovery_profile_id": c.snapshot.profile_id,
        "resource_issues": _plain(c.issues), "conflicts": _plain(c.conflicts),
        "inheritances": _plain(c.inheritances), "creation_issues": _plain(p.issues)} for c, p in zip(censuses, paths)]
    serialized = {name: _bytes(value) for name, value in artifacts.items()}
    hashes = {name: sha256(data).hexdigest().upper() for name, data in sorted(serialized.items())}
    serialized["OUTPUT_MANIFEST.json"] = _bytes({"artifacts": [{"path": name, "sha256": hashes[name], "bytes": len(serialized[name])}
                                                             for name in sorted(serialized)]})
    # Parent must already exist; do not create arbitrary trees or touch inputs.
    output.mkdir(exist_ok=False)
    for name, data in serialized.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    for name, data in serialized.items():
        if (output / name).read_bytes() != data:
            raise ValueError("OUTPUT_VERIFICATION_FAILED: " + name)
    if set(p.name for p in output.iterdir()) != set(serialized):
        raise ValueError("OUTPUT_SET_MISMATCH")
    return CensusResult(output, tuple(candidates), audit, hashes)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.config.read_bytes().decode("utf-8-sig"))
    result = generate_census(CensusConfiguration(output_directory=args.output, **value))
    print(json.dumps({"output": str(result.output_directory), "hashes": result.artifact_hashes,
                      "configured_source_count": result.audit["configured_source_count"], "release_complete": False}, indent=2))


if __name__ == "__main__":
    main()
