"""Lossless resource observations over retained, verified package bytes.

No file or converter is opened here. XML definitions keep their full ordered
element trees (including attribute metadata, comments, text and tails); the
original/inspection bytes retain lexical details XML normalizes. Stats keeps
every physical line and every repeated declaration. Nothing selects a winning
duplicate, resolves a route, infers a body mode, or inherits effective values.

``definition_parse_complete`` concerns parsing/ambiguity only. Even a true value
is not source-profile, permission, dependency, route, or release acceptance.
Missing Stats parents are local-census observations; dependency joins belong to
creation_paths, not this parser.
"""

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import xml.etree.ElementTree as ET

from . import snapshot as snapshots
from .snapshot import (
    ConversionSnapshot, FileSnapshot, FrozenSnapshot, ModuleMetadata, PackageIdentity,
)


@dataclass(frozen=True)
class XmlElement:
    tag: str
    attributes: tuple[tuple[str, str], ...]
    text: str | None
    tail: str | None
    children: tuple["XmlElement", ...]
    locator: str


@dataclass(frozen=True)
class StatsStatement:
    command: str
    arguments: tuple[str, ...]
    raw: str
    line: int


@dataclass(frozen=True)
class ResourceSource:
    profile_id: str
    module: ModuleMetadata
    package: PackageIdentity
    original: FileSnapshot
    representation: str
    inspection: FileSnapshot | None = None
    conversion: ConversionSnapshot | None = None


@dataclass(frozen=True)
class ResourceDefinition:
    observation_id: str
    kind: str
    resource_id: str | None
    source: ResourceSource
    locator: str
    node: XmlElement | None = None
    statements: tuple[StatsStatement, ...] = ()
    stats_types: tuple[str, ...] = ()
    stats_parents: tuple[str, ...] = ()
    stats_data: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ResourceIssue:
    code: str
    relative_path: str
    locator: str
    detail: str
    observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceFile:
    source: ResourceSource
    status: str
    document: XmlElement | None = None
    statements: tuple[StatsStatement, ...] = ()
    definition_ids: tuple[str, ...] = ()
    issue_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DefinitionConflict:
    kind: str
    resource_id: str
    observation_ids: tuple[str, ...]
    content_equal: bool
    precedence: str = "UNRESOLVED"


@dataclass(frozen=True)
class StatsInheritance:
    child_observation_id: str
    parent_name: str
    parent_observation_ids: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ResourceCensus:
    snapshot: FrozenSnapshot
    files: tuple[ResourceFile, ...]
    definitions: tuple[ResourceDefinition, ...]
    issues: tuple[ResourceIssue, ...]
    conflicts: tuple[DefinitionConflict, ...]
    inheritances: tuple[StatsInheritance, ...]

    @property
    def definition_parse_complete(self) -> bool:
        return not self.issues


# Region -> (wrapper node, record node, identity attribute, observation kind).
# Unknown regions are retained and blocked, never silently called empty banks.
_REGIONS = {
    "Templates": ("Templates", "GameObjects", "MapKey", "RootTemplate"),
    **{name: (name, "Resource", "ID", name) for name in
       ("VisualBank", "CharacterVisualBank", "MaterialBank", "TextureBank")},
    **{plural: ("root", singular, "UUID", singular) for plural, singular in (
        ("CharacterCreationAccessorySets", "CharacterCreationAccessorySet"),
        ("CharacterCreationSharedVisuals", "CharacterCreationSharedVisual"),
        ("CharacterCreationAppearanceVisuals", "CharacterCreationAppearanceVisual"),
        ("CharacterCreationEquipmentIcons", "CharacterCreationEquipmentIcon"),
    )},
}
_ASSETS = frozenset((".gr2", ".dds", ".png", ".jpg", ".jpeg", ".tga", ".wem", ".bnk", ".loca"))
_QUOTED = re.compile(r'"((?:\\.|[^"\\])*)"')


def _inconsistent(detail):
    raise ValueError("SNAPSHOT_INCONSISTENT: " + detail)


