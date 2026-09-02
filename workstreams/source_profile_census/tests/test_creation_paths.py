"""Creation joins through real retained-byte census fixtures, not success flags."""

from dataclasses import replace
import importlib
import importlib.util
from pathlib import Path

import pytest

from workstreams.source_profile_census.resources import parse_resources
from workstreams.source_profile_census.tests.test_resources import bank, frozen
from workstreams.source_profile_census.tests.test_snapshot import META, META_PATH, MODULE, TOOL, digest, write, write_json
from workstreams.source_profile_census.snapshot import load_snapshot


def resolver():
    name = "workstreams.source_profile_census.creation_paths"
    assert importlib.util.find_spec(name), "Creation-path resolver is not implemented"
    return importlib.import_module(name).resolve_creation_paths


def attr(key, value):
    return f'<attribute id="{key}" value="{value}"/>'


def node(kind, attributes="", children=""):
    return f'<node id="{kind}">{attributes}' + (f'<children>{children}</children>' if children else '') + '</node>'


def root(key="root", extra="", children=""):
    return node("GameObjects", attr("MapKey", key) + extra, children)


def visual(key, path="Assets/robe.GR2", extra=""):
    return node("Resource", attr("ID", key) + attr("SourceFile", path) + extra)


def mapped():
    return node("Equipment", "", node("Visuals", "",
        node("Object", attr("MapKey", "race-one"), node("MapValue", attr("Object", "vr-b")) + node("MapValue", attr("Object", "vr-a"))) +
        node("Object", attr("MapKey", "race-two"), node("MapValue", attr("Object", "vr-a")) + node("MapValue", attr("Object", "vr-a")))))


def census(tmp_path, roots="", stats=b"", visuals="", extras=None):
    files = {META_PATH: META.replace(META[META.index(b'<node id="Dependencies">'):META.index(b'<node id="ModuleInfo">')], b'<node id="Dependencies"/>')}
    if roots:
        files["roots.lsx"] = bank("Templates", roots)
    if stats:
        files["Public/Example/Stats/data.txt"] = stats
    if visuals:
        files["visuals.lsx"] = bank("VisualBank", visuals)
        files["Assets/robe.GR2"] = b"exact mesh bytes"
    files.update(extras or {})
    return parse_resources(frozen(tmp_path, files))


def observations(result, kind):
    return [o for o in result.observations if o.kind == kind]


def codes(result):
    return {i.code for i in result.issues}


def module_census(tmp, uuid, files, dependencies=(), version="1"):
    """Tiny independently hashed multi-module fixture through the actual loader."""
    module = {"uuid": uuid, "folder": "Example", "name": "Example", "version64": version}
    deps = ''.join(node("ModuleShortDesc", attr("UUID", dep) + attr("Folder", "Example") + attr("Name", "Example") + attr("Version64", ver)) for dep, ver in dependencies)
    info = ''.join(attr(key, module[field]) for key, field in (("UUID", "uuid"), ("Folder", "folder"), ("Name", "name"), ("Version64", "version64")))
    meta = bank("Config", node("Dependencies", "", deps) + node("ModuleInfo", info), "root")
    files = {META_PATH: meta, **files}
    package = write(tmp, "source.pak", (uuid + version).encode())
    package["recorded_path"] = "Z:/fixture/source.pak"
    for name, data in files.items():
        write(tmp, "extract/" + name, data)
    manifest = {"schema": "clothmorph.source-content-manifest", "schema_version": 1,
        "pak_path": package["recorded_path"], "pak_sha256": package["sha256"], "extract_root": "Z:/fixture/extract",
        "tool_sha256": TOOL, "file_count": len(files),
        "files": [{"relative_path": name, "bytes": len(data), "sha256": digest(data)} for name, data in files.items()]}
    return parse_resources(load_snapshot({"root": tmp, "profile_id": uuid + version, "role": "garment_source",
        "module": module, "metadata_path": META_PATH, "package": package,
        "extract_root": {"path": "extract", "recorded_path": "Z:/fixture/extract"},
        "content_manifest": write_json(tmp, "manifest.json", manifest),
        "listing": write(tmp, "listing.txt", ''.join(f"{name}\t{len(data)}\t0\n" for name, data in files.items()).encode()),
        "tool_sha256": TOOL, "conversions": []}))


SOURCE_UUID = "aaaaaaaa-1111-2222-3333-000000000000"
DEP_UUID = "bbbbbbbb-1111-2222-3333-000000000000"
OTHER_UUID = "cccccccc-1111-2222-3333-000000000000"


