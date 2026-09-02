"""Conservative creation-path observations over verified, retained resource bytes.

These are discovery identities, not release-ledger IDs or accepted routes. Every
reference occurrence is retained, including duplicate ordered components. Missing
or competing definitions have no selected winner. EquipmentRace is an exact key,
not a canonical body tuple. Dependency list order does not prove override order.
No filesystem or process is accessed by this module.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
import json
import re

from .resources import ResourceCensus, ResourceDefinition, ResourceSource, parse_resources
from .snapshot import FileSnapshot


@dataclass(frozen=True)
class CreationIssue:
    code: str
    source_observation_id: str
    locator: str
    detail: str
    candidate_observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class VisualComponent:
    reference: str
    locator: str
    candidate_observation_ids: tuple[str, ...]
    visual_slots: tuple[str, ...] = ()
    source_file_values: tuple[str, ...] = ()
    mesh: FileSnapshot | None = None
    mesh_source: ResourceSource | None = None
    shared_observation_id: str | None = None
    reference_owner_observation_id: str = ""
    accessory_locator: str | None = None


@dataclass(frozen=True)
class RouteBinding:
    source_observation_id: str
    locator: str
    kind: str
    equipment_race: str | None
    visual_references: tuple[str, ...]
    components: tuple[VisualComponent, ...]
    shared_visual_references: tuple[str, ...] = ()
    equipment_race_values: tuple[str, ...] = ()
    shared_visual_locators: tuple[str, ...] = ()


@dataclass(frozen=True)
class _VisualReference:
    """The declaring owner is independent of the accessory discovery edge."""
    reference: str
    locator: str
    owner: ResourceDefinition
    shared_observation_id: str | None = None
    accessory_locator: str | None = None


@dataclass(frozen=True)
class CreationObservation:
    observation_id: str
    source_observation_id: str
    kind: str
    related_observation_ids: tuple[str, ...]
    root_references: tuple[str, ...] = ()
    slot_values: tuple[str, ...] = ()
    routes: tuple[RouteBinding, ...] = ()
    effective_data: tuple[tuple[str, str, str], ...] = ()
    body_evidence: tuple[tuple[str, str, str], ...] = ()
    body_tuple: None = None
    scope: str = "UNRESOLVED"


@dataclass(frozen=True)
class CreationPathCensus:
    source: ResourceCensus
    dependencies: tuple[ResourceCensus, ...]
    source_observation_ids: tuple[str, ...]
    observations: tuple[CreationObservation, ...]
    issues: tuple[CreationIssue, ...]

    @property
    def creation_paths_complete(self):
        return not self.issues


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if is_dataclass(left):
        return all(_strict_equal(getattr(left, f.name), getattr(right, f.name)) for f in fields(left))
    if type(left) is tuple:
        return len(left) == len(right) and all(_strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def _verified(census):
    if type(census) is not ResourceCensus:
        raise TypeError("resolve_creation_paths requires ResourceCensus from parse_resources")
    actual = parse_resources(census.snapshot)
    if not _strict_equal(actual, census):
        raise ValueError("CENSUS_INCONSISTENT: definitions differ from retained source bytes")
    return actual


def _values(node, name):
    return tuple(value for value, _ in _attribute_occurrences(node, name))


def _attribute_occurrences(node, name):
    if node is None:
        return ()
    return tuple((dict(c.attributes).get("value", ""), c.locator) for c in node.children
                 if c.tag == "attribute" and dict(c.attributes).get("id") == name)


def _children(node, name=None):
    if node is None:
        return ()
    return tuple(c for group in node.children if group.tag == "children" for c in group.children
                 if c.tag == "node" and (name is None or dict(c.attributes).get("id") == name))


def _key(kind, value):
    return value.lower() if kind != "Stats" and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value) else value


def _identity(definition, kind, suffix=""):
    return sha256(json.dumps((definition.observation_id, kind, suffix), separators=(",", ":")).encode()).hexdigest().upper()


class _Resolver:
    def __init__(self, source, dependencies):
        self.source, self.dependencies = source, dependencies
        self.issues, self.observations = [], []
        self.inputs = (source, *dependencies)
        self.by_id = {d.observation_id: d for c in self.inputs for d in c.definitions}
        self.input_by_source = {(c.snapshot.profile_id, c.snapshot.package.sha256): i for i, c in enumerate(self.inputs)}
        self.scopes = self.dependency_scopes()
        # Parser issues remain available verbatim on source/dependencies. Local
        # inheritance gaps are recomputed here so a proven dependency can close one.
        for c in self.inputs:
            for issue in c.issues:
                if issue.code.startswith("STATS_PARENT_") or issue.code == "STATS_INHERITANCE_CYCLE":
                    continue
                self.issues.append(CreationIssue(issue.code, issue.observation_ids[0] if issue.observation_ids else "",
                                                 issue.locator, issue.detail, issue.observation_ids))

    def dependency_scopes(self):
        edges = defaultdict(list)
        for index, c in enumerate(self.inputs):
            for declaration in c.snapshot.module.dependencies:
                candidates = [(i, candidate) for i, candidate in enumerate(self.inputs)
                              if candidate.snapshot.module.uuid.lower() == declaration.uuid.lower()]
                code = None
                if not candidates:
                    code = "DEPENDENCY_MISSING"
                elif len(candidates) != 1:
                    code = "DEPENDENCY_MODULE_AMBIGUOUS"
                else:
                    i, candidate = candidates[0]
                    if candidate.snapshot.module.version64 != declaration.version64:
                        code = "DEPENDENCY_VERSION_UNRESOLVED"
                    elif (candidate.snapshot.module.folder, candidate.snapshot.module.name) != (declaration.folder, declaration.name):
                        code = "DEPENDENCY_IDENTITY_UNRESOLVED"
                    else:
                        edges[index].append(i)
                if code:
                    self.issues.append(CreationIssue(code, "", c.snapshot.module.relative_path,
                        f"{c.snapshot.profile_id}: declared {declaration.uuid} at exact version {declaration.version64}"))

        def walk(index, stack):
            if index in stack:
                self.issues.append(CreationIssue("DEPENDENCY_CYCLE", "", self.inputs[index].snapshot.module.relative_path,
                                                self.inputs[index].snapshot.profile_id))
                return set()
            reached = {index}
            for child in edges[index]:
                reached.update(walk(child, (*stack, index)))
            return reached

        scopes = tuple(walk(i, ()) for i in range(len(self.inputs)))
        for index, c in enumerate(self.inputs[1:], 1):
            if index not in scopes[0]:
                self.issues.append(CreationIssue("DEPENDENCY_UNDECLARED", "", c.snapshot.module.relative_path,
                                                "Not reachable by exact verified declarations: " + c.snapshot.profile_id))
        return scopes

    def scope(self, owner):
        index = self.input_by_source[(owner.source.profile_id, owner.source.package.sha256)]
        return tuple(c for i, c in enumerate(self.inputs) if i in self.scopes[index])

    def issue(self, code, definition, locator=None, detail="", candidates=()):
        self.issues.append(CreationIssue(code, definition.observation_id, locator or definition.locator,
                                         detail, tuple(d.observation_id for d in candidates)))

    def lookup(self, kind, reference, owner, code, locator=None):
        candidates = tuple(d for c in self.scope(owner) for d in c.definitions
                           if d.kind == kind and d.resource_id is not None and _key(kind, d.resource_id) == _key(kind, reference))
        # A declaring dependency cannot conceal a competing definition in the
        # release source's reachable set. No load-order override is assumed.
        shadows = tuple(d for i, c in enumerate(self.inputs) if i in self.scopes[0] for d in c.definitions
                        if d.kind == kind and d.resource_id is not None
                        and _key(kind, d.resource_id) == _key(kind, reference)
                        and d.observation_id not in {item.observation_id for item in candidates})
        if shadows and candidates:
            candidates += shadows
        elif shadows:
            self.issue("REFERENCE_DEPENDENCY_UNDECLARED", owner, locator, reference, shadows)
        if len(candidates) != 1:
            self.issue(code + ("_MISSING" if not candidates else "_AMBIGUOUS"), owner, locator, reference, candidates)
        return candidates

    def lineage(self, definition, stack=()):
        prefix = "STATS" if definition.kind == "Stats" else "ROOT"
        if definition.observation_id in stack:
            self.issue(prefix + "_INHERITANCE_CYCLE", definition)
            return ()
        names = definition.stats_parents if prefix == "STATS" else _values(definition.node, "ParentTemplateId")
        if len(names) > 1:
            self.issue(prefix + "_PARENT_DECLARATION_AMBIGUOUS", definition)
        parents = []
        for name in names:
            matches = self.lookup(definition.kind, name, definition, prefix + "_PARENT")
            if len(matches) == 1:
                inherited = self.lineage(matches[0], (*stack, definition.observation_id))
                if len(names) == 1:
                    parents.extend(inherited)
        return (*parents, definition)

    def effective(self, lineage):
        data = []
        for definition in lineage:
            values = definition.stats_data if definition.kind == "Stats" else tuple(
                (dict(c.attributes).get("id", ""), dict(c.attributes).get("value", ""))
                for c in definition.node.children if c.tag == "attribute" and "value" in dict(c.attributes))
            keys = {k for k, _ in values}
            if definition.kind != "Stats" and len(keys) != len(values):
                self.issue("ROOT_PROPERTY_AMBIGUOUS", definition, detail="Repeated scalar attributes are not a proven override")
            data = [row for row in data if row[0] not in keys]
            data.extend((key, value, definition.observation_id) for key, value in values)
        return tuple(data)

    def components(self, references):
        result = []
        for occurrence in references:
            reference, locator, owner = occurrence.reference, occurrence.locator, occurrence.owner
            matches = self.lookup("VisualBank", reference, owner, "VISUAL_BANK", locator)
            slots, paths, mesh, source = (), (), None, None
            if len(matches) == 1:
                definition = matches[0]
                slots, paths = _values(definition.node, "Slot"), _values(definition.node, "SourceFile")
                if len(paths) != 1:
                    self.issue("MESH_SOURCE_ATTRIBUTE_UNRESOLVED", definition, detail=str(paths))
                else:
                    path = paths[0].replace("\\", "/")
                    if not path or path.startswith("/") or ":" in path or any(p in ("", ".", "..") for p in path.split("/")):
                        self.issue("MESH_SOURCE_PATH_UNSAFE", definition, detail=path)
                    elif not path.lower().endswith(".gr2"):
                        self.issue("MESH_SOURCE_FORMAT_UNRESOLVED", definition, detail=path)
                    else:
                        files = [f for c in self.scope(definition)
                                 for f in c.files if f.source.original.relative_path.casefold() == path.casefold()]
                        shadows = [f for i, c in enumerate(self.inputs) if i in self.scopes[0]
                                   for f in c.files if f.source.original.relative_path.casefold() == path.casefold()
                                   and f not in files]
                        if files:
                            files.extend(shadows)
                        elif shadows:
                            self.issue("MESH_DEPENDENCY_UNDECLARED", definition, detail=path)
                        if len(files) == 1:
                            source, mesh = files[0].source, files[0].source.original
                        else:
                            self.issue("MESH_SOURCE_MISSING" if not files else "MESH_SOURCE_AMBIGUOUS", definition, detail=path)
            result.append(VisualComponent(reference, locator, tuple(d.observation_id for d in matches),
                                          slots, paths, mesh, source, occurrence.shared_observation_id,
                                          owner.observation_id, occurrence.accessory_locator))
        return tuple(result)

    def routes(self, definition):
        lineage = self.lineage(definition)
        data = self.effective(lineage)
        result = []
        direct_occurrences = defaultdict(int)
        for key, reference, source_id in data:
            if key == "VisualTemplate":
                owner = self.by_id[source_id]
                attributes = tuple(c for c in owner.node.children if c.tag == "attribute"
                                   and dict(c.attributes).get("id") == "VisualTemplate" and "value" in dict(c.attributes))
                locator = attributes[direct_occurrences[source_id]].locator
                direct_occurrences[source_id] += 1
                refs = (_VisualReference(reference, locator, owner),)
                result.append(RouteBinding(owner.observation_id, locator, "DIRECT_VISUAL", None,
                                           (reference,), self.components(refs)))
        mapped_owners = []
        for owner in lineage:
            maps = []
            for equipment in _children(owner.node, "Equipment"):
                maps.extend(entry for group in _children(equipment, "Visuals") for entry in _children(group))
            for visual_set in _children(owner.node, "VisualSet"):
                maps.extend(_children(visual_set, "Visuals"))
            if maps:
                mapped_owners.append(owner)
            for entry in maps:
                if any(dict(n.attributes).get("id") != "MapValue" for n in _children(entry)):
                    self.issue("EQUIPMENT_MAP_STRUCTURE_UNRESOLVED", owner, entry.locator)
                keys = _values(entry, "MapKey")
                if len(keys) != 1 or not keys[0]:
                    self.issue("EQUIPMENT_RACE_KEY_UNRESOLVED", owner, entry.locator)
                refs = []
                for part in _children(entry, "MapValue"):
                    values = _values(part, "Object")
                    if len(values) != 1 or not values[0]:
                        self.issue("EQUIPMENT_COMPONENT_REFERENCE_UNRESOLVED", owner, part.locator)
                    refs.extend(_VisualReference(value, locator, owner)
                                for value, locator in (_attribute_occurrences(part, "Object") or (("", part.locator),)))
                refs = tuple(refs)
                if not refs:
                    self.issue("EQUIPMENT_COMPONENTS_MISSING", owner, entry.locator)
                result.append(RouteBinding(owner.observation_id, entry.locator, "EQUIPMENT_RACE",
                    keys[0] if len(keys) == 1 else None, tuple(r.reference for r in refs), self.components(refs),
                    equipment_race_values=keys))
        if len(mapped_owners) > 1:
            self.issue("ROOT_MAP_INHERITANCE_UNRESOLVED", definition, candidates=mapped_owners)
        race_keys = [r.equipment_race for r in result if r.kind == "EQUIPMENT_RACE"]
        if len(set(race_keys)) != len(race_keys):
            self.issue("EQUIPMENT_RACE_MAP_AMBIGUOUS", definition)
        if not result:
            self.issue("ROOT_VISUAL_UNRESOLVED", definition)
        return tuple(result)

    def observe(self, definition, kind, related=(), roots=(), slots=(), routes=(), data=(), scope="UNRESOLVED", suffix=""):
        body = tuple(row for row in data if row[0] in ("Race", "RaceUUID", "EquipmentRace", "BodyType", "BodyShape"))
        observation = CreationObservation(_identity(definition, kind, suffix), definition.observation_id, kind,
            tuple(related), tuple(roots), tuple(slots), tuple(routes), data, body, None, scope)
        self.observations.append(observation)
        return observation

    def garment(self, definition):
        lineage = self.lineage(definition)
        data = self.effective(lineage)
        related = tuple(d.observation_id for d in lineage[:-1])
        slots = tuple(v for k, v, _ in data if k == "Slot")
        if definition.kind == "Stats":
            roots = tuple(v for k, v, _ in data if k == "RootTemplate")
            routes = []
            for key, reference, origin in data:
                if key == "RootTemplate":
                    matches = self.lookup("RootTemplate", reference, self.by_id[origin], "ROOT_TEMPLATE")
                    if len(matches) == 1:
                        related += (matches[0].observation_id,)
                        routes.extend(self.routes(matches[0]))
            if not roots:
                self.issue("STATS_ROOT_TEMPLATE_UNRESOLVED", definition)
            self.observe(definition, "NAMED_STATS", related, roots, slots, routes, data)
            if definition.stats_parents:
                self.observe(definition, "INHERITED_SPAWN", related, roots, slots, routes, data)
        else:
            roots = (definition.resource_id,) if definition.resource_id else ()
            routes = self.routes(definition)
            for key, reference, origin in data:
                if key == "Stats":
                    matches = self.lookup("Stats", reference, self.by_id[origin], "ROOT_STATS")
                    if len(matches) == 1:
                        related += (matches[0].observation_id,)
                        if not slots:
                            slots = tuple(v for k, v, _ in self.effective(self.lineage(matches[0])) if k == "Slot")
            self.observe(definition, "ROOT_TEMPLATE", related, roots, slots, routes, data)
        for index, route in enumerate(routes):
            body_data = data + (("EquipmentRace", route.equipment_race, route.source_observation_id),) if route.equipment_race else data
            self.observe(definition, "BODY_FAMILY", related, roots, slots, (route,), body_data, suffix=str(index))
            self.issue("BODY_TUPLE_UNRESOLVED", definition, route.locator, "Exact canonical body/equipment map not supplied")

    def validate_character_creation(self, definition):
        """Apply the same semantic checks to discovered and referenced records."""
        allowed = ("VisualUUIDs",) if definition.kind == "CharacterCreationAccessorySet" else ()
        for child in _children(definition.node):
            if dict(child.attributes).get("id") not in allowed:
                self.issue("CREATION_STRUCTURE_UNRESOLVED", definition, child.locator)
            elif _children(child) or any(c.tag == "attribute" and dict(c.attributes).get("id") != "Object"
                                         for c in child.children):
                self.issue("CREATION_STRUCTURE_UNRESOLVED", definition, child.locator)
        slots = _values(definition.node, "SlotName")
        if len(slots) != 1 or not slots[0]:
            self.issue("CREATION_SLOT_UNRESOLVED", definition)
        if definition.kind != "CharacterCreationAccessorySet":
            references = _values(definition.node, "VisualResource")
            if not references or not all(references):
                self.issue("CREATION_VISUAL_MISSING", definition)
            if len(references) > 1:
                self.issue("CREATION_VISUAL_AMBIGUOUS", definition)

    def character_creation(self, definition):
        data = self.effective((definition,))
        self.validate_character_creation(definition)
        slots = _values(definition.node, "SlotName")
        scope = "NON_GARMENT_PIERCING" if slots == ("Piercing",) else "UNRESOLVED"
        related, refs, shared_refs, shared_locators = [], [], [], []
        if definition.kind == "CharacterCreationAccessorySet":
            for item in _children(definition.node, "VisualUUIDs"):
                values = _values(item, "Object")
                if len(values) != 1 or not values[0]:
                    self.issue("CREATION_SHARED_REFERENCE_UNRESOLVED", definition, item.locator)
                for shared, accessory_locator in _attribute_occurrences(item, "Object") or (("", item.locator),):
                    shared_refs.append(shared)
                    shared_locators.append(accessory_locator)
                    matches = self.lookup("CharacterCreationSharedVisual", shared, definition, "SHARED_VISUAL", accessory_locator)
                    if len(matches) == 1:
                        target = matches[0]
                        self.validate_character_creation(target)
                        related.append(target.observation_id)
                        if _values(target.node, "SlotName") != slots:
                            scope = "UNRESOLVED"
                            self.issue("CREATION_SLOT_CONFLICT", definition, item.locator, shared, matches)
                        refs.extend(_VisualReference(value, locator, target, target.observation_id, accessory_locator)
                                    for value, locator in _attribute_occurrences(target.node, "VisualResource"))
            kind = "CHARACTER_CREATION_ACCESSORY_SET"
        else:
            refs.extend(_VisualReference(value, locator, definition)
                        for value, locator in _attribute_occurrences(definition.node, "VisualResource"))
            kind = "CHARACTER_CREATION_SHARED_VISUAL" if definition.kind == "CharacterCreationSharedVisual" else "CHARACTER_CREATION_APPEARANCE_VISUAL"
        if not refs:
            self.issue("CREATION_VISUAL_MISSING", definition)
        route = RouteBinding(definition.observation_id, definition.locator, "CHARACTER_CREATION", None,
                             tuple(r.reference for r in refs), self.components(refs), tuple(shared_refs),
                             shared_visual_locators=tuple(shared_locators))
        self.observe(definition, kind, related, slots=slots, routes=(route,), data=data, scope=scope)

    def run(self):
        for definition in self.source.definitions:
            if definition.kind in ("RootTemplate", "Stats"):
                self.garment(definition)
            elif definition.kind in ("CharacterCreationAccessorySet", "CharacterCreationSharedVisual", "CharacterCreationAppearanceVisual"):
                self.character_creation(definition)
            elif definition.kind == "CharacterVisualBank":
                self.observe(definition, "BODY_FAMILY", data=self.effective((definition,)))
                self.issue("CHARACTER_VISUAL_MAPPING_UNRESOLVED", definition)
        return CreationPathCensus(self.source, self.dependencies,
            tuple(d.observation_id for d in self.source.definitions), tuple(self.observations), tuple(self.issues))


def resolve_creation_paths(census: ResourceCensus, dependencies: Sequence[ResourceCensus]) -> CreationPathCensus:
    """Join exact observations; no filename inference, precedence guess or I/O."""
    source = _verified(census)
    if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
        raise TypeError("dependencies must be a sequence of ResourceCensus")
    verified_dependencies = tuple(_verified(d) for d in dependencies)
    identities = [(c.snapshot.profile_id, c.snapshot.package.sha256) for c in (source, *verified_dependencies)]
    if len(set(identities)) != len(identities):
        raise ValueError("CENSUS_INPUT_DUPLICATE: repeated package/profile input")
    return _Resolver(source, verified_dependencies).run()
