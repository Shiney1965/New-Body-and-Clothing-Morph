"""Literal semantic controls, through the real hash-verifying snapshot boundary."""

from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from workstreams.source_profile_census.snapshot import load_snapshot
from workstreams.source_profile_census.tests.test_snapshot import (
    META, META_PATH, MODULE, TOOL, digest, write, write_json,
)


def parser():
    name = "workstreams.source_profile_census.resources"
    assert importlib.util.find_spec(name) is not None, "ResourceCensus parser is not implemented"
    return importlib.import_module(name)


def frozen(root, files, converted=None):
    """Real portable evidence files; never construct a success-flag snapshot."""
    files = {META_PATH: META, **files}
    package = write(root, "source.pak", b"synthetic archive boundary")
    package["recorded_path"] = "Z:/frozen/source.pak"
    for path, data in files.items():
        write(root, "extract/" + path, data)
    manifest = {
        "schema": "clothmorph.source-content-manifest", "schema_version": 1,
        "pak_path": package["recorded_path"], "pak_sha256": package["sha256"],
        "extract_root": "Z:/frozen/extract", "tool_sha256": TOOL,
        "file_count": len(files),
        "files": [{"relative_path": p, "bytes": len(b), "sha256": digest(b)} for p, b in files.items()],
    }
    config = {
        "root": root, "profile_id": "exact-example", "role": "garment_source",
        "module": MODULE, "metadata_path": META_PATH, "package": package,
        "extract_root": {"path": "extract", "recorded_path": "Z:/frozen/extract"},
        "content_manifest": write_json(root, "manifest.json", manifest),
        "listing": write(root, "listing.txt", "".join(f"{p}\t{len(b)}\t72\r\n" for p, b in files.items()).encode()),
        "tool_sha256": TOOL, "conversions": [],
    }
    if converted:
        rows = []
        for index, (source, data) in enumerate(converted.items()):
            output = f"bank-{index}.lsx"
            write(root, "inspection/" + output, data)
            rows.append({"source": "Z:/frozen/extract/" + source, "source_sha256": digest(files[source]),
                         "inspection": "Z:/frozen/inspection/" + output, "inspection_sha256": digest(data)})
        conversion = {
            "schema": "clothmorph.source-bank-conversion-evidence", "schema_version": 1,
            "tool": {"sha256": TOOL, "arguments": ["-g", "bg3", "-a", "convert-resource", "-s", "{source}",
                                                         "-d", "{inspection}", "-i", "lsf", "-o", "lsx"]},
            "conversions": rows,
        }
        config["conversions"] = [{"manifest": write_json(root, "conversion.json", conversion),
                                  "inspection_root": {"path": "inspection", "recorded_path": "Z:/frozen/inspection"}}]
    return load_snapshot(config)


def bank(region, records, wrapper=None):
    return (f'<save><version major="4"/><region id="{region}"><node id="{wrapper or region}">'
            f'<children>{records}</children></node></region></save>').encode()


VISUAL = bank("VisualBank", '''<node id="Resource" custom="kept"><attribute id="ID" type="FixedString" value="vr-one"/>
<attribute id="Name" type="LSString" value="Étoile"/><attribute id="SourceFile" value="Assets/robe.GR2"/>
<children><node id="Objects"><attribute id="ObjectID" value="second"/><attribute id="MaterialID" value="mat-b"/></node>
<node id="Objects"><attribute id="ObjectID" value="first"/><attribute id="MaterialID" value="mat-a"/></node>
<node id="Objects"><attribute id="ObjectID" value="second"/><attribute id="MaterialID" value="mat-b"/></node></children></node>''')


def values(node, name):
    return tuple(dict(child.attributes).get("value") for child in node.children
                 if child.tag == "attribute" and dict(child.attributes).get("id") == name)


def children(node):
    return tuple(child for group in node.children if group.tag == "children" for child in group.children)


def codes(census):
    return {issue.code for issue in census.issues}