def test_declared_exact_dependency_resolves_inherited_stats_root_and_mesh(tmp_path):
    dep = module_census(tmp_path / "dep", DEP_UUID, {
        "Public/Example/Stats/parent.txt": b'new entry "Parent"\ntype "Armor"\ndata "RootTemplate" "root"\ndata "Slot" "Breast"\n',
        "roots.lsx": bank("Templates", root(extra=attr("VisualTemplate", "vr"))),
        "visual.lsx": bank("VisualBank", visual("vr")), "Assets/robe.GR2": b"dependency mesh"})
    src = module_census(tmp_path / "src", SOURCE_UUID, {
        "Public/Example/Stats/child.txt": b'new entry "Child"\ntype "Armor"\nusing "Parent"\n'}, ((DEP_UUID, "1"),))
    result = resolver()(src, (dep,))
    child, = observations(result, "NAMED_STATS")
    assert child.root_references == ("root",)
    assert child.slot_values == ("Breast",)
    assert child.routes[0].components[0].mesh.sha256 == digest(b"dependency mesh")
    assert "STATS_PARENT_MISSING" not in codes(result)
    assert child.routes[0].components[0].mesh_source.package.sha256 == dep.snapshot.package.sha256


@pytest.mark.parametrize("declared,version,expected", [((), "1", "DEPENDENCY_UNDECLARED"), (((DEP_UUID, "1"),), "2", "DEPENDENCY_VERSION_UNRESOLVED")])
def test_unproven_dependency_never_supplies_parent(tmp_path, declared, version, expected):
    dep = module_census(tmp_path / "dep", DEP_UUID, {"Public/Example/Stats/parent.txt": b'new entry "Parent"\ntype "Armor"\ndata "Slot" "Underwear"\n'}, version=version)
    src = module_census(tmp_path / "src", SOURCE_UUID, {"Public/Example/Stats/child.txt": b'new entry "Child"\ntype "Armor"\nusing "Parent"\n'}, declared)
    result = resolver()(src, (dep,))
    assert observations(result, "NAMED_STATS")[0].slot_values == ()
    assert {expected, "STATS_PARENT_MISSING"} <= codes(result)


def test_dependency_collision_never_treats_sequence_as_load_order(tmp_path):
    parents = [module_census(tmp_path / str(i), uuid, {"Public/Example/Stats/parent.txt":
        f'new entry "Parent"\ntype "Armor"\ndata "Slot" "{slot}"\n'.encode()})
        for i, (uuid, slot) in enumerate(((DEP_UUID, "Breast"), (OTHER_UUID, "Underwear")))]
    src = module_census(tmp_path / "src", SOURCE_UUID, {"Public/Example/Stats/child.txt": b'new entry "Child"\ntype "Armor"\nusing "Parent"\n'}, ((DEP_UUID, "1"), (OTHER_UUID, "1")))
    for dependencies in (parents, list(reversed(parents))):
        result = resolver()(src, dependencies)
        assert observations(result, "NAMED_STATS")[0].slot_values == ()
        assert "STATS_PARENT_AMBIGUOUS" in codes(result)
        problem = next(i for i in result.issues if i.code == "STATS_PARENT_AMBIGUOUS")
        assert set(problem.candidate_observation_ids) == {d.definitions[0].observation_id for d in parents}


def test_transitive_dependency_resolves_mesh_not_sibling_or_unrelated(tmp_path):
    mesh_dep = module_census(tmp_path / "mesh", OTHER_UUID, {"Assets/robe.GR2": b"external mesh"})
    visual_dep = module_census(tmp_path / "visual", DEP_UUID, {"visual.lsx": bank("VisualBank", visual("vr"))}, ((OTHER_UUID, "1"),))
    src = module_census(tmp_path / "src", SOURCE_UUID, {"root.lsx": bank("Templates", root(extra=attr("VisualTemplate", "vr")))}, ((DEP_UUID, "1"),))
    result = resolver()(src, (visual_dep, mesh_dep))
    component = observations(result, "ROOT_TEMPLATE")[0].routes[0].components[0]
    assert component.mesh.sha256 == digest(b"external mesh")
    assert component.mesh_source.module.uuid == OTHER_UUID


