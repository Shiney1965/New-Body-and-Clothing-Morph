"""Read explicitly configured, hash-pinned source evidence without source mutation.

Configuration has ``root`` (an explicitly chosen local directory), ``profile_id``,
``role`` (source/garment_source/provider/runtime/dependency), ``module`` with exact uuid,
folder, name and version64, ``metadata_path`` relative to the extraction, and:

* package: {path, sha256, recorded_path}
* extract_root: {path, recorded_path}
* content_manifest / listing: {path, sha256}
* tool_sha256: the pinned extraction/conversion executable digest
* conversions: [{manifest: {path, sha256},
                 inspection_root: {path, recorded_path}}]

All ``path`` values are canonical relative paths below root. ``recorded_path``
values are provenance labels from the frozen evidence, not paths to open. This
permits relocation without following an old machine's absolute/live paths. The
neutral ``source`` role nominates source evidence without asserting garment
content. Neither source role grants route eligibility or release authority. The
role is an explicit declaration bound to the expected module identity; a file
name or Add-On metadata type cannot establish garment/provider semantics.

The supported retained manifests are source-content-manifest v1 and
source-bank-conversion-evidence v1. The full listing is Divine's tab-separated
path, byte count and opaque integer field. Configuration pins its exact
bytes independently. This reader checks retained extraction evidence; it does
not execute Divine, decompress PAKs, or turn provenance into permission proof.
Conversions in a shared manifest belonging to other extraction roots are not
opened. Every conversion belonging to this extraction is verified, without a
caller-selectable row allowlist. Unsupported conversion formats fail closed.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
from uuid import UUID
import xml.etree.ElementTree as ET


class SnapshotError(ValueError):
    """Stable machine-readable refusal, independent of host error wording."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class FileSnapshot:
    relative_path: str
    locator: str
    sha256: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class PackageIdentity:
    locator: str
    recorded_path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class DependencyMetadata:
    uuid: str
    folder: str
    name: str
    version64: str
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ModuleMetadata:
    uuid: str
    folder: str
    name: str
    version64: str
    attributes: tuple[tuple[str, str], ...]
    dependencies: tuple[DependencyMetadata, ...]
    relative_path: str


@dataclass(frozen=True)
class ConversionSnapshot:
    source_relative_path: str
    source_sha256: str
    inspection: FileSnapshot
    manifest_sha256: str
    manifest_row: int
    tool_sha256: str
    tool_arguments: tuple[str, ...]


@dataclass(frozen=True)
class FrozenSnapshot:
    profile_id: str
    role: str
    module: ModuleMetadata
    package: PackageIdentity
    content_manifest: FileSnapshot
    listing: FileSnapshot
    files: tuple[FileSnapshot, ...]
    conversion_manifests: tuple[FileSnapshot, ...]
    conversions: tuple[ConversionSnapshot, ...]
    unconverted_binary_paths: tuple[str, ...]


_HASH = re.compile(r"[0-9A-Fa-f]{64}\Z")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)
_CONVERT_ARGS = ("-g", "bg3", "-a", "convert-resource", "-s", "{source}",
                 "-d", "{inspection}", "-i", "lsf", "-o", "lsx")


def _fail(code, detail):
    raise SnapshotError(code, detail)


def _text(value, code="CONFIG_INVALID"):
    if not isinstance(value, str) or not value or value.strip() != value or "\x00" in value:
        _fail(code, "Expected a nonempty exact string")
    return value


def _mapping(value, code="CONFIG_INVALID"):
    if not isinstance(value, Mapping):
        _fail(code, "Expected an object")
    return value


def _sequence(value, code="CONFIG_INVALID"):
    if not isinstance(value, (list, tuple)):
        _fail(code, "Expected an ordered array")
    return value


def _digest(value, code="CONFIG_INVALID"):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _fail(code, "Expected a SHA-256 digest")
    return value.upper()


def _relative(value):
    value = _text(value, "UNSAFE_PATH")
    if "\\" in value or value.startswith("/"):
        _fail("UNSAFE_PATH", value)
    for part in value.split("/"):
        if (part in ("", ".", "..") or part.endswith((".", " ")) or _RESERVED.fullmatch(part)
                or any(ord(char) < 32 or char in '<>:"|?*' for char in part)):
            _fail("UNSAFE_PATH", value)
    return value


def _check_link(path):
    try:
        info = path.lstat()
    except OSError as error:
        _fail("FILE_UNAVAILABLE", str(error))
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        _fail("UNSAFE_PATH", f"Links and reparse points are not allowed: {path}")
    return info