def test_visual_objects_materials_and_duplicate_components_keep_source_order(tmp_path):
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/bank.lsx": VISUAL}))
    definition, = census.definitions
    assert definition.kind == "VisualBank"
    assert definition.resource_id == "vr-one"
    assert definition.node.attributes == (("id", "Resource"), ("custom", "kept"))
    assert values(definition.node, "Name") == ("Étoile",)
    assert tuple((values(n, "ObjectID"), values(n, "MaterialID")) for n in children(definition.node)) == (
        (("second",), ("mat-b",)), (("first",), ("mat-a",)), (("second",), ("mat-b",)),
    )
    assert definition.locator == "/save[1]/region[1]/node[1]/children[1]/node[1]"
    assert definition.source.original.sha256 == digest(VISUAL)
    assert definition.source.package.sha256 == census.snapshot.package.sha256
    assert definition.source.module.uuid == MODULE["uuid"]
    assert definition.source.profile_id == "exact-example"
    assert definition.source.representation == "PACKED_XML"
    assert not census.issues


ROUTE = bank("Templates", '''<node id="GameObjects"><attribute id="MapKey" value="root-one"/>
<attribute id="Stats" value="external-stats"/><children><node id="VisualSet"><children>
<node id="Visuals"><attribute id="MapKey" value="race-one"/><children><node id="MapValue"><attribute id="Object" value="vr-b"/></node><node id="MapValue"><attribute id="Object" value="vr-a"/></node></children></node>
<node id="Visuals"><attribute id="MapKey" value="race-two"/><children><node id="MapValue"><attribute id="Object" value="vr-a"/></node><node id="MapValue"><attribute id="Object" value="vr-a"/></node></children></node>
</children></node></children></node>''')


def test_literal_two_component_race_routes_are_not_reordered_or_deduplicated(tmp_path):
    result = parser().parse_resources(frozen(tmp_path, {"Public/Example/root.lsx": ROUTE}))
    root, = result.definitions
    assert root.kind == "RootTemplate"
    assert root.resource_id == "root-one"
    routes = children(children(root.node)[0])
    assert tuple((values(route, "MapKey"), tuple(values(n, "Object") for n in children(route))) for route in routes) == (
        (("race-one",), (("vr-b",), ("vr-a",))),
        (("race-two",), (("vr-a",), ("vr-a",))),
    )
    # A root remains discoverable without local Stats; joining is Task 3.
    assert values(root.node, "Stats") == ("external-stats",)


@pytest.mark.parametrize("region,node_id,key,kind", [
    ("CharacterVisualBank", "Resource", "ID", "CharacterVisualBank"),
    ("MaterialBank", "Resource", "ID", "MaterialBank"),
    ("TextureBank", "Resource", "ID", "TextureBank"),
    ("CharacterCreationAccessorySets", "CharacterCreationAccessorySet", "UUID", "CharacterCreationAccessorySet"),
    ("CharacterCreationSharedVisuals", "CharacterCreationSharedVisual", "UUID", "CharacterCreationSharedVisual"),
    ("CharacterCreationAppearanceVisuals", "CharacterCreationAppearanceVisual", "UUID", "CharacterCreationAppearanceVisual"),
    ("CharacterCreationEquipmentIcons", "CharacterCreationEquipmentIcon", "UUID", "CharacterCreationEquipmentIcon"),
])
def test_resource_families_preserve_every_attribute_and_nested_node(tmp_path, region, node_id, key, kind):
    data = bank(region, f'''<node id="{node_id}"><attribute id="{key}" type="guid" value="id-one"/>
<attribute id="DisplayName" type="TranslatedString" handle="h123" version="7"/>
<children><node id="Slots"><attribute id="Slot" value="Body"/><attribute id="VisualResource" value="body-vr"/></node>
<node id="Slots"><attribute id="Slot" value="Body"/><attribute id="VisualResource" value="other-vr"/></node></children></node>''',
                "root" if region.startswith("CharacterCreation") else None)
    census = parser().parse_resources(frozen(tmp_path, {"bank.lsx": data}))
    definition, = census.definitions
    assert definition.kind == kind
    assert definition.resource_id == "id-one"
    assert definition.node.children[1].attributes == (("id", "DisplayName"), ("type", "TranslatedString"), ("handle", "h123"), ("version", "7"))
    assert tuple(values(n, "VisualResource") for n in children(definition.node)) == (("body-vr",), ("other-vr",))
    assert not census.issues