def test_duplicate_scalar_declarations_are_preserved_but_never_claim_resolved(tmp_path):
    roots = root(extra=attr("VisualTemplate", "vr") + attr("VisualTemplate", "vr"), children=mapped())
    src = census(tmp_path, roots, visuals=visual("vr") + visual("vr-a") + visual("vr-b"))
    result = resolver()(src, ())
    assert len([r for r in observations(result, "ROOT_TEMPLATE")[0].routes if r.kind == "DIRECT_VISUAL"]) == 2
    assert "ROOT_PROPERTY_AMBIGUOUS" in codes(result)


def test_missing_component_object_is_not_silently_omitted(tmp_path):
    maps = node("Equipment", "", node("Visuals", "", node("Object", attr("MapKey", "race"), node("MapValue") + node("MapValue", attr("Object", "vr")))))
    result = resolver()(census(tmp_path, root(children=maps), visuals=visual("vr")), ())
    assert "EQUIPMENT_COMPONENT_REFERENCE_UNRESOLVED" in codes(result)
    assert observations(result, "ROOT_TEMPLATE")[0].routes[0].visual_references == ("", "vr")


def test_root_without_visual_is_explicit_incomplete_discovery(tmp_path):
    result = resolver()(census(tmp_path, root()), ())
    assert "ROOT_VISUAL_UNRESOLVED" in codes(result)
    assert not result.creation_paths_complete


@pytest.mark.parametrize("field,mutation,expected", [
    ("Object", "", "CREATION_SHARED_REFERENCE_UNRESOLVED"),
    ("SlotName", "", "CREATION_SLOT_UNRESOLVED"),
    ("VisualResource", attr("VisualResource", "vr") + attr("VisualResource", "vr"), "CREATION_VISUAL_AMBIGUOUS"),
])
def test_cc_malformed_reference_or_slot_is_retained_and_blocked(tmp_path, field, mutation, expected):
    sets = node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"), node("VisualUUIDs", attr("Object", "shared")))
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr"))
    if field == "Object":
        sets = sets.replace(attr("Object", "shared"), mutation)
    elif field == "SlotName":
        shared = shared.replace(attr("SlotName", "Piercing"), mutation)
    else:
        shared = shared.replace(attr("VisualResource", "vr"), mutation)
    src = census(tmp_path, visuals=visual("vr"), extras={"sets.lsx": bank("CharacterCreationAccessorySets", sets, "root"),
        "shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root")})
    result = resolver()(src, ())
    assert expected in codes(result)
    assert not result.creation_paths_complete
    assert len(observations(result, "CHARACTER_CREATION_ACCESSORY_SET")) == 1


def test_repeated_race_key_preserves_both_bindings_and_blocks_precedence(tmp_path):
    maps = mapped().replace("race-two", "race-one")
    result = resolver()(census(tmp_path, root(children=maps), visuals=visual("vr-a") + visual("vr-b")), ())
    assert [r.equipment_race for r in observations(result, "ROOT_TEMPLATE")[0].routes] == ["race-one", "race-one"]
    assert "EQUIPMENT_RACE_MAP_AMBIGUOUS" in codes(result)


def test_mesh_reference_to_non_gr2_does_not_pass_as_geometry(tmp_path):
    result = resolver()(census(tmp_path, root(extra=attr("VisualTemplate", "vr")), visuals=visual("vr", "Assets/icon.png"), extras={"Assets/icon.png": b"not geometry"}), ())
    assert "MESH_SOURCE_FORMAT_UNRESOLVED" in codes(result)
    assert observations(result, "ROOT_TEMPLATE")[0].routes[0].components[0].mesh is None


def test_extra_unrecognized_map_member_is_not_silently_ignored(tmp_path):
    maps = node("Equipment", "", node("Visuals", "", node("Object", attr("MapKey", "race"), node("MapValue", attr("Object", "vr")) + node("FutureComponent", attr("Object", "hidden")))))
    result = resolver()(census(tmp_path, root(children=maps), visuals=visual("vr")), ())
    assert "EQUIPMENT_MAP_STRUCTURE_UNRESOLVED" in codes(result)


def test_missing_declared_dependency_blocks_otherwise_resolved_cc(tmp_path):
    src = module_census(tmp_path, SOURCE_UUID, {}, ((DEP_UUID, "1"),))
    assert "DEPENDENCY_MISSING" in codes(resolver()(src, ()))


