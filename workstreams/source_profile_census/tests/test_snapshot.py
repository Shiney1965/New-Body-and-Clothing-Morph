"""Portable real-file tests: no installed mod, converter, or source copy required."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import pytest

from workstreams.source_profile_census.snapshot import SnapshotError, load_snapshot


MODULE = {"uuid": "73928ffc-07c0-46ac-8cf4-86a693b0cd92", "folder": "Example",
          "name": "Exact display name", "version64": "72057772279070722"}
META_PATH = "Mods/Example/meta.lsx"
BANK_PATH = "Public/Example/RootTemplates/_merged.lsf"
TOOL = "65C47A5050E55F686B55484A901A01D0F1A1D5BA0E776F65FEC71D3E1B2A16B7"
META = b'''<?xml version="1.0" encoding="utf-8"?>
<save><region id="Config"><node id="root"><children>
<node id="Dependencies"><children>
<node id="ModuleShortDesc"><attribute id="UUID" value="11111111-1111-1111-1111-111111111111"/><attribute id="Folder" value="First"/><attribute id="Name" value="First dependency"/><attribute id="Version64" value="2"/><attribute id="MD5" value=""/></node>
<node id="ModuleShortDesc"><attribute id="UUID" value="22222222-2222-2222-2222-222222222222"/><attribute id="Folder" value="Second"/><attribute id="Name" value="Second dependency"/><attribute id="Version64" value="1"/></node>
</children></node>
<node id="ModuleInfo"><attribute id="UUID" value="73928ffc-07c0-46ac-8cf4-86a693b0cd92"/><attribute id="Folder" value="Example"/><attribute id="Name" value="Exact display name"/><attribute id="Version64" value="72057772279070722"/><attribute id="Type" value="Add-On"/>
<children><node id="PublishVersion"><attribute id="Version64" value="999"/></node></children>
</node></children></node></region></save>'''


def digest(data):
    return sha256(data).hexdigest().upper()


def write(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": relative, "sha256": digest(data)}


def write_json(root, relative, value):
    return write(root, relative, json.dumps(value).encode())


@pytest.fixture
def fixture(tmp_path):
    """Mirrors the retained content/listing/conversion formats, with tiny bytes."""
    package = write(tmp_path, "source.pak", b"synthetic archive boundary fixture")
    package["recorded_path"] = "Z:/frozen/source.pak"
    files = {META_PATH: META, BANK_PATH: b"binary bank fixture\x00\xff"}
    for name, data in files.items():
        write(tmp_path, "extracted/" + name, data)
    manifest = {
        "schema": "clothmorph.source-content-manifest", "schema_version": 1,
        "pak_path": package["recorded_path"], "pak_sha256": package["sha256"],
        "extract_root": "Z:/frozen/extracted", "listing_path_size_verified": True,
        "tool_sha256": TOOL, "file_count": len(files),
        "files": [{"relative_path": name, "bytes": len(data), "sha256": digest(data)}
                  for name, data in files.items()],
    }
    listing = "".join(f"{name}\t{len(data)}\t0\r\n" for name, data in files.items()).encode()
    config = {
        "root": tmp_path, "profile_id": "source-exact-version", "role": "garment_source",
        "module": dict(MODULE), "metadata_path": META_PATH, "package": package,
        "extract_root": {"path": "extracted", "recorded_path": "Z:/frozen/extracted"},
        "content_manifest": write_json(tmp_path, "content.json", manifest),
        "listing": write(tmp_path, "listing.txt", listing), "tool_sha256": TOOL,
        "conversions": [],
    }
    return config, manifest


def update_manifest(config, manifest):
    config["content_manifest"] = write_json(config["root"], "content.json", manifest)


def add_conversion(config):
    data = b'<save><region id="Templates"/></save>'
    write(config["root"], "inspection/bank.lsx", data)
    conversion = {
        "schema": "clothmorph.source-bank-conversion-evidence", "schema_version": 1,
        "tool": {"path": "Z:/not-opened/Divine.exe", "sha256": TOOL,
                 "arguments": ["-g", "bg3", "-a", "convert-resource", "-s", "{source}",
                               "-d", "{inspection}", "-i", "lsf", "-o", "lsx"]},
        "conversions": [{"source": "Z:/frozen/extracted/" + BANK_PATH,
                         "source_sha256": digest(b"binary bank fixture\x00\xff"),
                         "inspection": "Z:/frozen/inspection/bank.lsx",
                         "inspection_sha256": digest(data), "xml_valid": True,
                         "source_unchanged": True}],
    }
    config["conversions"] = [{
        "manifest": write_json(config["root"], "conversion.json", conversion),
        "inspection_root": {"path": "inspection", "recorded_path": "Z:/frozen/inspection"},
    }]
    return conversion


def update_conversion(config, conversion):
    config["conversions"][0]["manifest"] = write_json(config["root"], "conversion.json", conversion)


def rejects(config, code):
    with pytest.raises(SnapshotError) as error:
        load_snapshot(config)
    assert error.value.code == code


def test_valid_snapshot_retains_original_bytes_and_exact_ordered_metadata(fixture):
    config, _ = fixture
    snapshot = load_snapshot(config)
    assert snapshot.module.uuid == MODULE["uuid"]
    assert snapshot.module.folder == "Example"
    assert snapshot.module.name == "Exact display name"
    assert snapshot.module.version64 == "72057772279070722"
    assert tuple(dep.folder for dep in snapshot.module.dependencies) == ("First", "Second")
    assert snapshot.module.dependencies[0].attributes[-1] == ("MD5", "")
    assert tuple(item.relative_path for item in snapshot.files) == (META_PATH, BANK_PATH)
    assert snapshot.files[1].data == b"binary bank fixture\x00\xff"
    assert snapshot.package.sha256 == config["package"]["sha256"]
    assert snapshot.role == "garment_source"
    # File edits after loading cannot change the next parser's inputs.
    (config["root"] / "extracted" / BANK_PATH).write_bytes(b"later drift")
    assert snapshot.files[1].data == b"binary bank fixture\x00\xff"
    with pytest.raises(FrozenInstanceError):
        snapshot.role = "provider"
    with pytest.raises(FrozenInstanceError):
        snapshot.files[0].data = b"forged"


@pytest.mark.parametrize("field", ["package", "listing", "content_manifest"])
def test_changed_pinned_artifact_is_rejected_before_parsing(fixture, field):
    config, _ = fixture
    (config["root"] / config[field]["path"]).write_bytes(b"malformed changed bytes")
    rejects(config, "HASH_MISMATCH")


def test_changed_source_byte_is_rejected(fixture):
    config, _ = fixture
    path = config["root"] / "extracted" / BANK_PATH
    path.write_bytes(path.read_bytes().replace(b"bank", b"BANK"))
    rejects(config, "HASH_MISMATCH")


@pytest.mark.parametrize("action", ["missing", "extra"])
def test_complete_extraction_path_set_is_required(fixture, action):
    config, _ = fixture
    if action == "missing":
        (config["root"] / "extracted" / BANK_PATH).unlink()
    else:
        write(config["root"], "extracted/extra.txt", b"extra")
    rejects(config, "EXTRACTION_SET_MISMATCH")


def test_listing_sizes_must_match_manifest(fixture):
    config, _ = fixture
    # Explicitly set the first row's size; independent from the fixture's size.
    lines = (config["root"] / "listing.txt").read_text().splitlines()
    lines[0] = META_PATH + "\t1\t0"
    config["listing"] = write(config["root"], "listing.txt", "\n".join(lines).encode())
    rejects(config, "LISTING_SIZE_MISMATCH")


@pytest.mark.parametrize("where", ["manifest", "listing"])
@pytest.mark.parametrize("variant", ["duplicate", "case"])
def test_duplicate_or_case_colliding_source_paths_fail(fixture, where, variant):
    config, manifest = fixture
    path = META_PATH if variant == "duplicate" else META_PATH.upper()
    if where == "manifest":
        manifest["files"].append({**manifest["files"][0], "relative_path": path})
        manifest["file_count"] += 1
        update_manifest(config, manifest)
    else:
        current = (config["root"] / "listing.txt").read_bytes()
        config["listing"] = write(config["root"], "listing.txt", current + f"{path}\t{len(META)}\t0".encode())
    rejects(config, "PATH_COLLISION")


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "C:/live/file", "a/../x",
                                  "a//x", "a/./x", "a\\x", "a/NUL.txt", "a/file.", "a/file:stream"])
def test_unsafe_manifest_paths_fail_without_opening_them(fixture, bad):
    config, manifest = fixture
    manifest["files"][1]["relative_path"] = bad
    update_manifest(config, manifest)
    rejects(config, "UNSAFE_PATH")


@pytest.mark.parametrize("field", ["package", "listing", "content_manifest", "extract_root"])
def test_configuration_paths_cannot_escape_root(fixture, field):
    config, _ = fixture
    config[field]["path"] = "../outside"
    rejects(config, "UNSAFE_PATH")


@pytest.mark.parametrize("key,value", [("uuid", "11111111-1111-1111-1111-111111111111"),
                                      ("version64", "1"), ("folder", "Wrong"), ("name", "Wrong")])
def test_relabelled_profile_identity_rejected(fixture, key, value):
    config, _ = fixture
    config["module"][key] = value
    rejects(config, "MODULE_IDENTITY_MISMATCH")


def test_missing_metadata_is_not_an_empty_module(fixture):
    config, manifest = fixture
    manifest["files"] = manifest["files"][1:]
    manifest["file_count"] = 1
    update_manifest(config, manifest)
    (config["root"] / "extracted" / META_PATH).unlink()
    config["listing"] = write(config["root"], "listing.txt", f"{BANK_PATH}\t{len(b'binary bank fixture' + bytes([0, 255]))}\t0".encode())
    rejects(config, "METADATA_MISSING")


@pytest.mark.parametrize("key", ["pak_path", "extract_root", "pak_sha256", "tool_sha256"])
def test_manifest_must_bind_exact_package_extraction_and_tool(fixture, key):
    config, manifest = fixture
    manifest[key] = "F" * 64 if "sha256" in key else "Z:/other-source"
    update_manifest(config, manifest)
    rejects(config, "MANIFEST_BINDING_MISMATCH")


def test_conversion_retains_exact_verified_source_and_inspection_relation(fixture):
    config, _ = fixture
    add_conversion(config)
    snapshot = load_snapshot(config)
    assert len(snapshot.conversions) == 1
    converted = snapshot.conversions[0]
    assert converted.source_relative_path == BANK_PATH
    assert converted.inspection.data == b'<save><region id="Templates"/></save>'
    assert converted.source_sha256 == digest(b"binary bank fixture\x00\xff")
    assert converted.tool_sha256 == TOOL


@pytest.mark.parametrize("key", ["source_sha256", "inspection_sha256"])
def test_conversion_hash_relation_cannot_be_forged(fixture, key):
    config, _ = fixture
    conversion = add_conversion(config)
    conversion["conversions"][0][key] = "0" * 64
    update_conversion(config, conversion)
    rejects(config, "CONVERSION_SOURCE_MISMATCH" if key == "source_sha256" else "HASH_MISMATCH")


def test_conversion_manifest_is_hash_checked_before_parsing(fixture):
    config, _ = fixture
    add_conversion(config)
    (config["root"] / "conversion.json").write_bytes(b"not JSON")
    rejects(config, "HASH_MISMATCH")


@pytest.mark.parametrize("mutation,code", [
    ("tool", "CONVERTER_MISMATCH"), ("arguments", "CONVERTER_MISMATCH"),
    ("source_missing", "CONVERSION_SOURCE_MISMATCH"), ("escape", "UNSAFE_PATH"),
    ("duplicate", "CONVERSION_DUPLICATE"), ("missing_output", "FILE_UNAVAILABLE"),
])
def test_conversion_cannot_use_unbound_source_tool_or_output(fixture, mutation, code):
    config, _ = fixture
    conversion = add_conversion(config)
    row = conversion["conversions"][0]
    if mutation == "tool":
        conversion["tool"]["sha256"] = "F" * 64
    elif mutation == "arguments":
        conversion["tool"]["arguments"] = ["wrong-action"]
    elif mutation == "source_missing":
        row["source"] = "Z:/frozen/extracted/unknown.lsf"
    elif mutation == "escape":
        row["inspection"] = "Z:/frozen/inspection/../live.lsx"
    elif mutation == "duplicate":
        conversion["conversions"].append(dict(row))
    else:
        (config["root"] / "inspection/bank.lsx").unlink()
    update_conversion(config, conversion)
    rejects(config, code)


def test_no_conversion_does_not_claim_binary_bank_complete(fixture):
    config, _ = fixture
    snapshot = load_snapshot(config)
    assert snapshot.unconverted_binary_paths == (BANK_PATH,)
    assert snapshot.conversions == ()


def test_unknown_role_cannot_be_filename_inferred(fixture):
    config, _ = fixture
    config["role"] = "guess-from-pak"
    rejects(config, "CONFIG_INVALID")


def replace_meta(config, manifest, data):
    write(config["root"], "extracted/" + META_PATH, data)
    manifest["files"][0].update(bytes=len(data), sha256=digest(data))
    update_manifest(config, manifest)
    lines = (config["root"] / "listing.txt").read_text().splitlines()
    lines[0] = f"{META_PATH}\t{len(data)}\t0"
    config["listing"] = write(config["root"], "listing.txt", "\n".join(lines).encode())


@pytest.mark.parametrize("mutation", ["invalid_xml", "missing_version", "duplicate_uuid",
                                      "missing_dependencies", "unknown_dependency", "utf16_dtd",
                                      "hidden_dependency", "dependency_attributes"])
def test_malformed_metadata_cannot_silently_drop_identity_or_dependency(fixture, mutation):
    config, manifest = fixture
    if mutation == "invalid_xml":
        data = b"not XML"
    elif mutation == "missing_version":
        data = META.replace(b'<attribute id="Version64" value="72057772279070722"/>', b"")
    elif mutation == "duplicate_uuid":
        attr = b'<attribute id="UUID" value="73928ffc-07c0-46ac-8cf4-86a693b0cd92"/>'
        data = META.replace(attr, attr + attr)
    elif mutation == "missing_dependencies":
        data = META.replace(b'id="Dependencies"', b'id="NotDependencies"')
    elif mutation == "unknown_dependency":
        data = META.replace(b'id="ModuleShortDesc"', b'id="UnexpectedRecord"')
    elif mutation == "utf16_dtd":
        data = ('<!DOCTYPE save [<!ENTITY x "Exact display name">]>' +
                META.decode().split('?>', 1)[1].replace('Exact display name', '&x;')).encode('utf-16')
    elif mutation == "hidden_dependency":
        data = META.replace(b'<node id="Dependencies"><children>', b'<node id="Dependencies"><hidden>')
        data = data.replace(b'</children></node>\n<node id="ModuleInfo">', b'</hidden></node>\n<node id="ModuleInfo">')
    else:
        data = META.replace(b'<node id="Dependencies"><children>', b'<node id="Dependencies"><attribute id="Dependency" value="hidden"/><children>')
    replace_meta(config, manifest, data)
    rejects(config, "METADATA_INVALID")


@pytest.mark.parametrize("where", ["listing", "manifest"])
def test_missing_discovery_entry_is_not_treated_as_complete(fixture, where):
    config, manifest = fixture
    if where == "listing":
        config["listing"] = write(config["root"], "listing.txt", f"{META_PATH}\t{len(META)}\t0".encode())
    else:
        manifest["files"] = manifest["files"][:1]
        manifest["file_count"] = 1
        update_manifest(config, manifest)
    rejects(config, "LISTING_SET_MISMATCH")


@pytest.mark.parametrize("text", [b"garbage", b"path\tnan\t0", b"path\t1\tx", b"\n"])
def test_unparsed_listing_lines_refuse_the_snapshot(fixture, text):
    config, _ = fixture
    config["listing"] = write(config["root"], "listing.txt", text)
    rejects(config, "LISTING_INVALID")


def test_success_flags_do_not_replace_byte_checks_or_completeness(fixture):
    config, manifest = fixture
    manifest["listing_path_size_verified"] = False
    update_manifest(config, manifest)
    conversion = add_conversion(config)
    conversion["conversions"][0]["xml_valid"] = False
    conversion["conversions"][0]["source_unchanged"] = False
    update_conversion(config, conversion)
    snapshot = load_snapshot(config)
    assert snapshot.files[1].data == b"binary bank fixture\x00\xff"
    assert len(snapshot.conversions) == 1


def test_case_colliding_directories_cannot_hide_behind_distinct_filenames(fixture):
    config, manifest = fixture
    manifest["files"][1]["relative_path"] = "mods/different-file"
    update_manifest(config, manifest)
    rejects(config, "PATH_COLLISION")


def test_opaque_listing_field_is_retained_without_guessing_its_meaning(fixture):
    config, _ = fixture
    listing = (config["root"] / "listing.txt").read_bytes().replace(b"\t0\r\n", b"\t2363048827\r\n")
    config["listing"] = write(config["root"], "listing.txt", listing)
    snapshot = load_snapshot(config)
    assert snapshot.listing.data == listing
    assert len(snapshot.files) == 2


def test_shared_conversion_manifest_never_opens_another_source_path(fixture):
    config, _ = fixture
    conversion = add_conversion(config)
    conversion["conversions"].append({
        "source": "Z:/other-source/extracted/file.lsf", "source_sha256": "0" * 64,
        "inspection": "Z:/not-readable/output.lsx", "inspection_sha256": "0" * 64,
    })
    update_conversion(config, conversion)
    snapshot = load_snapshot(config)
    assert tuple(item.source_relative_path for item in snapshot.conversions) == (BANK_PATH,)


def test_conversion_format_without_pinned_provenance_is_not_assumed_valid(fixture):
    config, _ = fixture
    conversion = add_conversion(config)
    conversion["schema"] = "clothmorph.source-scope-audit"
    conversion.pop("tool")
    update_conversion(config, conversion)
    rejects(config, "MANIFEST_INVALID")