def _verified_snapshot(snapshot):
    """Defend the typed boundary against altered dataclass copies, without I/O.

    The caller supplies a load_snapshot result, not independent success flags.
    Recheck its retained content/listing/conversion and metadata bindings so a
    replaced byte/hash or conversion object cannot bypass that reader.
    """
    if not isinstance(snapshot, FrozenSnapshot):
        raise TypeError("parse_resources requires a FrozenSnapshot from load_snapshot")
    try:
        if any(type(value) is not tuple for value in (snapshot.files, snapshot.conversions,
                snapshot.conversion_manifests, snapshot.unconverted_binary_paths)):
            _inconsistent("Snapshot sequences must be immutable tuples")
        artifacts = (snapshot.content_manifest, snapshot.listing, *snapshot.files,
                     *snapshot.conversion_manifests, *(c.inspection for c in snapshot.conversions))
        for file in artifacts:
            if type(file.data) is not bytes or sha256(file.data).hexdigest().upper() != file.sha256:
                _inconsistent("Retained file digest differs: " + file.relative_path)
        manifest = snapshots._json(snapshot.content_manifest, "clothmorph.source-content-manifest")
        rows = manifest["files"]
        snapshots._paths_unique(f.relative_path for f in snapshot.files)
        expected = tuple((r["relative_path"], r["bytes"], r["sha256"]) for r in rows)
        actual = tuple((f.relative_path, f.size, f.sha256) for f in snapshot.files)
        if expected != actual or manifest["file_count"] != len(actual):
            _inconsistent("Retained source files differ from their content manifest")
        if snapshots._listing(snapshot.listing) != {p: size for p, size, _ in actual}:
            _inconsistent("Retained listing differs from source files")
        if (manifest["pak_sha256"] != snapshot.package.sha256
                or manifest["pak_path"] != snapshot.package.recorded_path):
            _inconsistent("Package identity differs from content manifest")
        by_path = {file.relative_path: file for file in snapshot.files}
        metadata = snapshots._metadata(by_path[snapshot.module.relative_path], {
            field: getattr(snapshot.module, field) for field in ("uuid", "folder", "name", "version64")})
        if metadata != snapshot.module:
            _inconsistent("Module metadata differs from retained bytes")
        manifests = {file.sha256: file for file in snapshot.conversion_manifests}
        converted_paths = set()
        for converted in snapshot.conversions:
            if type(converted.manifest_row) is not int or converted.manifest_row < 0:
                _inconsistent("Conversion row must be an exact nonnegative integer")
            source = by_path[converted.source_relative_path]
            proof = snapshots._json(manifests[converted.manifest_sha256], "clothmorph.source-bank-conversion-evidence")
            row = proof["conversions"][converted.manifest_row]
            if (source.relative_path in converted_paths or not source.relative_path.lower().endswith(".lsf")
                    or source.sha256 != converted.source_sha256
                    or snapshots._label_relative(row["source"], manifest["extract_root"]) != source.relative_path
                    or row["source_sha256"] != source.sha256
                    or row["inspection_sha256"] != converted.inspection.sha256
                    or not row["inspection"].replace("\\", "/").endswith("/" + converted.inspection.relative_path)
                    or proof["tool"]["sha256"] != converted.tool_sha256
                    or converted.tool_sha256 != manifest["tool_sha256"]
                    or tuple(proof["tool"]["arguments"]) != converted.tool_arguments
                    or converted.tool_arguments != snapshots._CONVERT_ARGS):
                _inconsistent("Conversion binding differs from retained evidence")
            converted_paths.add(source.relative_path)
        # An omitted conversion must not silently make a verified source look
        # unconverted. Conversely, a fabricated conversion row must not enter.
        proof_paths = []
        for file in snapshot.conversion_manifests:
            proof = snapshots._json(file, "clothmorph.source-bank-conversion-evidence")
            proof_paths.extend(path for row in proof["conversions"]
                               if (path := snapshots._label_relative(row["source"], manifest["extract_root"])) is not None)
        if len(proof_paths) != len(converted_paths) or set(proof_paths) != converted_paths:
            _inconsistent("Conversion coverage differs from retained manifests")
        if snapshot.unconverted_binary_paths != tuple(f.relative_path for f in snapshot.files
                if f.relative_path.lower().endswith(".lsf") and f.relative_path not in converted_paths):
            _inconsistent("Unconverted source coverage differs")
    except (KeyError, TypeError, AttributeError, IndexError, snapshots.SnapshotError) as error:
        _inconsistent(str(error))


def _tag(element):
    if element.tag is ET.Comment:
        return "#comment"
    if element.tag is ET.ProcessingInstruction:
        return "#processing-instruction"
    return element.tag