def test_dependency_cycle_is_explicit_and_does_not_recurse_forever(tmp_path):
    src = module_census(tmp_path / "src", SOURCE_UUID, {}, ((DEP_UUID, "1"),))
    dep = module_census(tmp_path / "dep", DEP_UUID, {}, ((SOURCE_UUID, "1"),))
    assert "DEPENDENCY_CYCLE" in codes(resolver()(src, (dep,)))


def test_root_parent_inherited_direct_route_keeps_parent_source_id(tmp_path):
    src = census(tmp_path, root("parent", attr("VisualTemplate", "vr")) + root("child", attr("ParentTemplateId", "parent")), visuals=visual("vr"))
    result = resolver()(src, ())
    parent, child = observations(result, "ROOT_TEMPLATE")
    assert child.routes[0].source_observation_id == parent.source_observation_id
    assert child.routes[0].visual_references == ("vr",)
    assert parent.source_observation_id in child.related_observation_ids


def test_character_visual_body_evidence_kept_without_name_inference(tmp_path):
    body = node("Resource", attr("ID", "body") + attr("Name", "HUM_F_BCB") + attr("BodyType", "1") + attr("BodyShape", "0") + attr("RaceUUID", "race"))
    src = census(tmp_path, extras={"body.lsx": bank("CharacterVisualBank", body)})
    result = resolver()(src, ())
    observation, = observations(result, "BODY_FAMILY")
    assert [(k, v) for k, v, _ in observation.body_evidence] == [("BodyType", "1"), ("BodyShape", "0"), ("RaceUUID", "race")]
    assert observation.body_tuple is None
    assert "CHARACTER_VISUAL_MAPPING_UNRESOLVED" in codes(result)


def test_legacy_visualset_route_spelling_and_uuid_case_preserve_raw_values(tmp_path):
    vr = "abcdefab-1111-2222-3333-abcdefabcdef"
    maps = node("VisualSet", "", node("Visuals", attr("MapKey", "race"), node("MapValue", attr("Object", vr.upper()))))
    result = resolver()(census(tmp_path, root(children=maps), visuals=visual(vr)), ())
    route = observations(result, "ROOT_TEMPLATE")[0].routes[0]
    assert route.visual_references == (vr.upper(),)
    assert route.components[0].mesh is not None


def test_dependency_cannot_mutate_retained_census_with_fake_lists(tmp_path):
    src = census(tmp_path, root())
    with pytest.raises(ValueError, match="CENSUS_INCONSISTENT"):
        resolver()(src, (replace(src, definitions=list(src.definitions)),))


def test_inherited_dependency_reference_does_not_hide_source_override(tmp_path):
    dep = module_census(tmp_path / "dep", DEP_UUID, {"Public/Example/Stats/parent.txt":
        b'new entry "Parent"\ntype "Armor"\ndata "RootTemplate" "root"\n',
        "root.lsx": bank("Templates", root(extra=attr("VisualTemplate", "dependency-vr")))})
    src = module_census(tmp_path / "src", SOURCE_UUID, {"Public/Example/Stats/child.txt":
        b'new entry "Child"\ntype "Armor"\nusing "Parent"\n',
        "root.lsx": bank("Templates", root(extra=attr("VisualTemplate", "override-vr")))}, ((DEP_UUID, "1"),))
    result = resolver()(src, (dep,))
    child, = observations(result, "NAMED_STATS")
    assert child.routes == ()
    assert "ROOT_TEMPLATE_AMBIGUOUS" in codes(result)


def test_same_mesh_path_in_source_and_dependency_has_no_guessed_winner(tmp_path):
    dep = module_census(tmp_path / "dep", DEP_UUID, {"visual.lsx": bank("VisualBank", visual("vr")), "Assets/robe.GR2": b"dep"})
    src = module_census(tmp_path / "src", SOURCE_UUID, {"root.lsx": bank("Templates", root(extra=attr("VisualTemplate", "vr"))), "Assets/robe.GR2": b"main"}, ((DEP_UUID, "1"),))
    result = resolver()(src, (dep,))
    assert observations(result, "ROOT_TEMPLATE")[0].routes[0].components[0].mesh is None
    assert "MESH_SOURCE_AMBIGUOUS" in codes(result)


def test_duplicate_census_input_is_refused_not_reindexed(tmp_path):
    src = census(tmp_path, root())
    with pytest.raises(ValueError, match="CENSUS_INPUT_DUPLICATE"):
        resolver()(src, (src,))