def test_packed_conversion_and_bundled_text_are_separate_conflicting_observations(tmp_path):
    path = "Public/Example/bank.lsf"
    stale = VISUAL.replace(b"mat-b", b"old-mat")
    snapshot = frozen(tmp_path, {path: b"packed\x00", "Public/Example/bank.lsx": stale}, {path: VISUAL})
    census = parser().parse_resources(snapshot)
    assert len(census.definitions) == 2
    first, second = census.definitions
    assert first.source.representation == "CONVERTED_LSF"
    assert first.source.original.relative_path == path
    assert first.source.original.data == b"packed\x00"
    assert first.source.conversion == snapshot.conversions[0]
    assert first.source.inspection.data == VISUAL
    assert second.source.representation == "PACKED_XML"
    assert "DUPLICATE_DEFINITION_CONFLICT" in codes(census)
    conflict, = census.conflicts
    assert conflict.resource_id == "vr-one"
    assert conflict.kind == "VisualBank"
    assert conflict.observation_ids == tuple(d.observation_id for d in census.definitions)
    assert conflict.precedence == "UNRESOLVED"


def test_identical_duplicates_are_visible_and_no_last_writer_is_selected(tmp_path):
    census = parser().parse_resources(frozen(tmp_path, {"a.lsx": VISUAL, "b.lsx": VISUAL}))
    assert len(census.definitions) == 2
    assert len({d.observation_id for d in census.definitions}) == 2
    assert census.conflicts[0].content_equal is True
    assert census.conflicts[0].precedence == "UNRESOLVED"
    assert "DUPLICATE_DEFINITION_UNRESOLVED" in codes(census)


def test_every_input_is_accounted_unknown_regions_and_binary_are_not_empty_success(tmp_path):
    unknown = bank("FutureBank", '<node id="NewThing"><attribute id="ID" value="future"/></node>')
    census = parser().parse_resources(frozen(tmp_path, {"unknown.lsx": unknown, "missing.lsf": b"binary",
                                                       "body.GR2": b"mesh", "other.xyz": b"unknown"}))
    assert tuple((f.source.original.relative_path, f.status) for f in census.files) == (
        (META_PATH, "PARSED"), ("unknown.lsx", "UNSUPPORTED"), ("missing.lsf", "UNSUPPORTED"),
        ("body.GR2", "NON_DEFINITION_ASSET"), ("other.xyz", "UNSUPPORTED"),
    )
    assert {"UNKNOWN_XML_REGION", "BINARY_CONVERSION_MISSING", "UNSUPPORTED_FILE_FORMAT"} <= codes(census)
    assert census.files[1].document.children[1].attributes == (("id", "FutureBank"),)
    assert census.definition_parse_complete is False


@pytest.mark.parametrize("data,code", [
    (b"<save><region>", "XML_MALFORMED"),
    (b'<save><region id="VisualBank"><node id="Wrong"/></region></save>', "XML_STRUCTURE_UNSUPPORTED"),
    (b'<save><region id="VisualBank"><node id="VisualBank"><children><node id="Surprise"/></children></node></region></save>', "XML_STRUCTURE_UNSUPPORTED"),
    (b"<different/>", "XML_STRUCTURE_UNSUPPORTED"),
    (b'<!DOCTYPE save [<!ENTITY a "replacement">]><save>&a;</save>', "XML_DTD_FORBIDDEN"),
])
def test_unknown_and_malformed_xml_cannot_certify_parse_completeness(tmp_path, data, code):
    census = parser().parse_resources(frozen(tmp_path, {"bad.lsx": data}))
    assert code in codes(census)
    assert census.files[1].status == "UNSUPPORTED"
    assert not census.definition_parse_complete


