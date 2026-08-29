from pathlib import Path

from true_underwear.inventory import ClassificationResult, SourceInput, SourceRoots, build_all_creation_paths, build_inventory, classify_creation_paths


FIXTURES = Path(__file__).parent / "fixtures"


def make_sources(tmp_path):
    return SourceRoots(
        shared_stats=(FIXTURES / "inventory_shared_armor.txt",),
        sources=(
            SourceInput(
                source="FIXTURE_SOURCE",
                module_folder="FixtureModule",
                module_name="Fixture Module",
                module_uuid="11111111-1111-1111-1111-111111111111",
                version64="1",
                stats=(FIXTURES / "inventory_source_armor.txt",),
                roots=(FIXTURES / "root_templates.lsx",),
            ),
        ),
        rejections_path=tmp_path / "rejections.json",
    )


def test_inventory_contains_only_effective_underwear_slots(tmp_path):
    records = build_inventory(make_sources(tmp_path))

    assert records
    assert {record.effective_slot for record in records} == {"Underwear"}
    assert [record.stats_entry for record in records] == ["FixtureGarmentUnderwear"]


def test_stats_template_without_root_template_is_not_a_concrete_wearable(tmp_path):
    records = build_inventory(make_sources(tmp_path))

    assert "FixtureTemplateOnly" not in [record.stats_entry for record in records]


def test_root_and_named_stats_mismatch_are_separate_records(tmp_path):
    all_paths = build_all_creation_paths(make_sources(tmp_path))
    garment = [record for record in all_paths if record.display_name == "Fixture Vanity Garment"]

    assert {record.effective_slot for record in garment} == {"Underwear", "VanityBody"}
    assert {record.creation_path for record in garment} == {"named_stats", "root_template"}


def test_unresolved_inheritance_is_returned_not_silently_excluded(tmp_path):
    sources = make_sources(tmp_path)

    result = classify_creation_paths(sources)

    assert isinstance(result, ClassificationResult)
    rejection_text = str(result.rejections)
    assert "FixtureUnresolvedGarment" in rejection_text
    assert "FixtureMissingParent" in rejection_text
    assert not sources.rejections_path.exists()


def test_character_root_with_underwear_slot_is_rejected_not_emitted(tmp_path):
    sources = make_sources(tmp_path)

    result = classify_creation_paths(sources)

    assert "FixtureCharacterUnderwear" not in [record.stats_entry for record in result.records]
    assert "NOT_A_WEARABLE" in str(result.rejections)
    assert not sources.rejections_path.exists()


def test_compatibility_wrapper_does_not_write_caller_selected_rejections_path(tmp_path):
    sources = make_sources(tmp_path)

    records = build_all_creation_paths(sources)

    assert records
    assert not sources.rejections_path.exists()