def test_cc_unhandled_child_is_visible_as_semantic_gap(tmp_path):
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr"), node("FutureVisuals", attr("Object", "other")))
    result = resolver()(census(tmp_path, visuals=visual("vr"), extras={"shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root")}), ())
    assert "CREATION_STRUCTURE_UNRESOLVED" in codes(result)


def test_repeated_direct_reference_has_exact_distinct_attribute_locators(tmp_path):
    src = census(tmp_path, root(extra=attr("VisualTemplate", "vr") + attr("VisualTemplate", "vr")), visuals=visual("vr"))
    result = resolver()(src, ())
    routes = observations(result, "ROOT_TEMPLATE")[0].routes
    assert [r.locator for r in routes] == [
        "/save[1]/region[1]/node[1]/children[1]/node[1]/attribute[2]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/attribute[3]"]


def test_ambiguous_race_scalar_retains_all_observed_keys(tmp_path):
    maps = node("Equipment", "", node("Visuals", "", node("Object", attr("MapKey", "race-a") + attr("MapKey", "race-b"), node("MapValue", attr("Object", "vr")))))
    result = resolver()(census(tmp_path, root(children=maps), visuals=visual("vr")), ())
    route = observations(result, "ROOT_TEMPLATE")[0].routes[0]
    assert route.equipment_race is None
    assert route.equipment_race_values == ("race-a", "race-b")
    assert "EQUIPMENT_RACE_KEY_UNRESOLVED" in codes(result)


def test_relocation_does_not_change_creation_observation_identity(tmp_path):
    a = resolver()(census(tmp_path / "a", root(extra=attr("VisualTemplate", "vr")), visuals=visual("vr")), ())
    b = resolver()(census(tmp_path / "b", root(extra=attr("VisualTemplate", "vr")), visuals=visual("vr")), ())
    assert [o.observation_id for o in a.observations] == [o.observation_id for o in b.observations]
    assert a.source_observation_ids == b.source_observation_ids


def test_accessory_join_cannot_borrow_its_sibling_dependency_for_shared_visual(tmp_path):
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr"))
    dep_a = module_census(tmp_path / "a", DEP_UUID, {"shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root")})
    dep_b = module_census(tmp_path / "b", OTHER_UUID, {"visual.lsx": bank("VisualBank", visual("vr")), "Assets/robe.GR2": b"sibling mesh"})
    accessory = node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"), node("VisualUUIDs", attr("Object", "shared")))
    src = module_census(tmp_path / "s", SOURCE_UUID, {"sets.lsx": bank("CharacterCreationAccessorySets", accessory, "root")}, ((DEP_UUID, "1"), (OTHER_UUID, "1")))
    result = resolver()(src, (dep_a, dep_b))
    component = observations(result, "CHARACTER_CREATION_ACCESSORY_SET")[0].routes[0].components[0]
    assert component.mesh is None
    assert component.candidate_observation_ids == ()
    assert {"REFERENCE_DEPENDENCY_UNDECLARED", "VISUAL_BANK_MISSING"} <= codes(result)
    assert not result.creation_paths_complete


def test_accessory_join_accepts_shared_visuals_own_exact_dependency(tmp_path):
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr"))
    dep_a = module_census(tmp_path / "a", DEP_UUID, {"shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root")}, ((OTHER_UUID, "1"),))
    dep_b = module_census(tmp_path / "b", OTHER_UUID, {"visual.lsx": bank("VisualBank", visual("vr")), "Assets/robe.GR2": b"declared mesh"})
    accessory = node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"), node("VisualUUIDs", attr("Object", "shared")))
    src = module_census(tmp_path / "s", SOURCE_UUID, {"sets.lsx": bank("CharacterCreationAccessorySets", accessory, "root")}, ((DEP_UUID, "1"),))
    result = resolver()(src, (dep_a, dep_b))
    component = observations(result, "CHARACTER_CREATION_ACCESSORY_SET")[0].routes[0].components[0]
    assert component.mesh.sha256 == digest(b"declared mesh")
    assert component.reference_owner_observation_id == dep_a.definitions[0].observation_id
    assert component.mesh_source.module.uuid == OTHER_UUID
    assert result.creation_paths_complete