def test_missing_or_duplicate_identity_attributes_preserve_nodes_and_block(tmp_path):
    data = bank("VisualBank", '<node id="Resource"/><node id="Resource"><attribute id="ID" value="a"/><attribute id="ID" value="b"/></node>')
    census = parser().parse_resources(frozen(tmp_path, {"bad.lsx": data}))
    assert len(census.definitions) == 2
    assert tuple(d.resource_id for d in census.definitions) == (None, None)
    assert {"DEFINITION_ID_MISSING", "DEFINITION_ID_AMBIGUOUS"} <= codes(census)
    assert values(census.definitions[1].node, "ID") == ("a", "b")


def test_stats_unicode_crlf_all_types_using_and_repeated_data_are_lossless(tmp_path):
    data = ('// header\r\nnew entry "Étoile"\r\ntype "Armor"\r\nusing "Base"\r\n'
            'data "Slot" "VanityBody"\r\ndata "Slot" "Underwear" // do not overwrite\r\n'
            'data "Description" "été; 🌙"\r\n\r\nnew entry "Base"\r\ntype "Object"\r\n').encode()
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Generated/Data/Armor.txt": data}))
    first, base = census.definitions
    assert (first.kind, first.resource_id, first.stats_types, first.stats_parents) == ("Stats", "Étoile", ("Armor",), ("Base",))
    assert first.stats_data == (("Slot", "VanityBody"), ("Slot", "Underwear"), ("Description", "été; 🌙"))
    assert base.stats_types == ("Object",)
    file = census.files[1]
    assert "".join(s.raw for s in file.statements).encode() == data
    assert first.locator == "line:2"
    assert first.statements[-1].raw == "\r\n"
    assert "STATS_DATA_REPEATED" in codes(census)
    relation = next(r for r in census.inheritances if r.child_observation_id == first.observation_id)
    assert relation.parent_name == "Base"
    assert relation.parent_observation_ids == (base.observation_id,)
    assert relation.status == "LOCAL_PARENT"


def test_stats_missing_cyclic_and_ambiguous_parents_are_observed_without_joining(tmp_path):
    data = b'new entry "A"\ntype "Armor"\nusing "B"\nnew entry "B"\ntype "Armor"\nusing "A"\nnew entry "C"\ntype "Armor"\nusing "Absent"\nnew entry "D"\ntype "Armor"\nusing "Parent"\nnew entry "Parent"\ntype "Armor"\nnew entry "Parent"\ntype "Object"\n'
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Generated/Data/Armor.txt": data}))
    assert tuple(d.resource_id for d in census.definitions) == ("A", "B", "C", "D", "Parent", "Parent")
    assert {"STATS_INHERITANCE_CYCLE", "STATS_PARENT_MISSING", "STATS_PARENT_AMBIGUOUS", "DUPLICATE_DEFINITION_CONFLICT"} <= codes(census)
    assert tuple(r.status for r in census.inheritances) == ("CYCLE", "CYCLE", "MISSING_PARENT", "AMBIGUOUS_PARENT")


@pytest.mark.parametrize("suffix,code", [
    ('mystery "value"\n', "STATS_STATEMENT_UNSUPPORTED"),
    ('data "Slot"\n', "STATS_STATEMENT_MALFORMED"),
    ('using "A"\nusing "B"\n', "STATS_PARENT_DECLARATION_AMBIGUOUS"),
    ('type "Object"\n', "STATS_TYPE_AMBIGUOUS"),
])
def test_stats_unknown_malformed_and_multiple_declarations_block_without_dropping_text(tmp_path, suffix, code):
    data = ('new entry "A"\ntype "Armor"\n' + suffix).encode()
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Generated/Data/Armor.txt": data}))
    assert code in codes(census)
    assert "".join(s.raw for s in census.files[1].statements).encode() == data
    assert len(census.definitions) == 1
    assert not census.definition_parse_complete