def _tree(element, locator):
    counts = defaultdict(int)
    children = []
    for child in element:
        tag = _tag(child)
        counts[tag] += 1
        children.append(_tree(child, f"{locator}/{tag}[{counts[tag]}]"))
    return XmlElement(_tag(element), tuple(element.attrib.items()), element.text, element.tail,
                      tuple(children), locator)


def _structural(node):
    return tuple(child for child in node.children if not child.tag.startswith("#"))


def _attr(node, name):
    return dict(node.attributes).get(name)


def _id(snapshot, source, locator, kind):
    # Raw observation identity, not a final canonical release-ledger identity.
    parts = (snapshot.profile_id, snapshot.module.uuid, snapshot.package.sha256,
             source.original.relative_path, source.original.sha256,
             source.inspection.sha256 if source.inspection else None, locator, kind)
    return sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest().upper()


def _issue(issues, source, code, locator, detail, ids=()):
    issues.append(ResourceIssue(code, source.original.relative_path, locator, detail, ids))


def _xml(snapshot, source, issues):
    data = source.inspection.data if source.inspection else source.original.data
    # Decode first so UTF-16 cannot conceal a DTD. XML's byte declaration is
    # still honored by the actual parser; only UTF-8 and BOM-marked UTF-16 are
    # accepted as text encodings in this evidence stage.
    try:
        text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeError:
        _issue(issues, source, "XML_ENCODING_UNSUPPORTED", "/", "Unsupported or malformed XML encoding")
        return None, []
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        _issue(issues, source, "XML_DTD_FORBIDDEN", "/", "DTD/entity declarations are unsupported")
        return None, []
    try:
        element = ET.fromstring(data, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    except (ET.ParseError, ValueError):
        _issue(issues, source, "XML_MALFORMED", "/", "Cannot parse retained XML bytes")
        return None, []
    document = _tree(element, f"/{_tag(element)}[1]")
    definitions = []
    if document.tag != "save":
        _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", document.locator, "Expected save document")
        return document, definitions
    if not any(child.tag == "region" for child in _structural(document)):
        _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", document.locator, "No resource region present")
    for region in _structural(document):
        if region.tag == "version":
            if _structural(region) or (region.text and region.text.strip()):
                _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", region.locator, "Unexpected content inside version")
            continue
        if region.tag != "region":
            _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", region.locator, "Unexpected save child")
            continue
        name = _attr(region, "id")
        if name == "Config" and source.original.relative_path == snapshot.module.relative_path:
            # The snapshot reader already parsed and bound this metadata. The
            # entire Config tree remains available on the file observation.
            continue
        rule = _REGIONS.get(name)
        if rule is None:
            _issue(issues, source, "UNKNOWN_XML_REGION", region.locator, f"Unsupported region: {name}")
            continue
        wrapper_name, record_name, key, kind = rule
        wrappers = _structural(region)
        if len(wrappers) != 1 or wrappers[0].tag != "node" or _attr(wrappers[0], "id") != wrapper_name:
            _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", region.locator, "Unexpected bank wrapper")
            continue
        groups = _structural(wrappers[0])
        if len(groups) > 1 or any(group.tag != "children" for group in groups):
            _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", wrappers[0].locator, "Unexpected bank record container")
            continue
        for node in _structural(groups[0]) if groups else ():
            if node.tag != "node" or _attr(node, "id") != record_name:
                _issue(issues, source, "XML_STRUCTURE_UNSUPPORTED", node.locator, "Unexpected bank record")
                continue
            ids = tuple(_attr(child, "value") for child in node.children
                        if child.tag == "attribute" and _attr(child, "id") == key)
            resource_id = ids[0] if len(ids) == 1 and ids[0] else None
            observation_id = _id(snapshot, source, node.locator, kind)
            definitions.append(ResourceDefinition(observation_id, kind, resource_id, source, node.locator, node))
            if resource_id is None:
                code = "DEFINITION_ID_AMBIGUOUS" if len(ids) > 1 else "DEFINITION_ID_MISSING"
                _issue(issues, source, code, node.locator, f"Expected one nonempty {key}", (observation_id,))
    return document, definitions


def _statement(raw, line):
    text = (raw.removeprefix("\ufeff") if line == 1 else raw).strip()
    if not text:
        return StatsStatement("blank", (), raw, line)
    if text.startswith("//"):
        return StatsStatement("comment", (), raw, line)
    match = re.match(r"(new\s+entry|type|using|data)\b", text)
    if match is None:
        return StatsStatement("unsupported", (), raw, line)
    command = "new entry" if match.group(1).startswith("new") else match.group(1)
    rest = text[match.end():].lstrip()
    arguments = []
    while rest and not rest.startswith("//"):
        token = _QUOTED.match(rest)
        if token is None:
            return StatsStatement("malformed", tuple(arguments), raw, line)
        arguments.append(re.sub(r'\\(["\\])', r"\1", token.group(1)))
        rest = rest[token.end():].lstrip()
    if len(arguments) != (2 if command == "data" else 1):
        command = "malformed"
    return StatsStatement(command, tuple(arguments), raw, line)


def _stats(snapshot, source, issues):
    try:
        text = source.original.data.decode("utf-8")
    except UnicodeError:
        _issue(issues, source, "STATS_ENCODING_UNSUPPORTED", "line:1", "Stats must be valid UTF-8")
        return (), []
    # str.splitlines also splits Unicode NEL and line/paragraph separators,
    # which may occur inside a quoted value. Only physical CR/LF ends a line.
    lines = (raw for raw in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text) if raw)
    statements = tuple(_statement(raw, index) for index, raw in enumerate(lines, 1))
    definitions = []
    entry = []

    def finish():
        if not entry:
            return
        name = entry[0].arguments[0]
        locator = f"line:{entry[0].line}"
        identity = _id(snapshot, source, locator, "Stats")
        types = tuple(s.arguments[0] for s in entry if s.command == "type")
        parents = tuple(s.arguments[0] for s in entry if s.command == "using")
        data = tuple(s.arguments for s in entry if s.command == "data")
        definitions.append(ResourceDefinition(identity, "Stats", name or None, source, locator,
                                              statements=tuple(entry), stats_types=types,
                                              stats_parents=parents, stats_data=data))
        problems = []
        if not name:
            problems.append("DEFINITION_ID_MISSING")
        if not types or (len(types) == 1 and not types[0]):
            problems.append("STATS_TYPE_MISSING")
        elif len(types) > 1:
            problems.append("STATS_TYPE_AMBIGUOUS")
        if len(parents) > 1:
            problems.append("STATS_PARENT_DECLARATION_AMBIGUOUS")
        if len({key for key, _ in data}) != len(data):
            problems.append("STATS_DATA_REPEATED")
        for code in problems:
            _issue(issues, source, code, locator, "Repeated or missing Stats declaration", (identity,))

    for statement in statements:
        if statement.command == "new entry":
            finish()
            entry = [statement]
        else:
            if entry:
                entry.append(statement)
            if statement.command in ("unsupported", "malformed"):
                _issue(issues, source, "STATS_STATEMENT_" + statement.command.upper(),
                       f"line:{statement.line}", "Unsupported or malformed Stats line retained verbatim")
            elif not entry and statement.command not in ("blank", "comment"):
                _issue(issues, source, "STATS_ORPHAN_STATEMENT", f"line:{statement.line}", "Statement has no named entry")
    finish()
    return statements, definitions


