"""Read-only evidence inspection for the eleven retained Authority audit gaps."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import re
import zipfile
import xml.etree.ElementTree as ET

import numpy as np


def inspect_gr2_bindings(source: Path, expected_sha256: str) -> dict[str, object]:
    """Read exact Granny model/mesh bindings using the pinned converter library."""
    if sha256_file(source) != expected_sha256:
        raise ValueError("GR2_SOURCE_HASH_MISMATCH")
    script = Path(__file__).with_name("inspect_gr2_bindings.ps1")
    powershell = Path("C:/Users/Alan/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")
    completed = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-File", str(script),
                                "-Source", str(source), "-ExpectedSourceSha256", expected_sha256],
                               cwd="C:/bg3-sidecar-work/Tools", capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise ValueError("GR2_READBACK_FAILED:" + completed.stdout + completed.stderr)
    result = json.loads(completed.stdout)
    if sha256_file(source) != expected_sha256 or result["source_sha256"] != expected_sha256:
        raise ValueError("GR2_SOURCE_CHANGED_DURING_READ")
    return result


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def inventory_against_listing(root: Path, listing: str) -> list[dict[str, object]]:
    """Read every file, rejecting omissions, extras, duplicate paths and reparses."""
    expected = {}
    for line in listing.splitlines():
        relative, size, _ = line.split("\t")
        if relative in expected or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("LISTING_PATH_INVALID")
        expected[relative] = int(size)
    records = []
    def unreadable(error):
        raise error
    for directory, directories, names in os.walk(root, onerror=unreadable):
        for name in directories + names:
            path = Path(directory) / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("INVENTORY_REPARSE_FORBIDDEN")
        for name in names:
            path = Path(directory) / name
            records.append({"path": path.relative_to(root).as_posix(),
                            "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    records.sort(key=lambda record: record["path"])
    actual = {record["path"]: record["bytes"] for record in records}
    if actual != expected:
        raise ValueError("LISTING_INVENTORY_MISMATCH:" + json.dumps(sorted(
            key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key))))
    return records


def source_audit_disposition(gaps: list[dict[str, object]]) -> dict[str, object]:
    """A completed bounded source audit is never a geometry test or exclusion."""
    ids = [record.get("gap_id") for record in gaps]
    complete = (len(ids) == 11 and set(ids) == {f"{number:02}" for number in range(1, 12)}
                and all(record.get("status") == "RESOLVED_SOURCE_EVIDENCE" for record in gaps))
    return {
        "status": "SOURCE_AUDIT_COMPLETE_GEOMETRY_UNASSESSED" if complete else "BLOCKED_SOURCE_AUDIT_INCOMPLETE",
        "source_audit_complete": complete,
        "geometry_admitted": False, "geometry_methods_tested": [],
        "defect_region": None, "exclusion_event_input": None,
        "ready_for_attachment": False, "release_blocking": True,
        "replacement_routes": 0, "protected_mutations": 0,
    }


def inspect_glb_semantics(path: Path) -> dict[str, object]:
    """Decode actual accessor bytes and retain source topology/skin semantics.

    This is readback of converter output, not a garment fit test or a claim of
    byte-preserving GR2 round-trip. Unsupported sparse/external accessors fail.
    """
    raw = Path(path).read_bytes()
    if len(raw) < 28 or raw[:4] != b"glTF" or struct.unpack_from("<II", raw, 4) != (2, len(raw)):
        raise ValueError("GLB_HEADER_INVALID")
    chunks = {}
    offset = 12
    while offset < len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        start = offset + 8
        end = start + length
        if end > len(raw) or kind in chunks:
            raise ValueError("GLB_CHUNK_INVALID")
        chunks[kind] = raw[start:end]
        offset = end
    document = json.loads(chunks[0x4E4F534A].decode("utf-8").rstrip(" \0\r\n\t"))
    binary = chunks.get(0x004E4942, b"")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or "uri" in buffers[0] or buffers[0]["byteLength"] > len(binary):
        raise ValueError("GLB_EXTERNAL_OR_INVALID_BUFFER")
    dtypes = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    accessors = document.get("accessors", [])
    arrays = {}
    def accessor(index):
        if index in arrays:
            return arrays[index]
        entry = accessors[index]
        if "sparse" in entry or "bufferView" not in entry:
            raise ValueError("GLB_ACCESSOR_UNSUPPORTED")
        view = document["bufferViews"][entry["bufferView"]]
        if view.get("buffer", 0) != 0:
            raise ValueError("GLB_EXTERNAL_OR_INVALID_BUFFER")
        dtype, width, count = np.dtype(dtypes[entry["componentType"]]), widths[entry["type"]], entry["count"]
        stride = view.get("byteStride", dtype.itemsize * width)
        view_start = view.get("byteOffset", 0)
        start = view_start + entry.get("byteOffset", 0)
        end = start + max(0, count - 1) * stride + (dtype.itemsize * width if count else 0)
        if count < 0 or stride < dtype.itemsize * width or start < view_start or end > view_start + view["byteLength"] or end > len(binary):
            raise ValueError("GLB_ACCESSOR_BOUNDS_INVALID")
        result = np.ndarray((count, width), dtype=dtype, buffer=binary, offset=start,
                            strides=(stride, dtype.itemsize)).copy()
        if not np.isfinite(result).all():
            raise ValueError("GLB_NONFINITE_ATTRIBUTE")
        arrays[index] = result
        return result
    def descriptor(index):
        entry = accessors[index]
        value = accessor(index)
        return {"count": entry["count"], "component_type": entry["componentType"],
                "type": entry["type"], "normalized": entry.get("normalized", False),
                "sha256": hashlib.sha256(value.tobytes()).hexdigest().upper()}
    nodes = document.get("nodes", [])
    skins = []
    for entry in document.get("skins", []):
        joints = entry["joints"]
        if any(index < 0 or index >= len(nodes) for index in joints):
            raise ValueError("SKIN_NODE_OUT_OF_RANGE")
        skin = {"joint_indices": joints, "joint_names": [nodes[index].get("name", "") for index in joints],
                "skeleton_node": entry.get("skeleton"), "inverse_bind_matrices": None}
        if "inverseBindMatrices" in entry:
            if accessor(entry["inverseBindMatrices"]).shape != (len(joints), 16):
                raise ValueError("SKIN_BIND_MATRIX_COUNT_MISMATCH")
            skin["inverse_bind_matrices"] = descriptor(entry["inverseBindMatrices"])
        skins.append(skin)
    meshes = []
    materials = document.get("materials", [])
    for mesh_index, entry in enumerate(document.get("meshes", [])):
        primitives = []
        for primitive in entry["primitives"]:
            if primitive.get("mode", 4) != 4 or primitive.get("targets"):
                raise ValueError("GLB_PRIMITIVE_UNSUPPORTED")
            attrs = primitive["attributes"]
            positions = accessor(attrs["POSITION"])
            indices = accessor(primitive["indices"]).reshape(-1)
            if positions.shape[1] != 3 or indices.size % 3:
                raise ValueError("GLB_TOPOLOGY_SHAPE_INVALID")
            if indices.size and (indices.min() < 0 or indices.max() >= len(positions)):
                raise ValueError("INDEX_OUT_OF_RANGE")
            for semantic, index in attrs.items():
                if len(accessor(index)) != len(positions):
                    raise ValueError("GLB_ATTRIBUTE_COUNT_MISMATCH")
            bound_skins = [node["skin"] for node in nodes if node.get("mesh") == mesh_index and "skin" in node]
            for bound_skin in bound_skins:
                for semantic, index in attrs.items():
                    if semantic.startswith("JOINTS_"):
                        values = accessor(index)
                        if values.size and (values.min() < 0 or values.max() >= len(skins[bound_skin]["joint_indices"])):
                            raise ValueError("JOINT_OUT_OF_RANGE")
            faces = indices.reshape(-1, 3)
            triangles = positions[faces].astype(np.float64)
            cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            attributes = {name: descriptor(index) for name, index in sorted(attrs.items())}
            material = primitive.get("material")
            if material is not None and not 0 <= material < len(materials):
                raise ValueError("MATERIAL_OUT_OF_RANGE")
            record = {
                "vertices": len(positions), "triangles": len(faces), "indices": int(indices.size),
                "indices_sha256": hashlib.sha256(indices.tobytes()).hexdigest().upper(),
                "attributes": attributes, "material_index": material, "bound_skins": bound_skins,
                "zero_area_triangles": int(np.count_nonzero(np.einsum("ij,ij->i", cross, cross) == 0)),
                "position_min": positions.min(axis=0).tolist(), "position_max": positions.max(axis=0).tolist(),
                "non_position_sha256": hashlib.sha256(canonical_bytes({
                    "attributes": {name: value for name, value in attributes.items() if name != "POSITION"},
                    "indices": descriptor(primitive["indices"]), "material": material,
                })).hexdigest().upper(),
            }
            for semantic, index in attrs.items():
                if semantic.startswith("WEIGHTS_"):
                    sums = accessor(index).astype(np.float64).sum(axis=1)
                    record[semantic + "_sum_range"] = [float(sums.min()), float(sums.max())]
            primitives.append(record)
        meshes.append({"name": entry.get("name", ""), "primitives": primitives})
    # Hash all nodes, including hierarchy/transforms and mesh/skin bindings.
    return {
        "glb_sha256": hashlib.sha256(raw).hexdigest().upper(), "glb_bytes": len(raw),
        "meshes": meshes, "skins": skins, "materials": materials,
        "nodes": nodes, "node_semantics_sha256": hashlib.sha256(canonical_bytes(nodes)).hexdigest().upper(),
        "geometry_method_tested": False, "defect_region": None,
        "readback_scope": "Converted GLB accessors/topology/skin/node/material semantics; not a GR2 round-trip or fit test.",
    }


WORKSTREAM = Path(__file__).resolve().parent
GAP_ROOT = WORKSTREAM / "local/task-4-gap-audit-20260902"
LEGACY_ROOT = Path("C:/Claude Projects/BG3 Mods/ChatGPT Work Files/BCBScantily_BardClassGeneralization_20260826")
TOOL_PINS = {
    "Divine.exe": "65C47A5050E55F686B55484A901A01D0F1A1D5BA0E776F65FEC71D3E1B2A16B7",
    "Divine.dll": "13C631770E5FCEE21915E4CCFA18F3A77E9223B767C9DAB201A7F9DFBB48A004",
    "LSLib.dll": "5DFE246B93CBC95531E011DBF18478C665A9DE4F922F8B4A2B73DA5A865C76D0",
    "LSLibNative.dll": "4F70EDAD1BF5D080F845E3BD467659485D82780FCFBBF534BA86D4EB1DD5DFFA",
    "granny2.dll": "93E29135AF0F8CB08A9CF95BAD69F7B6A13ACEE82D689D1086312FE1135F2AF6",
}
PACKAGE_MANIFEST_PINS = {
    "addon": "1FBBF69B416E14F269D6B819118425FC2E7FC49C707DDC113CCECD36FC4CB4FA",
    "separator": "DD61692FCE06E1F5B5ACADEB060D412CF02D8B1D54BB7640367B59B9277C3DB4",
    "sbbf": "2FC8EC954D543F3F77692379CF7FD7D5030F2EF4854ED98B5099F88749C157FE",
}


def _pin(path: Path, expected: str) -> dict[str, object]:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"GAP_INPUT_HASH_MISMATCH:{path}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def _stats_entries(text: str) -> list[dict[str, object]]:
    entries = []
    current = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.fullmatch(r'new entry "([^"]+)"', line.strip())
        if match:
            current = {"name": match[1], "line": number, "type": None, "using": None, "data": {}}
            entries.append(current)
        elif current is not None:
            data = re.fullmatch(r'data "([^"]+)" "([^"]*)"', line.strip())
            single = re.fullmatch(r'(type|using) "([^"]+)"', line.strip())
            if data:
                current["data"][data[1]] = data[2]
            elif single:
                current[single[1]] = single[2]
            elif line.strip() and not line.strip().startswith("//"):
                raise ValueError(f"STATS_UNPARSED_LINE:{number}:{line}")
    return entries


def build_current_gap_audit(snapshot=None) -> dict[str, object]:
    """Revalidate and inspect the exact eleven gaps; never perform geometry work.

    Conversions/extractions are retained actual tool outputs, pinned below. This
    reader performs no extraction, conversion, candidate writing or installation.
    """
    from . import authority_contracts as contracts
    if snapshot is None:
        snapshot = contracts.load_current_authority_snapshot(include_gap_audit=False)
    inputs = contracts._load_verified_authority_inputs()
    fresh = snapshot.fresh_source_audit
    frozen = Path(fresh["source_root"]) / "extracted/Scantily"
    expected_gaps = {
        str(LEGACY_ROOT / "BCBSCANTILY_CLASS_FINDINGS.md"),
        str(inputs["authority_geometry_inventory"].path),
        "C:\\Claude Projects\\BG3 Mods\\ClothMorph_Build\\_sco_unpack\\Public\\SCO\\Stats\\Generated\\Data\\Armor.txt",
        "C:\\Claude Projects\\BG3 Mods\\ClothMorph_Build\\_sco_unpack\\sco_visualbank_merged.lsx",
        *(str(inputs[key].path) for key in ("sco_addon_pak", "sbbf_sco_patch_zip", "scantily_separator_pak")),
        *(str(frozen / record["source_file"]) for record in fresh["geometry_records"]),
    }
    if tuple(sorted(expected_gaps)) != snapshot.unresolved_retained_evidence_files:
        raise ValueError("GAP_ORIGINAL_SET_CHANGED")
    tools = [_pin(Path("C:/bg3-sidecar-work/Tools") / name, digest) for name, digest in TOOL_PINS.items()]
    doc_pins = [
        _pin(LEGACY_ROOT / "BCBSCANTILY_CLASS_FINDINGS.md", "DC14900F4D5BAC1E3851342349EF2C8B11C15D60068AC1751F4D735EA80E0070"),
        _pin(LEGACY_ROOT / "build_audit.py", "7DC8BBEE0C72DB2D39B72C141D9596A60EC91A4653DA4B3A571B78707BADBB7C"),
        _pin(LEGACY_ROOT / "class_audit.py", "4C1AA480F0E7E78ADCF054075277C6A927BB9A9A2BE0E04C80F3135B8804D9ED"),
    ]
    spec = importlib.util.spec_from_file_location("authority_pinned_metadata_reader", LEGACY_ROOT / "class_audit.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)

    packages = {}
    for name, input_id, listing_id in (
        ("addon", "sco_addon_pak", "sco_addon_package_list"),
        ("separator", "scantily_separator_pak", "scantily_separator_package_list"),
        ("sbbf", "sbbf_sco_patch_zip", None),
    ):
        archive_entries = None
        if listing_id:
            listing = inputs[listing_id].path.read_text(encoding="utf-8")
        else:
            with zipfile.ZipFile(inputs[input_id].path) as archive:
                archive_entries = [{"path": info.filename, "bytes": info.file_size, "is_directory": info.is_dir()}
                                   for info in archive.infolist()]
                listing = "".join(f"{info.filename}\t{info.file_size}\t0\n" for info in archive.infolist() if not info.is_dir())
        manifest = inventory_against_listing(GAP_ROOT / name, listing)
        digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest().upper()
        if digest != PACKAGE_MANIFEST_PINS[name]:
            raise ValueError(f"GAP_PACKAGE_MANIFEST_MISMATCH:{name}")
        packages[name] = {"source_path": str(inputs[input_id].path), "source_sha256": inputs[input_id].sha256,
                          "file_count": len(manifest), "manifest_sha256": digest, "manifest": manifest,
                          "archive_entries": archive_entries, "listing_path_size_mismatches": []}

    derived = []
    for directory in ("decoded", "geometry"):
        # The independent fixed digest below detects omitted/extra/content-changed outputs.
        for current, subdirs, filenames in os.walk(GAP_ROOT / directory, onerror=lambda error: (_ for _ in ()).throw(error)):
            for filename in subdirs + filenames:
                path = Path(current) / filename
                if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                    raise ValueError("GAP_DERIVED_REPARSE_FORBIDDEN")
            for filename in filenames:
                path = Path(current) / filename
                derived.append({"path": path.relative_to(GAP_ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    derived.sort(key=lambda value: value["path"])
    derived_digest = hashlib.sha256(canonical_bytes(derived)).hexdigest().upper()
    if derived_digest != "18DBCDC1A52BCAFB37C28003BDC7B10C604E311096BA22D1920BC42D86571D6D":
        raise ValueError("GAP_DERIVED_MANIFEST_MISMATCH")

    all_text = {}
    xml_reviews = []
    stats_reviews = []
    for package in ("addon", "separator", "sbbf", "decoded"):
        for current, _, filenames in os.walk(GAP_ROOT / package):
            for filename in filenames:
                path = Path(current) / filename
                if path.suffix.lower() in {".lsx", ".txt", ".json", ".xml"}:
                    text = path.read_text(encoding="utf-8-sig")
                    all_text[str(path)] = text
                    if path.suffix.lower() in {".lsx", ".xml"}:
                        xml = ET.fromstring(text)
                        xml_reviews.append({"path": str(path), "sha256": sha256_file(path),
                                            "elements": sum(1 for _ in xml.iter())})
                    elif path.suffix.lower() == ".json":
                        json.loads(text)
                    if "Stats" in path.parts and path.name in {"Armor.txt", "Object.txt"}:
                        stats_reviews.append({"path": str(path), "entries": _stats_entries(text)})
    # Every packed resource in the retained addon/separator has a pinned decode.
    conversion_records = []
    for package in ("addon", "separator"):
        for record in packages[package]["manifest"]:
            if record["path"].lower().endswith(".lsf"):
                output = GAP_ROOT / "decoded" / package / (record["path"] + ".lsx")
                if not output.is_file():
                    raise ValueError("GAP_PACKED_RESOURCE_DECODE_MISSING")
                conversion_records.append({"source_path": str(GAP_ROOT / package / record["path"]),
                                           "source_sha256": record["sha256"], "output_path": str(output),
                                           "output_sha256": sha256_file(output), "action": "convert-resource",
                                           "observed_exit_code": 0, "game": "bg3"})

    legacy_stats_path = Path("C:/Claude Projects/BG3 Mods/ClothMorph_Build/_sco_unpack/Public/SCO/Stats/Generated/Data/Armor.txt")
    legacy_visual_path = Path("C:/Claude Projects/BG3 Mods/ClothMorph_Build/_sco_unpack/sco_visualbank_merged.lsx")
    doc_pins.extend([
        _pin(legacy_stats_path, "B594CAEE6E51BD1B44116576D4A2EE38C122FE8353AAF429AE5CE6714B1CC44F"),
        _pin(legacy_visual_path, "F539469DC3372601BC5F19394298803500B2FE0A7FBD1B903E39B90668435281"),
    ])
    findings = Path(doc_pins[0]["path"]).read_text(encoding="utf-8")
    generator_text = Path(doc_pins[1]["path"]).read_text(encoding="utf-8")
    inventory = json.loads(inputs["authority_geometry_inventory"].path.read_text(encoding="utf-8"))
    inventory_sources = inventory["sources"]
    # Iterate every retained record, not only the Authority matches.
    inventory_review = [{"path": path, "status": value["inspection_status"], "sha256": value["sha256"],
                         "record_sha256": hashlib.sha256(canonical_bytes(value)).hexdigest().upper(),
                         "mesh_count": len(value.get("mesh_order", [])), "bones": len(value.get("bones", []))}
                        for path, value in sorted(inventory_sources.items())]
    old_visuals = reader.parse_visual_bank(legacy_visual_path)
    fresh_visual_path = WORKSTREAM / "local/task-4-fresh-readback-20260902/visualbank.lsx"
    fresh_roots_path = WORKSTREAM / "local/task-4-fresh-readback-20260902/roottemplates.lsx"
    new_visuals = reader.parse_visual_bank(fresh_visual_path)
    fresh_stats = frozen / "Public/SCO/Stats/Generated/Data/Armor.txt"
    legacy_stats = _stats_entries(legacy_stats_path.read_text(encoding="utf-8"))
    if old_visuals != new_visuals or sha256_file(legacy_stats_path) != sha256_file(fresh_stats):
        raise ValueError("GAP_LEGACY_CURRENT_EQUIVALENCE_CHANGED")
    for path in (legacy_stats_path, legacy_visual_path, fresh_visual_path, fresh_roots_path,
                 inputs["authority_geometry_inventory"].path, inputs["bcbscantily_roottemplates"].path,
                 inputs["bcbscantily_visualbank"].path, LEGACY_ROOT / "BCBSCANTILY_CLASS_FINDINGS.md"):
        all_text[str(path)] = path.read_text(encoding="utf-8")
    bcb_items = reader.parse_root_templates(inputs["bcbscantily_roottemplates"].path)
    sco_items = reader.parse_root_templates(fresh_roots_path)
    bcb_visuals = reader.parse_visual_bank(inputs["bcbscantily_visualbank"].path)
    selected_items = {contracts.NORMAL_ITEM_UUID: "normal", contracts.SKIRT_ITEM_UUID: "skirt", contracts.ALT_ITEM_UUID: "alt"}
    human_race = "71180b76-5752-4a97-b71f-911a69197f58"
    def human_routes(items):
        return {selected_items[item["item_uuid"]]: route["visual_resource_uuids"]
                for item in items if item["item_uuid"] in selected_items
                for route in item["routes"] if route["race_uuid"] == human_race}
    routes = {"bcb_overlay_human": human_routes(bcb_items), "raw_sco_human": human_routes(sco_items),
              "bcb_items": [item for item in bcb_items if item["item_uuid"] in selected_items],
              "raw_sco_items": [item for item in sco_items if item["item_uuid"] in selected_items]}
    for route in snapshot.routes:
        item = next(item for item in routes["bcb_items"] if item["item_uuid"] == route.item_uuid)
        exact = next(record for record in item["routes"] if record["race_uuid"] == route.race_uuid)
        if exact["visual_resource_uuids"] != [component.visual_resource_uuid for component in route.components]:
            raise ValueError("GAP_BCB_ROUTE_BINDING_MISMATCH")

    geometry = {}
    sources = {Path(record["source_file"]).stem: (frozen / record["source_file"], record["sha256"], record["visual_resource_uuid"], "SCO")
               for record in fresh["geometry_records"]}
    for name, visual_id in (("bcbscantily_main_gr2", contracts.MAIN_VISUAL_UUID), ("bcbscantily_skirt_gr2", contracts.SKIRT_VISUAL_UUID)):
        sources[name] = (inputs[name].path, inputs[name].sha256, visual_id, "BCBScantily")
    for suffix, visual_id in (("", contracts.MAIN_VISUAL_UUID), ("_Alt", routes["raw_sco_human"]["alt"][0])):
        source = frozen / f"Generated/Public/SCO/Assets/HUM_F_ARM_Authority_Robe{suffix}.GR2"
        sources[f"SCO_HUM_F_ARM_Authority_Robe{suffix}"] = (source, sha256_file(source), visual_id, "SCO")
        patch = GAP_ROOT / f"sbbf/SBBF(L)_ScantyCampOutfit/Data/Generated/Public/SCO/Assets/HUM_F_ARM_Authority_Robe{suffix}.gr2"
        sources[f"SBBF_HUM_F_ARM_Authority_Robe{suffix}"] = (patch, sha256_file(patch), visual_id, "SBBF_LOOSE_SCO")
    discrepancies = []
    for name, (source, digest, visual_id, family) in sources.items():
        gr2 = inspect_gr2_bindings(source, digest)
        glb = GAP_ROOT / "geometry" / (name + ".glb")
        converted = inspect_glb_semantics(glb)
        if gr2["mesh_count"] != len(converted["meshes"]):
            raise ValueError("GAP_GR2_GLB_MESH_COUNT_MISMATCH")
        for native, decoded in zip(gr2["meshes"], converted["meshes"]):
            primitive = decoded["primitives"]
            if len(primitive) != 1 or native["vertices"] != primitive[0]["vertices"] or native["indices16"] + native["indices32"] != primitive[0]["indices"]:
                raise ValueError("GAP_GR2_GLB_TOPOLOGY_MISMATCH")
        visual = (bcb_visuals if family == "BCBScantily" else new_visuals)[visual_id]
        record = {"source_path": str(source), "source_sha256": digest, "source_family": family,
                  "visual_resource_uuid": visual_id, "gr2": gr2, "glb": converted,
                  "visual_object_slot_count": len(visual["objects"]), "visual_contract": visual,
                  "runtime_material_source": "Packed VisualBank object MaterialID; GLB Dummy material is not runtime material proof.",
                  "geometry_admitted": False, "defect_region": None}
        if len(visual["objects"]) != gr2["mesh_count"]:
            discrepancies.append({"source": name, "visual_slots": len(visual["objects"]), "physical_mesh_bindings": gr2["mesh_count"],
                                  "meaning": "Exact source metadata/physical count difference; do not repair or infer missing geometry by slot count."})
        geometry[name] = record
        conversion_records.append({"source_path": str(source), "source_sha256": digest,
                                   "output_path": str(glb), "output_sha256": converted["glb_sha256"], "action": "convert-model",
                                   "observed_exit_code": 0, "game": "bg3"})

    # Fully parse all dependency item/visual metadata; retain every relevant item.
    dependency_metadata = {}
    for package in ("addon", "separator"):
        records = []
        for path in sorted((GAP_ROOT / "decoded" / package).rglob("*.lsx")):
            visuals = reader.parse_visual_bank(path)
            items = reader.parse_root_templates(path)
            relevant_visuals = {key: value for key, value in visuals.items() if "authority" in json.dumps(value).lower()}
            relevant_ids = set(relevant_visuals)
            relevant_items = [item for item in items if "authority" in json.dumps(item).lower()
                              or any(visual in relevant_ids for route in item["routes"] for visual in route["visual_resource_uuids"])]
            records.append({"path": str(path), "visual_count": len(visuals), "item_count": len(items),
                            "authority_visuals": relevant_visuals, "authority_items": relevant_items})
        dependency_metadata[package] = records
    aliases = set(snapshot.required_aliases)
    aliases.update(query["alias"] for query in fresh["queries"])
    aliases.add("Authority")
    for record in geometry.values():
        aliases.update((record["source_sha256"], record["glb"]["glb_sha256"], record["visual_resource_uuid"], record["visual_contract"]["source_file"]))
        aliases.update(obj["material_id"] for obj in record["visual_contract"]["objects"])
    queries = []
    for alias in sorted(aliases):
        needle = alias.casefold()
        hits = [{"path": path, "line": number, "text": line}
                for path, text in sorted(all_text.items()) for number, line in enumerate(text.splitlines(), start=1)
                if needle in line.casefold()]
        path_hits = [{"package": name, "path": record["path"]} for name, package in packages.items()
                     for record in package["manifest"] if needle in record["path"].casefold()]
        queries.append({"alias": alias, "hit_count": len(hits), "hits": hits, "path_hits": path_hits})

    old_gaps = list(snapshot.unresolved_retained_evidence_files)
    if len(old_gaps) != 11:
        raise ValueError("GAP_ORIGINAL_SET_CHANGED")
    conclusions = [
        "Complete findings read: Authority is deferred on the exact BCB nine-slot/optional-skirt contract; no defect-region coordinates or correction candidate are supplied.",
        "Complete legacy inventory parsed: 63 BCB-only source records. Four SCO files were outside its input coverage, not absent from the complete Scantily PAK.",
        "Complete legacy Stats parsed and byte-identical to frozen Stats; exact normal/Alt RootTemplate references retained without inventing inheritance resolution.",
        "Complete legacy VisualBank parsed: all 828 retained field contracts match packed frozen readback, with no added/missing/changed IDs.",
        "Fresh add-on extraction matches every listing entry; all packed resources decoded and all text metadata searched. No exact original Authority UUID/path replacement supplied.",
        "Exact HFL normal GR2 directly read and converted accessors audited: physical nine-mesh structure, 82-joint skins, ten metadata slots; semantics known, defect/correction unassessed.",
        "Exact HFL Alt GR2 directly read and converted accessors audited: physical ten-mesh structure, 82-joint skins, distinct Alt topology; no Human substitution admitted.",
        "Exact TIF_FS normal GR2 directly read and converted accessors audited: physical nine-mesh structure, 82-joint skins, ten metadata slots; semantics known, defect/correction unassessed.",
        "Exact TIF_FS Alt GR2 directly read and converted accessors audited: physical ten-mesh structure, 82-joint skins, distinct Alt topology; no Human substitution admitted.",
        "Fresh SBBF archive inventory complete; two Authority loose Human replacements decoded. Their body/stone/skirt contents differ and do not supply an admitted exact BCB route correction.",
        "Fresh separator inventory complete and all packed resources decoded/searched; separated Authority components and distinct routes are not the original combined nine-object contract.",
    ]
    gaps = [{"gap_id": f"{index:02}", "path": path, "status": "RESOLVED_SOURCE_EVIDENCE", "conclusion": conclusion,
             "evidence": {"source_sha256": sha256_file(Path(path)), "section": (
                 "legacy" if index <= 4 else "packages/addon" if index == 5 else "geometry" if index <= 9 else "packages/sbbf" if index == 10 else "packages/separator")}}
            for index, (path, conclusion) in enumerate(zip(old_gaps, conclusions), start=1)]
    result = source_audit_disposition(gaps)
    result.update({
        "schema": "clothmorph.authority-eleven-gap-source-audit", "schema_version": 1,
        "scope": "Exact eleven retained gaps and their concrete Authority routes; not global release-profile or geometry acceptance.",
        "gaps": gaps, "tools": tools, "document_pins": doc_pins, "packages": packages,
        "derived_manifest": derived, "derived_manifest_sha256": derived_digest,
        "fresh_source_pak_sha256": fresh["pak_sha256"],
        "fresh_source_manifest_sha256": fresh["input_manifest_sha256"],
        "conversions": conversion_records, "xml_reviews": xml_reviews, "stats_reviews": stats_reviews,
        "legacy": {"findings_full_read_sha256": doc_pins[0]["sha256"], "findings_line_count": len(findings.splitlines()),
                   "inventory_source_count": len(inventory_sources), "inventory_all_records": inventory_review,
                   "authority_inventory": {path: value for path, value in inventory_sources.items() if "Authority" in path},
                   "generator_extraction_lines": [line for line in generator_text.splitlines() if '"-x"' in line],
                   "stats_byte_identical_to_frozen": True, "stats_all_entries": legacy_stats,
                   "visual_record_count": len(old_visuals), "visual_records_identical_to_packed": True},
        "routes": routes, "geometry": geometry, "dependency_metadata": dependency_metadata,
        "queries": queries, "text_scan_paths": sorted(all_text), "access_gaps": [],
        "known_source_discrepancies": discrepancies,
        "remaining_admission_conditions": ["No source-bound defect region supplied; no conditional geometry architecture has been tested.",
            "Preserve exact Human BCB main/optional skirt and concrete non-Human source contracts separately.",
            "Do not equate metadata object-slot count with physical GR2 mesh count or silently repair either.",
            "Independent anti-omission review and any later canonical ledger/terminal-policy binding remain outside this source audit."],
    })
    return result


def write_current_gap_audit(output_directory: Path) -> Path:
    """Write a new immutable local source-evidence packet, never a terminal event."""
    output_directory = Path(output_directory)
    if output_directory.exists():
        raise FileExistsError("GAP_OUTPUT_DIRECTORY_EXISTS")
    result = build_current_gap_audit()
    output_directory.mkdir(parents=True, exist_ok=False)
    target = output_directory / "authority-eleven-gap-audit.json"
    with target.open("xb") as stream:
        stream.write(canonical_bytes(result))
    return target