def test_stats_orphan_syntax_and_missing_type_are_not_empty_success(tmp_path):
    data = b'data "Slot" "Body"\nnew entry "NoType"\n'
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Generated/Data/Armor.txt": data}))
    assert {"STATS_ORPHAN_STATEMENT", "STATS_TYPE_MISSING"} <= codes(census)
    assert census.definitions[0].resource_id == "NoType"


def test_parser_uses_retained_bytes_and_never_reopens_local_paths(tmp_path, monkeypatch):
    snapshot = frozen(tmp_path, {"bank.lsx": VISUAL})
    module = parser()
    def forbidden(*args, **kwargs):
        raise AssertionError("Resource parser must not open local files")
    monkeypatch.setattr(Path, "open", forbidden)
    census = module.parse_resources(snapshot)
    assert census.definitions[0].resource_id == "vr-one"


def test_success_dictionary_is_not_a_verified_snapshot():
    with pytest.raises(TypeError, match="FrozenSnapshot"):
        parser().parse_resources({"verified": True, "files": []})


@pytest.mark.parametrize("mutation", ["original_bytes", "rehash_original", "inspection_bytes", "conversion_binding"])
def test_relabelled_or_changed_retained_bytes_are_rejected(tmp_path, mutation):
    snapshot = frozen(tmp_path, {"bank.lsf": b"binary"}, {"bank.lsf": VISUAL})
    if mutation in ("original_bytes", "rehash_original"):
        changed = replace(snapshot.files[1], data=b"changed", **({"sha256": digest(b"changed")} if mutation == "rehash_original" else {}))
        snapshot = replace(snapshot, files=(snapshot.files[0], changed))
    elif mutation == "inspection_bytes":
        converted = snapshot.conversions[0]
        snapshot = replace(snapshot, conversions=(replace(converted, inspection=replace(converted.inspection, data=b"<save/>")),))
    else:
        snapshot = replace(snapshot, conversions=(replace(snapshot.conversions[0], source_sha256="A" * 64),))
    with pytest.raises(ValueError, match="SNAPSHOT_INCONSISTENT"):
        parser().parse_resources(snapshot)


def test_stats_bom_unicode_separators_quotes_and_literal_backslashes_survive(tmp_path):
    data = ('\ufeffnew entry "Étoile"\r\ntype "CustomType"\r\n'
            'data "Description" "a\u2028b\u0085c \\"quoted\\""\r\n'
            'data "Path" "Assets\\new\\thing"\r\n').encode()
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Data.txt": data}))
    definition, = census.definitions
    assert definition.resource_id == "Étoile"
    assert definition.stats_types == ("CustomType",)
    assert definition.stats_data == (("Description", 'a\u2028b\u0085c "quoted"'), ("Path", "Assets\\new\\thing"))
    assert "".join(s.raw for s in census.files[1].statements).encode() == data
    assert tuple(s.line for s in census.files[1].statements) == (1, 2, 3, 4)
    assert not census.issues


def test_xml_comments_processing_instructions_and_mixed_text_are_retained(tmp_path):
    data = VISUAL.replace(b'<children><node id="Objects">', b'<children>lead<!-- comment --><?audit exact?><node id="Objects">', 1)
    census = parser().parse_resources(frozen(tmp_path, {"bank.lsx": data}))
    definition, = census.definitions
    group = next(child for child in definition.node.children if child.tag == "children")
    assert group.text == "lead"
    assert tuple(n.tag for n in group.children) == ("#comment", "#processing-instruction", "node", "node", "node")
    assert group.children[0].text == " comment "
    assert group.children[1].text == "audit exact"
    assert census.files[1].source.original.data == data