def _semantic_node(node):
    # Ignore indentation only; all attributes, ordered children, mixed text,
    # tails and comments remain part of the conservative content comparison.
    return (node.tag, node.attributes, (node.text or "").strip() or None,
            (node.tail or "").strip() or None,
            tuple(_semantic_node(child) for child in node.children))


def _conflicts(definitions, issues):
    groups = defaultdict(list)
    for definition in definitions:
        if definition.resource_id is not None:
            identity = definition.resource_id
            # GUID spelling case is not a distinct bank identity. Keep exact
            # spelling on each observation; do not case-fold named Stats.
            if definition.kind != "Stats" and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", identity):
                identity = identity.lower()
            groups[(definition.kind, identity)].append(definition)
    conflicts = []
    for (kind, resource_id), group in groups.items():
        if len(group) < 2:
            continue
        contents = [(_semantic_node(d.node) if d.node else
                     tuple((s.command, s.arguments) for s in d.statements if s.command not in ("blank", "comment")))
                    for d in group]
        equal = all(content == contents[0] for content in contents[1:])
        ids = tuple(d.observation_id for d in group)
        conflicts.append(DefinitionConflict(kind, resource_id, ids, equal))
        _issue(issues, group[0].source,
               "DUPLICATE_DEFINITION_UNRESOLVED" if equal else "DUPLICATE_DEFINITION_CONFLICT",
               group[0].locator, f"No precedence established for {kind} {resource_id}", ids)
    return tuple(conflicts)