@pytest.mark.parametrize("location", ["dependency_shared", "accessory_item", "accessory_item_attribute"])
def test_cc_dependency_and_nested_item_structure_are_validated(tmp_path, location):
    future = node("FutureVisuals", attr("Object", "hidden"))
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr"), future if location == "dependency_shared" else "")
    dep = module_census(tmp_path / "dep", DEP_UUID, {"shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root"),
        "visual.lsx": bank("VisualBank", visual("vr")), "Assets/robe.GR2": b"real fixture mesh"})
    accessory = node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"),
        node("VisualUUIDs", attr("Object", "shared") + (attr("FutureVisual", "hidden") if location == "accessory_item_attribute" else ""), future if location == "accessory_item" else ""))
    src = module_census(tmp_path / "src", SOURCE_UUID, {"set.lsx": bank("CharacterCreationAccessorySets", accessory, "root")}, ((DEP_UUID, "1"),))
    result = resolver()(src, (dep,))
    assert "CREATION_STRUCTURE_UNRESOLVED" in codes(result)
    assert not result.creation_paths_complete
    assert len(observations(result, "CHARACTER_CREATION_ACCESSORY_SET")) == 1


def test_repeated_map_object_attributes_have_distinct_exact_locators(tmp_path):
    maps = node("Equipment", "", node("Visuals", "", node("Object", attr("MapKey", "race"), node("MapValue", attr("Object", "vr") + attr("Object", "vr")))))
    result = resolver()(census(tmp_path, root(children=maps), visuals=visual("vr")), ())
    route = observations(result, "ROOT_TEMPLATE")[0].routes[0]
    assert route.visual_references == ("vr", "vr")
    assert [c.locator for c in route.components] == [
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/children[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[1]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/children[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[2]"]


def test_cc_attribute_occurrences_keep_declaring_owner_and_accessory_edge(tmp_path):
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr") + attr("VisualResource", "vr"))
    dep = module_census(tmp_path / "dep", DEP_UUID, {"shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root"),
        "visual.lsx": bank("VisualBank", visual("vr")), "Assets/robe.GR2": b"fixture mesh"})
    accessory = node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"),
        node("VisualUUIDs", attr("Object", "shared") + attr("Object", "shared")))
    src = module_census(tmp_path / "src", SOURCE_UUID, {"set.lsx": bank("CharacterCreationAccessorySets", accessory, "root")}, ((DEP_UUID, "1"),))
    result = resolver()(src, (dep,))
    route = observations(result, "CHARACTER_CREATION_ACCESSORY_SET")[0].routes[0]
    shared_id = dep.definitions[0].observation_id
    assert [c.locator for c in route.components] == [
        "/save[1]/region[1]/node[1]/children[1]/node[1]/attribute[3]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/attribute[4]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/attribute[3]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/attribute[4]"]
    assert [c.reference_owner_observation_id for c in route.components] == [shared_id] * 4
    assert [c.accessory_locator for c in route.components] == [
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[1]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[1]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[2]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[2]"]
    assert route.shared_visual_locators == (
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[1]",
        "/save[1]/region[1]/node[1]/children[1]/node[1]/children[1]/node[1]/attribute[2]")


def test_standalone_cc_repeated_visual_attributes_have_exact_locators(tmp_path):
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr") + attr("VisualResource", "vr"))
    src = census(tmp_path, visuals=visual("vr"), extras={"shared.lsx": bank("CharacterCreationSharedVisuals", shared, "root")})
    result = resolver()(src, ())
    component_a, component_b = observations(result, "CHARACTER_CREATION_SHARED_VISUAL")[0].routes[0].components
    assert component_a.locator.endswith("/attribute[3]")
    assert component_b.locator.endswith("/attribute[4]")


def test_exact_race_components_duplicates_and_direct_visual_all_survive(tmp_path):
    src = census(tmp_path, root(extra=attr("VisualTemplate", "direct"), children=mapped()),
                 visuals=visual("vr-a") + visual("vr-b") + visual("direct"))
    result = resolver()(src, ())
    observation, = observations(result, "ROOT_TEMPLATE")
    assert observation.source_observation_id == src.definitions[0].observation_id
    assert [(p.kind, p.equipment_race, p.visual_references) for p in observation.routes] == [
        ("DIRECT_VISUAL", None, ("direct",)), ("EQUIPMENT_RACE", "race-one", ("vr-b", "vr-a")),
        ("EQUIPMENT_RACE", "race-two", ("vr-a", "vr-a"))]
    assert [c.mesh.sha256 for c in observation.routes[2].components] == [digest(b"exact mesh bytes")] * 2
    assert len(observations(result, "BODY_FAMILY")) == 3
    assert all(o.body_tuple is None for o in observations(result, "BODY_FAMILY"))
    assert "BODY_TUPLE_UNRESOLVED" in codes(result)
    assert result.source_observation_ids == tuple(d.observation_id for d in src.definitions)


def test_named_stats_inherited_root_and_distinct_slot_are_separate_paths(tmp_path):
    src = census(tmp_path, root(extra=attr("Stats", "Base"), children=mapped()),
        b'new entry "Base"\ntype "Armor"\ndata "RootTemplate" "root"\ndata "Slot" "Breast"\n'
        b'new entry "Child"\ntype "Armor"\nusing "Base"\ndata "Slot" "Underwear"\n',
        visual("vr-a") + visual("vr-b"))
    result = resolver()(src, ())
    base, child = observations(result, "NAMED_STATS")
    assert base.slot_values == ("Breast",)
    assert child.slot_values == ("Underwear",)
    assert child.root_references == ("root",)
    assert child.routes[0].visual_references == ("vr-b", "vr-a")
    inherited, = observations(result, "INHERITED_SPAWN")
    assert inherited.source_observation_id == child.source_observation_id
    assert base.source_observation_id in inherited.related_observation_ids
    assert child.observation_id != inherited.observation_id


@pytest.mark.parametrize("stats,expected", [
    (b'new entry "A"\ntype "Armor"\nusing "Missing"\n', "STATS_PARENT_MISSING"),
    (b'new entry "A"\ntype "Armor"\nusing "B"\nnew entry "B"\ntype "Armor"\nusing "A"\n', "STATS_INHERITANCE_CYCLE"),
    (b'new entry "A"\ntype "Armor"\nusing "B"\nnew entry "B"\ntype "Armor"\nnew entry "B"\ntype "Object"\n', "STATS_PARENT_AMBIGUOUS"),
])
def test_unresolved_stats_inheritance_never_drops_discovery(tmp_path, stats, expected):
    src = census(tmp_path, stats=stats)
    result = resolver()(src, ())
    assert len(observations(result, "NAMED_STATS")) == len(src.definitions)
    assert expected in codes(result)
    assert not result.creation_paths_complete


def test_cc_piercing_shared_join_preserves_raw_unassigned_visual_slot(tmp_path):
    sets = node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"),
                node("VisualUUIDs", attr("Object", "shared")) + node("VisualUUIDs", attr("Object", "shared")))
    shared = node("CharacterCreationSharedVisual", attr("UUID", "shared") + attr("SlotName", "Piercing") + attr("VisualResource", "vr"))
    src = census(tmp_path, visuals=visual("vr", extra=attr("Slot", "Unassigned")), extras={
        "ccsets.lsx": bank("CharacterCreationAccessorySets", sets, "root"),
        "ccshared.lsx": bank("CharacterCreationSharedVisuals", shared, "root")})
    result = resolver()(src, ())
    accessory, = observations(result, "CHARACTER_CREATION_ACCESSORY_SET")
    assert accessory.scope == "NON_GARMENT_PIERCING"
    assert accessory.slot_values == ("Piercing",)
    assert accessory.routes[0].shared_visual_references == ("shared", "shared")
    assert accessory.routes[0].visual_references == ("vr", "vr")
    assert len(accessory.routes[0].components) == 2
    component = accessory.routes[0].components[0]
    assert component.visual_slots == ("Unassigned",)
    assert component.mesh.relative_path == "Assets/robe.GR2"
    assert component.mesh.sha256 == digest(b"exact mesh bytes")
    assert len(observations(result, "CHARACTER_CREATION_SHARED_VISUAL")) == 1
    assert not observations(result, "NAMED_STATS")


@pytest.mark.parametrize("roots,expected", [
    (root(extra=attr("ParentTemplateId", "absent")), "ROOT_PARENT_MISSING"),
    (root("a", attr("ParentTemplateId", "b")) + root("b", attr("ParentTemplateId", "a")), "ROOT_INHERITANCE_CYCLE"),
    (root("a", attr("ParentTemplateId", "b")) + root("b") + root("b"), "ROOT_PARENT_AMBIGUOUS"),
])
def test_unresolved_root_parent_is_discovery_not_empty_success(tmp_path, roots, expected):
    src = census(tmp_path, roots)
    result = resolver()(src, ())
    assert len(observations(result, "ROOT_TEMPLATE")) == len(src.definitions)
    assert expected in codes(result)


@pytest.mark.parametrize("visuals,expected", [("", "VISUAL_BANK_MISSING"), (visual("vr", "Assets/missing.GR2"), "MESH_SOURCE_MISSING"),
                                           (visual("vr") + visual("vr"), "VISUAL_BANK_AMBIGUOUS")])
def test_missing_or_ambiguous_visuals_preserve_exact_reference(tmp_path, visuals, expected):
    src = census(tmp_path, root(extra=attr("VisualTemplate", "vr")), visuals=visuals)
    result = resolver()(src, ())
    assert observations(result, "ROOT_TEMPLATE")[0].routes[0].visual_references == ("vr",)
    assert expected in codes(result)


def test_no_display_prefix_body_slot_or_mode_inference(tmp_path):
    src = census(tmp_path, root(extra=attr("Name", "TIF_F_BCB_Underwear")), visuals=visual("HUM_F_Body"))
    result = resolver()(src, ())
    observed, = observations(result, "ROOT_TEMPLATE")
    assert observed.body_tuple is None
    assert observed.slot_values == ()
    assert observed.scope == "UNRESOLVED"


def test_retained_bytes_only_and_tampered_census_rejected(tmp_path, monkeypatch):
    src = census(tmp_path, root(extra=attr("VisualTemplate", "vr")), visuals=visual("vr"))
    resolve = resolver()
    def no_open(*args, **kwargs):
        raise AssertionError("Creation joins must not open source files")
    monkeypatch.setattr(Path, "open", no_open)
    assert observations(resolve(src, ()), "ROOT_TEMPLATE")[0].routes[0].components[0].mesh
    with pytest.raises(ValueError, match="CENSUS_INCONSISTENT"):
        resolve(replace(src, definitions=()), ())
    with pytest.raises(TypeError, match="ResourceCensus"):
        resolve({"verified": True}, ())


def discovery_api():
    module = importlib.import_module("workstreams.source_profile_census.creation_paths")
    assert hasattr(module, "discover_creation_paths"), "Independent source creation discovery is not implemented"
    return module


def test_independent_discovery_preserves_unresolved_repeated_route_locators_without_emission(tmp_path, monkeypatch):
    src = census(tmp_path, root(extra=attr("VisualTemplate", "absent"), children=mapped()),
        b'new entry "Child"\ntype "Armor"\nusing "MissingParent"\ndata "RootTemplate" "root"\n')
    module = discovery_api()
    def forbidden(*args, **kwargs):
        raise AssertionError("Discovery must not invoke observation or route emission")
    for name in ("run", "observe", "garment", "character_creation", "routes"):
        monkeypatch.setattr(module._Resolver, name, forbidden)
    result = module.discover_creation_paths(src, ())
    assert [r.kind for r in result] == ["ROOT_TEMPLATE", "BODY_FAMILY", "BODY_FAMILY", "BODY_FAMILY",
        "NAMED_STATS", "INHERITED_SPAWN", "BODY_FAMILY", "BODY_FAMILY", "BODY_FAMILY"]
    root_bodies = result[1:4]
    assert root_bodies[0].declaration_locators[0].endswith("/attribute[2]")
    assert len(root_bodies[2].declaration_locators) == 3
    assert root_bodies[2].declaration_locators[1] != root_bodies[2].declaration_locators[2]
    assert root_bodies[1].observation_id != root_bodies[2].observation_id


def test_independent_discovery_keeps_missing_root_and_repeated_accessory_declarations(tmp_path):
    src = census(tmp_path, stats=b'new entry "Child"\ntype "Armor"\nusing "Missing"\ndata "RootTemplate" "Absent"\n', extras={
        "sets.lsx": bank("CharacterCreationAccessorySets", node("CharacterCreationAccessorySet", attr("UUID", "set") + attr("SlotName", "Piercing"),
            node("VisualUUIDs", attr("Object", "absent")) + node("VisualUUIDs", attr("Object", "absent"))), "root")})
    result = discovery_api().discover_creation_paths(src, ())
    assert [r.kind for r in result] == ["NAMED_STATS", "INHERITED_SPAWN", "CHARACTER_CREATION_ACCESSORY_SET"]
    assert "line:4" in result[0].declaration_locators
    assert len(result[2].declaration_locators) == 3
    assert result[2].declaration_locators[1] != result[2].declaration_locators[2]


def test_independent_discovery_requires_verified_definitions(tmp_path):
    src = census(tmp_path, root())
    with pytest.raises(ValueError, match="CENSUS_INCONSISTENT"):
        discovery_api().discover_creation_paths(replace(src, definitions=()), ())