def _path(root, relative):
    relative = _relative(relative)
    candidate = root
    for component in relative.split("/"):
        candidate = candidate / component
        _check_link(candidate)
    try:
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        _fail("UNSAFE_PATH", str(error))
    return candidate


def _read(root, descriptor):
    descriptor = _mapping(descriptor)
    relative = _relative(descriptor.get("path"))
    expected = _digest(descriptor.get("sha256"))
    path = _path(root, relative)
    try:
        data = path.read_bytes()
    except OSError as error:
        _fail("FILE_UNAVAILABLE", str(error))
    actual = sha256(data).hexdigest().upper()
    if actual != expected:
        _fail("HASH_MISMATCH", relative)
    return FileSnapshot(relative, str(path), actual, data)


def _package(root, descriptor):
    descriptor = _mapping(descriptor)
    path = _path(root, descriptor.get("path"))
    expected = _digest(descriptor.get("sha256"))
    hasher = sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
                size += len(chunk)
    except OSError as error:
        _fail("FILE_UNAVAILABLE", str(error))
    if hasher.hexdigest().upper() != expected:
        _fail("HASH_MISMATCH", str(path))
    return PackageIdentity(str(path), _text(descriptor.get("recorded_path")), expected, size)


def _json(artifact, schema):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("MANIFEST_INVALID", f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(artifact.data.decode("utf-8-sig"), object_pairs_hook=unique)
    except (UnicodeError, ValueError) as error:
        if isinstance(error, SnapshotError):
            raise
        _fail("MANIFEST_INVALID", str(error))
    _mapping(value, "MANIFEST_INVALID")
    if value.get("schema") != schema or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        _fail("MANIFEST_INVALID", "Unsupported manifest schema/version")
    return value


def _paths_unique(paths):
    seen = set()
    prefixes = {}
    for path in paths:
        _relative(path)
        if path.casefold() in seen:
            _fail("PATH_COLLISION", path)
        seen.add(path.casefold())
        parts = path.split("/")
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            previous = prefixes.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                _fail("PATH_COLLISION", f"{previous} / {prefix}")


def _listing(artifact):
    rows = []
    try:
        lines = artifact.data.decode("utf-8-sig").splitlines()
    except UnicodeError as error:
        _fail("LISTING_INVALID", str(error))
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 3 or not re.fullmatch(r"[0-9]+", fields[1]) or not re.fullmatch(r"[0-9]+", fields[2]):
            _fail("LISTING_INVALID", "Expected path, size and opaque integer on every line")
        rows.append((_relative(fields[0]), int(fields[1])))
    _paths_unique(path for path, _ in rows)
    return dict(rows)


def _filesystem(root):
    paths = []

    def visit(directory):
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as error:
            _fail("FILE_UNAVAILABLE", str(error))
        for child in children:
            info = _check_link(child)
            if stat.S_ISDIR(info.st_mode):
                visit(child)
            elif stat.S_ISREG(info.st_mode):
                paths.append(child.relative_to(root).as_posix())
            else:
                _fail("UNSAFE_PATH", f"Not a regular file/directory: {child}")

    visit(root)
    _paths_unique(paths)
    return set(paths)


def _attributes(node):
    result = []
    seen = set()
    for attr in node.findall("attribute"):
        key = _text(attr.get("id"), "METADATA_INVALID")
        value = attr.get("value")
        if key in seen or not isinstance(value, str):
            _fail("METADATA_INVALID", "Duplicate or valueless metadata attribute")
        seen.add(key)
        result.append((key, value))
    return tuple(result)


def _identity(attributes):
    values = dict(attributes)
    identity = tuple(_text(values.get(name), "METADATA_INVALID") for name in ("UUID", "Folder", "Name", "Version64"))
    try:
        if str(UUID(identity[0])) != identity[0].lower():
            raise ValueError("UUID must use canonical hyphenated syntax")
    except ValueError as error:
        _fail("METADATA_INVALID", str(error))
    if not re.fullmatch(r"[0-9]+", identity[3]) or not 0 <= int(identity[3]) <= 2**63 - 1:
        _fail("METADATA_INVALID", "Invalid Version64")
    return identity


def _metadata(file, expected):
    # DTD/entity declarations are unnecessary in BG3 metadata and fail closed.
    try:
        text = file.data.decode("utf-8-sig")
    except UnicodeError as error:
        _fail("METADATA_INVALID", str(error))
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        _fail("METADATA_INVALID", "DTD/entity declarations are not permitted")
    try:
        tree = ET.fromstring(text)
    except ET.ParseError as error:
        _fail("METADATA_INVALID", str(error))
    modules = tree.findall("./region[@id='Config']/node[@id='root']/children/node[@id='ModuleInfo']")
    dependencies = tree.findall("./region[@id='Config']/node[@id='root']/children/node[@id='Dependencies']")
    if len(modules) != 1 or len(dependencies) != 1:
        _fail("METADATA_INVALID", "Exactly one ModuleInfo and Dependencies node required")
    attributes = _attributes(modules[0])
    identity = _identity(attributes)
    expected_identity = tuple(_text(expected.get(key)) for key in ("uuid", "folder", "name", "version64"))
    if identity != expected_identity:
        _fail("MODULE_IDENTITY_MISMATCH", file.relative_path)
    if file.relative_path != f"Mods/{identity[1]}/meta.lsx":
        _fail("MODULE_IDENTITY_MISMATCH", "Metadata folder disagrees with packed path")
    ordered = []
    containers = list(dependencies[0])
    if len(containers) > 1 or any(child.tag != "children" for child in containers):
        _fail("METADATA_INVALID", "Unexpected dependency structure")
    if containers and any(child.tag != "node" for child in containers[0]):
        _fail("METADATA_INVALID", "Unexpected dependency entry structure")
    for dependency in dependencies[0].findall("./children/node"):
        if dependency.get("id") != "ModuleShortDesc" or any(child.tag != "attribute" for child in dependency):
            _fail("METADATA_INVALID", "Unknown dependency record")
        dep_attributes = _attributes(dependency)
        ordered.append(DependencyMetadata(*_identity(dep_attributes), dep_attributes))
    return ModuleMetadata(*identity, attributes, tuple(ordered), file.relative_path)


def _label_relative(label, prefix):
    # These labels are compared lexically only. Never use resolve()/open().
    label = _text(label, "MANIFEST_INVALID").replace("\\", "/")
    prefix = _text(prefix, "MANIFEST_INVALID").replace("\\", "/").rstrip("/")
    if not label.startswith(prefix + "/"):
        return None
    return _relative(label[len(prefix) + 1:])


def _conversions(root, configs, files, extract_label, tool):
    by_path = {file.relative_path: file for file in files}
    manifests, converted = [], []
    used_sources, used_outputs = set(), set()
    for config in _sequence(configs):
        config = _mapping(config)
        artifact = _read(root, config.get("manifest"))
        manifest = _json(artifact, "clothmorph.source-bank-conversion-evidence")
        provenance = _mapping(manifest.get("tool"), "MANIFEST_INVALID")
        if (provenance.get("sha256") != tool or tuple(_sequence(provenance.get("arguments"), "MANIFEST_INVALID")) != _CONVERT_ARGS):
            _fail("CONVERTER_MISMATCH", artifact.relative_path)
        inspection_root = _mapping(config.get("inspection_root"))
        inspection_path = _path(root, inspection_root.get("path"))
        inspection_label = _text(inspection_root.get("recorded_path"))
        matched = 0
        for index, row in enumerate(_sequence(manifest.get("conversions"), "MANIFEST_INVALID")):
            row = _mapping(row, "MANIFEST_INVALID")
            source = _label_relative(row.get("source"), extract_label)
            if source is None:
                continue
            matched += 1
            original = by_path.get(source)
            if (original is None or not source.lower().endswith(".lsf")
                    or original.sha256 != _digest(row.get("source_sha256"), "MANIFEST_INVALID")):
                _fail("CONVERSION_SOURCE_MISMATCH", source)
            output = _label_relative(row.get("inspection"), inspection_label)
            if output is None:
                _fail("CONVERSION_OUTPUT_MISMATCH", source)
            if not output.lower().endswith(".lsx"):
                _fail("CONVERSION_OUTPUT_MISMATCH", output)
            inspection = _read(inspection_path, {"path": output, "sha256": row.get("inspection_sha256")})
            output_key = inspection.locator.casefold()
            if source.casefold() in used_sources or output_key in used_outputs:
                _fail("CONVERSION_DUPLICATE", source)
            used_sources.add(source.casefold())
            used_outputs.add(output_key)
            converted.append(ConversionSnapshot(source, original.sha256, inspection,
                                                artifact.sha256, index, tool, _CONVERT_ARGS))
        if not matched:
            _fail("CONVERSION_SOURCE_MISMATCH", "Configured conversion manifest has no rows for this source")
        manifests.append(artifact)
    return tuple(manifests), tuple(converted)


def load_snapshot(configuration: Mapping[str, object]) -> FrozenSnapshot:
    """Verify a single exact source profile and retain immutable parsing inputs.

    Missing conversion coverage remains explicit in unconverted_binary_paths.
    Success is byte-evidence verification, not source-profile/release completion.
    """
    config = _mapping(configuration)
    try:
        raw_root = Path(config["root"])
        if not raw_root.is_absolute():
            _fail("CONFIG_INVALID", "root must be explicitly absolute")
        # Inspect from the anchor downward before resolve can erase a junction.
        # Checking only raw_root misses an ordinary leaf below a reparse parent.
        for component in (*reversed(raw_root.parents), raw_root):
            _check_link(component)
        root = raw_root.resolve(strict=True)
    except (KeyError, TypeError, OSError) as error:
        _fail("CONFIG_INVALID", str(error))
    if not root.is_dir():
        _fail("CONFIG_INVALID", "root must be a directory")
    profile_id = _text(config.get("profile_id"))
    role = _text(config.get("role"))
    if role not in ("source", "garment_source", "provider", "runtime", "dependency"):
        _fail("CONFIG_INVALID", "Unknown explicit package role")
    tool = _digest(config.get("tool_sha256"))
    expected_module = _mapping(config.get("module"))
    package = _package(root, config.get("package"))
    content = _read(root, config.get("content_manifest"))
    listing = _read(root, config.get("listing"))
    extraction = _mapping(config.get("extract_root"))
    extraction_path = _path(root, extraction.get("path"))
    extraction_label = _text(extraction.get("recorded_path"))
    manifest = _json(content, "clothmorph.source-content-manifest")
    if (manifest.get("pak_sha256") != package.sha256 or manifest.get("pak_path") != package.recorded_path
            or manifest.get("extract_root") != extraction_label or manifest.get("tool_sha256") != tool):
        _fail("MANIFEST_BINDING_MISMATCH", content.relative_path)
    rows = _sequence(manifest.get("files"), "MANIFEST_INVALID")
    if type(manifest.get("file_count")) is not int or manifest["file_count"] != len(rows):
        _fail("MANIFEST_INVALID", "Incorrect file count")
    entries = []
    for row in rows:
        row = _mapping(row, "MANIFEST_INVALID")
        path = _relative(row.get("relative_path"))
        if type(row.get("bytes")) is not int or row["bytes"] < 0:
            _fail("MANIFEST_INVALID", "Incorrect byte count")
        entries.append((path, row["bytes"], _digest(row.get("sha256"), "MANIFEST_INVALID")))
    _paths_unique(path for path, _, _ in entries)
    listed = _listing(listing)
    paths = {path for path, _, _ in entries}
    if set(listed) != paths:
        _fail("LISTING_SET_MISMATCH", listing.relative_path)
    if any(listed[path] != size for path, size, _ in entries):
        _fail("LISTING_SIZE_MISMATCH", listing.relative_path)
    if _filesystem(extraction_path) != paths:
        _fail("EXTRACTION_SET_MISMATCH", str(extraction_path))
    files = []
    for path, size, expected_hash in entries:
        file = _read(extraction_path, {"path": path, "sha256": expected_hash})
        if file.size != size:
            _fail("FILE_SIZE_MISMATCH", path)
        files.append(file)
    metadata_path = _relative(config.get("metadata_path"))
    metadata_files = [file for file in files if re.fullmatch(r"Mods/[^/]+/meta\.lsx", file.relative_path, re.I)]
    if not metadata_files or metadata_path not in paths:
        _fail("METADATA_MISSING", metadata_path)
    if len(metadata_files) != 1 or metadata_files[0].relative_path != metadata_path:
        _fail("METADATA_AMBIGUOUS", "Exactly one declared module per snapshot required")
    module = _metadata(metadata_files[0], expected_module)
    conversion_manifests, conversions = _conversions(root, config.get("conversions"), files, extraction_label, tool)
    converted = {entry.source_relative_path for entry in conversions}
    unconverted = tuple(file.relative_path for file in files
                        if file.relative_path.lower().endswith(".lsf") and file.relative_path not in converted)
    if _filesystem(extraction_path) != paths:
        _fail("EXTRACTION_SET_MISMATCH", "Extraction path set changed during verification")
    if _package(root, config.get("package")) != package:
        _fail("HASH_MISMATCH", "Package changed during verification")
    return FrozenSnapshot(profile_id, role, module, package, content, listing, tuple(files),
                          conversion_manifests, conversions, unconverted)
