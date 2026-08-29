from collections import Counter

from workstreams.coverage_ledger.build_ledger import build_master_ledger
from workstreams.coverage_ledger.models import GarmentRecord


def _record(identity: str, slot: str) -> GarmentRecord:
    return GarmentRecord(
        identity=identity, source_module={"name": "FixtureModule", "uuid": "fixture-module", "folder": "FixtureFolder"},
        root_template_uuid=identity, stats_entry="stats", effective_slot=slot,
        inheritance_chain=["stats"], source_visual_resource_uuid="vr",
        source_visual_resource_path="path", body_family="HUM_F", garment_family="Test",
        topology_family="UNASSESSED",
    )


def test_every_raw_identity_has_exactly_one_master_record():
    raw = [_record("vanity", "VanityBody"), _record("armor", "Breast")]
    master = build_master_ledger(raw, [])
    assert Counter(record.identity for record in master) == Counter({"vanity": 1, "armor": 1})


def test_no_unclassified_dispositions():
    master = build_master_ledger([_record("underwear", "Underwear")], [])
    assert all(record.disposition != "UNCLASSIFIED" for record in master)
    assert master[0].disposition == "DEFERRED WITH CAUSE"


def test_unresolved_slot_is_deferred_with_cause_not_excluded():
    master = build_master_ledger([_record("unknown", "UNRESOLVED")], [])
    assert master[0].disposition == "DEFERRED WITH CAUSE"


def test_unresolved_visual_resource_path_is_deferred_not_queued():
    record = _record("unknown-visual", "VanityBody")
    record.source_visual_resource_path = None
    master = build_master_ledger([record], [])
    assert master[0].disposition == "DEFERRED WITH CAUSE"


def test_non_target_equipment_slot_is_out_of_scope_even_without_readiness_contract():
    master = build_master_ledger([_record("boots", "VanityBoots")], [])
    assert master[0].disposition == "OUT OF SCOPE"