def test_empty_save_and_nested_version_content_are_not_accepted_as_empty_banks(tmp_path):
    census = parser().parse_resources(frozen(tmp_path, {"empty.lsx": b"<save/>",
                                                       "hidden.lsx": b'<save><version><region id="VisualBank"/></version></save>'}))
    assert tuple(f.status for f in census.files[1:]) == ("UNSUPPORTED", "UNSUPPORTED")
    assert "XML_STRUCTURE_UNSUPPORTED" in codes(census)


def test_parse_is_deterministic_and_raw_observation_ids_are_relocation_stable(tmp_path):
    left = frozen(tmp_path / "left", {"bank.lsx": VISUAL})
    right = frozen(tmp_path / "right", {"bank.lsx": VISUAL})
    first = parser().parse_resources(left)
    assert parser().parse_resources(left) == first
    assert tuple(d.observation_id for d in first.definitions) == tuple(d.observation_id for d in parser().parse_resources(right).definitions)


def test_unknown_stats_syntax_still_preserves_later_named_entries(tmp_path):
    data = b'new treasuretable "Example"\nobject category "I_Obj",1,0,0,0,0,0,0,0\nnew entry "Later"\ntype "Object"\n'
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Generated/Data/Mixed.txt": data}))
    assert tuple(d.resource_id for d in census.definitions) == ("Later",)
    assert "STATS_STATEMENT_UNSUPPORTED" in codes(census)
    assert "".join(s.raw for s in census.files[1].statements).encode() == data


def test_multiple_known_and_unknown_regions_all_remain_discoverable(tmp_path):
    extra = bank("MaterialBank", '<node id="Resource"><attribute id="ID" value="material"/></node>')
    data = VISUAL.replace(b"</save>", extra[6:] + b'<region id="Future"/></save>')
    # Construct literal valid XML, retaining both known banks and the unknown one.
    data = data.replace(b'</save><region id="Future"/>', b'<region id="Future"/>')
    census = parser().parse_resources(frozen(tmp_path, {"mixed.lsx": data}))
    assert tuple(d.kind for d in census.definitions) == ("VisualBank", "MaterialBank")
    assert "UNKNOWN_XML_REGION" in codes(census)


def test_dropped_conversion_manifest_row_cannot_be_disguised_as_unconverted(tmp_path):
    snapshot = frozen(tmp_path, {"bank.lsf": b"binary"}, {"bank.lsf": VISUAL})
    snapshot = replace(snapshot, conversions=(), unconverted_binary_paths=("bank.lsf",))
    with pytest.raises(ValueError, match="SNAPSHOT_INCONSISTENT"):
        parser().parse_resources(snapshot)


@pytest.mark.parametrize("row", [-1, True])
def test_conversion_locator_must_be_an_exact_nonnegative_row(tmp_path, row):
    snapshot = frozen(tmp_path, {"a.lsf": b"first", "b.lsf": b"second"}, {"a.lsf": VISUAL, "b.lsf": VISUAL})
    # Both -1 and True index row 1 in Python; neither is a valid evidence row.
    last = replace(snapshot.conversions[-1], manifest_row=row)
    snapshot = replace(snapshot, conversions=(*snapshot.conversions[:-1], last))
    with pytest.raises(ValueError, match="SNAPSHOT_INCONSISTENT"):
        parser().parse_resources(snapshot)


def test_mutable_forged_snapshot_container_is_not_an_immutable_parse_input(tmp_path):
    snapshot = frozen(tmp_path, {"bank.lsx": VISUAL})
    snapshot = replace(snapshot, files=list(snapshot.files))
    with pytest.raises(ValueError, match="SNAPSHOT_INCONSISTENT"):
        parser().parse_resources(snapshot)


def test_stats_multiple_parent_declarations_never_look_like_one_selected_parent(tmp_path):
    data = b'new entry "Child"\ntype "Armor"\nusing "A"\nusing "B"\nnew entry "A"\ntype "Armor"\nnew entry "B"\ntype "Armor"\n'
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Data.txt": data}))
    assert tuple(r.status for r in census.inheritances) == ("DECLARATION_AMBIGUOUS", "DECLARATION_AMBIGUOUS")
    assert tuple(r.parent_name for r in census.inheritances) == ("A", "B")