def _inheritances(definitions, issues):
    stats = [d for d in definitions if d.kind == "Stats"]
    by_name = defaultdict(list)
    for definition in stats:
        if definition.resource_id:
            by_name[definition.resource_id].append(definition)
    edges = {d.observation_id: tuple(parent.observation_id for name in d.stats_parents for parent in by_name[name]) for d in stats}

    def in_cycle(origin):
        pending = list(edges[origin])
        seen = set()
        while pending:
            target = pending.pop()
            if target == origin:
                return True
            if target not in seen:
                seen.add(target)
                pending.extend(edges[target])
        return False

    cyclic = {d.observation_id for d in stats if in_cycle(d.observation_id)}
    relations = []
    for child in stats:
        if child.observation_id in cyclic:
            _issue(issues, child.source, "STATS_INHERITANCE_CYCLE", child.locator,
                   "Cycle exists in local parent candidates", (child.observation_id,))
        for name in child.stats_parents:
            parents = tuple(d.observation_id for d in by_name[name])
            status = ("DECLARATION_AMBIGUOUS" if len(child.stats_parents) > 1
                      else "MISSING_PARENT" if not parents else "AMBIGUOUS_PARENT" if len(parents) > 1
                      else "CYCLE" if child.observation_id in cyclic else "LOCAL_PARENT")
            relations.append(StatsInheritance(child.observation_id, name, parents, status))
            # Report each observed defect independently. An ambiguous using
            # declaration must not suppress its absent/ambiguous parent facts.
            code = "STATS_PARENT_MISSING" if not parents else "STATS_PARENT_AMBIGUOUS" if len(parents) > 1 else None
            if code:
                _issue(issues, child.source, code, child.locator, f"Local parent observation: {name}",
                       (child.observation_id, *parents))
    return tuple(relations)


def parse_resources(snapshot: FrozenSnapshot) -> ResourceCensus:
    """Parse every configured original file; unsupported inputs stay explicit."""
    _verified_snapshot(snapshot)
    conversions = {conversion.source_relative_path: conversion for conversion in snapshot.conversions}
    files, definitions, issues = [], [], []
    for file in snapshot.files:
        suffix = "." + file.relative_path.rsplit(".", 1)[-1].lower() if "." in file.relative_path else ""
        conversion = conversions.get(file.relative_path)
        representation = "CONVERTED_LSF" if conversion else "PACKED_XML" if suffix in (".lsx", ".xml") else "PACKED_BYTES"
        source = ResourceSource(snapshot.profile_id, snapshot.module, snapshot.package, file, representation,
                                conversion.inspection if conversion else None, conversion)
        issue_start = len(issues)
        parsed, statements, document = [], (), None
        status = "PARSED"
        if suffix in (".lsx", ".xml") or conversion:
            document, parsed = _xml(snapshot, source, issues)
        elif suffix == ".txt" and ("/stats/" in ("/" + file.relative_path.lower())
                                    or re.search(rb"(?m)^\s*new\s+entry\b", file.data.removeprefix(b"\xef\xbb\xbf"))):
            source = ResourceSource(snapshot.profile_id, snapshot.module, snapshot.package, file, "PACKED_STATS")
            statements, parsed = _stats(snapshot, source, issues)
        elif suffix in _ASSETS:
            status = "NON_DEFINITION_ASSET"
        else:
            code = "BINARY_CONVERSION_MISSING" if suffix == ".lsf" else "UNSUPPORTED_FILE_FORMAT"
            _issue(issues, source, code, "/", "No supported definition parser or explicit asset classification")
        if len(issues) > issue_start:
            status = "UNSUPPORTED"
        definitions.extend(parsed)
        files.append(ResourceFile(source, status, document, statements, tuple(d.observation_id for d in parsed),
                                  tuple(issue.code for issue in issues[issue_start:])))
    conflicts = _conflicts(definitions, issues)
    inheritances = _inheritances(definitions, issues)
    return ResourceCensus(snapshot, tuple(files), tuple(definitions), tuple(issues), conflicts, inheritances)
