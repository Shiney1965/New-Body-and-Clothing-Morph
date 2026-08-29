from workstreams.coverage_ledger.generate_test_cards import bounded_cards
from workstreams.coverage_ledger.models import GarmentRecord


def _record(number: int, disposition: str = "READY FOR TEST") -> GarmentRecord:
    return GarmentRecord(
        identity=f"fixture-id-{number}", source_module={"name": "FixtureModule", "uuid": "fixture-module", "folder": "FixtureFolder"},
        root_template_uuid=f"root-{number}", stats_entry="stats", effective_slot="VanityBody",
        inheritance_chain=["stats"], source_visual_resource_uuid=f"vr-{number}",
        source_visual_resource_path="source.GR2", body_family="HUM_F", garment_family="Test",
        topology_family="UNASSESSED", disposition=disposition,
    )


def test_every_ready_record_is_in_exactly_one_bounded_card():
    cards = bounded_cards([*(_record(number) for number in range(13)), _record(99, "ACCEPTED / PROTECT")], maximum_records=12)
    card_ids = [identity for card in cards for identity in card["record_identities"]]
    assert len(cards) == 2
    assert set(card_ids) == {f"fixture-id-{number}" for number in range(13)}
    assert len(card_ids) == len(set(card_ids))
    assert all(len(card["record_identities"]) <= 12 for card in cards)
