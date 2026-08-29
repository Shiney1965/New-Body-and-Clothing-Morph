from pathlib import Path

from true_underwear.slot_resolver import parse_stats, resolve_slot


FIXTURE_STATS = Path(__file__).parent / "fixtures" / "armor_stats.txt"


def test_resolves_underwear_through_using_chain():
    records = parse_stats(FIXTURE_STATS)

    result = resolve_slot("FixtureNamedUnderwear", records)

    assert result.slot == "Underwear"
    assert result.inheritance == (
        "FixtureNamedUnderwear",
        "FixtureSlotUnderwear",
        "FixtureSlotUnderwearBase",
    )
    assert result.cycle is False
    assert result.missing_parent is None


def test_vanity_root_does_not_inherit_named_underwear_slot():
    records = parse_stats(FIXTURE_STATS)

    result = resolve_slot("FixtureSlotVanity", records)

    assert result.slot == "VanityBody"
    assert result.inheritance == ("FixtureSlotVanity",)


def test_cycle_and_missing_parent_are_explicit_resolution_failures():
    records = parse_stats(FIXTURE_STATS)

    cycle = resolve_slot("FixtureCycleA", records)
    missing = resolve_slot("FixtureMissingEntry", records)

    assert cycle.slot is None
    assert cycle.cycle is True
    assert cycle.inheritance == ("FixtureCycleA", "FixtureCycleB", "FixtureCycleA")
    assert missing.slot is None
    assert missing.cycle is False
    assert missing.missing_parent == "FixtureNoSuchParent"
    assert missing.inheritance == ("FixtureMissingEntry", "FixtureNoSuchParent")