def test_duplicate_data_and_type_in_different_stats_files_do_not_hide_conflicts(tmp_path):
    first = b'new entry "Duplicate"\ntype "Armor"\ndata "Slot" "Body"\n'
    second = b'new entry "Duplicate"\ntype "Armor"\ndata "Slot" "Underwear"\n'
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/a.txt": first, "Public/Example/Stats/b.txt": second}))
    assert len(census.definitions) == 2
    assert census.conflicts[0].content_equal is False
    assert "DUPLICATE_DEFINITION_CONFLICT" in codes(census)


def test_unknown_nested_record_content_is_retained_without_flattening(tmp_path):
    data = bank("MaterialBank", '<node id="Resource"><attribute id="ID" value="mat"/><children><node id="Vector3Parameters"><attribute id="Parameter" value="Color"/><attribute id="Value" type="fvec3" value="1 2 3"/><children><node id="FutureProperty"><attribute id="New" value="kept"/></node></children></node></children></node>')
    census = parser().parse_resources(frozen(tmp_path, {"material.lsx": data}))
    parameter, = children(census.definitions[0].node)
    nested, = children(parameter)
    assert values(parameter, "Value") == ("1 2 3",)
    assert nested.attributes == (("id", "FutureProperty"),)
    assert values(nested, "New") == ("kept",)


def test_xml_duplicate_conflict_detects_changed_mixed_tail_content(tmp_path):
    first = VISUAL.replace(b'<children><node id="Objects">', b'<children><node id="Hint"/>first<node id="Objects">', 1)
    second = first.replace(b"/>first<", b"/>second<")
    census = parser().parse_resources(frozen(tmp_path, {"a.lsx": first, "b.lsx": second}))
    assert census.conflicts[0].content_equal is False
    assert "DUPLICATE_DEFINITION_CONFLICT" in codes(census)


def test_uuid_spelling_case_does_not_hide_duplicate_resource_identity(tmp_path):
    first = VISUAL.replace(b"vr-one", b"abcdefab-1111-2222-3333-abcdefabcdef")
    second = VISUAL.replace(b"vr-one", b"ABCDEFAB-1111-2222-3333-ABCDEFABCDEF")
    census = parser().parse_resources(frozen(tmp_path, {"a.lsx": first, "b.lsx": second}))
    assert len(census.conflicts) == 1
    assert len(census.definitions) == 2
    assert tuple(d.resource_id for d in census.definitions) == (
        "abcdefab-1111-2222-3333-abcdefabcdef", "ABCDEFAB-1111-2222-3333-ABCDEFABCDEF")


@pytest.mark.parametrize("name", ["BOM.txt", "wrong-extension.cfg"])
def test_text_containing_named_stats_is_discovered_or_explicitly_unsupported(tmp_path, name):
    data = b'\xef\xbb\xbfnew entry "Present"\r\ntype "Armor"\r\n'
    census = parser().parse_resources(frozen(tmp_path, {name: data}))
    if name.endswith(".txt"):
        assert tuple(d.resource_id for d in census.definitions) == ("Present",)
    else:
        assert census.files[1].status == "UNSUPPORTED"
        assert "UNSUPPORTED_FILE_FORMAT" in codes(census)


def test_ambiguous_parent_declaration_does_not_hide_cycle_or_missing_parent(tmp_path):
    data = b'new entry "A"\ntype "Armor"\nusing "A"\nusing "Absent"\n'
    census = parser().parse_resources(frozen(tmp_path, {"Public/Example/Stats/Data.txt": data}))
    assert {"STATS_PARENT_DECLARATION_AMBIGUOUS", "STATS_INHERITANCE_CYCLE", "STATS_PARENT_MISSING"} <= codes(census)
    assert tuple(r.parent_observation_ids for r in census.inheritances) == ((census.definitions[0].observation_id,), ())
