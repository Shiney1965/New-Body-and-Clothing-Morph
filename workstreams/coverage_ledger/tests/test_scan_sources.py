from pathlib import Path

from workstreams.coverage_ledger.scan_sources import SourceModule, scan_source


ROOT_XML = """<save><region id=\"Templates\"><node id=\"Templates\"><children>
<node id=\"GameObjects\"><attribute id=\"Name\" value=\"HUM_F_CLT_Test\"/><attribute id=\"MapKey\" value=\"root-1\"/><attribute id=\"Type\" value=\"item\"/><attribute id=\"Stats\" value=\"ARM_TestVanity\"/><attribute id=\"VisualTemplate\" value=\"vr-root\"/><children><node id=\"Equipment\"><children><node id=\"Visuals\"><children><node id=\"Object\"><attribute id=\"MapKey\" value=\"body-a\"/><children><node id=\"MapValue\"><attribute id=\"Object\" value=\"vr-a\"/></node><node id=\"MapValue\"><attribute id=\"Object\" value=\"vr-b\"/></node></children></node></children></node></children></node></children></node>
</children></node></region></save>"""

VISUALS_XML = """<save><region id=\"VisualResources\"><node id=\"VisualResources\"><children>
<node id=\"Resource\"><attribute id=\"ID\" value=\"vr-root\"/><attribute id=\"SourceFile\" value=\"root.GR2\"/></node>
<node id=\"Resource\"><attribute id=\"ID\" value=\"vr-a\"/><attribute id=\"SourceFile\" value=\"a.GR2\"/></node>
<node id=\"Resource\"><attribute id=\"ID\" value=\"vr-b\"/><attribute id=\"SourceFile\" value=\"b.GR2\"/></node>
</children></node></region></save>"""

STATS = '''new entry "ARM_TestVanity"\ntype "Armor"\nusing "_Vanity_Body_Generic_Common"\n\nnew entry "ARM_TestUnderwear"\ntype "Armor"\nusing "ARM_TestVanity"\ndata "Slot" "Underwear"\ndata "RootTemplate" "root-1"\n\nnew entry "_Vanity_Body_Generic_Common"\ntype "Armor"\ndata "Slot" "VanityBody"\n'''


def test_scanner_splits_root_and_named_stats_creation_paths_and_all_visuals(tmp_path: Path):
    root = tmp_path / "root.lsx"
    visuals = tmp_path / "visuals.lsx"
    stats = tmp_path / "Armor.txt"
    root.write_text(ROOT_XML, encoding="utf-8")
    visuals.write_text(VISUALS_XML, encoding="utf-8")
    stats.write_text(STATS, encoding="utf-8")
    module = SourceModule("Test", "mod-1", "Test", root, [stats], visuals)

    records, rejections = scan_source(module)

    assert rejections == []
    assert {(r.stats_entry, r.effective_slot, r.source_visual_resource_uuid) for r in records} == {
        ("ARM_TestVanity", "VanityBody", "vr-root"),
        ("ARM_TestVanity", "VanityBody", "vr-a"),
        ("ARM_TestVanity", "VanityBody", "vr-b"),
        ("ARM_TestUnderwear", "Underwear", "vr-root"),
        ("ARM_TestUnderwear", "Underwear", "vr-a"),
        ("ARM_TestUnderwear", "Underwear", "vr-b"),
    }


def test_scanner_reports_visual_resource_join_failures(tmp_path: Path):
    root = tmp_path / "root.lsx"
    visuals = tmp_path / "visuals.lsx"
    stats = tmp_path / "Armor.txt"
    root.write_text(ROOT_XML.replace("vr-b", "missing-vr"), encoding="utf-8")
    visuals.write_text(VISUALS_XML, encoding="utf-8")
    stats.write_text(STATS, encoding="utf-8")
    module = SourceModule("Test", "mod-1", "Test", root, [stats], visuals)

    records, rejections = scan_source(module)

    assert len(records) == 6
    assert {r.source_visual_resource_uuid for r in records} == {"vr-root", "vr-a", "missing-vr"}
    assert {item["reason"] for item in rejections} == {"visual_resource_unresolved"}
