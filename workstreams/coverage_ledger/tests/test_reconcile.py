from workstreams.coverage_ledger.models import GarmentRecord
from workstreams.coverage_ledger.reconcile import Evidence, reconcile


def test_gameplay_pass_supersedes_stale_ready_card():
    garment = GarmentRecord(
        identity="mod|root|stats|VanityBody|vr|HUM_F",
        source_module={"name": "FixtureModule", "uuid": "fixture-module", "folder": "FixtureFolder"},
        root_template_uuid="root",
        stats_entry="stats",
        effective_slot="VanityBody",
        inheritance_chain=["stats"],
        source_visual_resource_uuid="vr",
        source_visual_resource_path="path",
        body_family="HUM_F",
        garment_family="Test",
        topology_family="UNASSESSED",
    )
    stale = Evidence("old-card.md", "READY_FOR_TEST", "2026-08-01", {"root"}, garment.identity)
    later = Evidence("later-pass.md", "GAMEPLAY_PASS", "2026-08-02", {"root"}, garment.identity)

    result = reconcile([garment], [stale, later])

    assert result.records[0].disposition == "ACCEPTED / PROTECT"
    assert result.records[0].reconciliation["controlling_evidence"] == "later-pass.md"


def test_conflicting_same_strength_evidence_is_emitted_not_silently_chosen():
    garment = GarmentRecord(
        identity="mod|root|stats|VanityBody|vr|HUM_F",
        source_module={"name": "FixtureModule", "uuid": "fixture-module", "folder": "FixtureFolder"},
        root_template_uuid="root", stats_entry="stats", effective_slot="VanityBody",
        inheritance_chain=["stats"], source_visual_resource_uuid="vr",
        source_visual_resource_path="path", body_family="HUM_F", garment_family="Test",
        topology_family="UNASSESSED",
    )
    result = reconcile([garment], [
        Evidence("defect-a.md", "CONFIRMED_DEFECT", "2026-08-03", {"root"}, garment.identity),
        Evidence("defect-b.md", "GAMEPLAY_PASS", "2026-08-03", {"root"}, garment.identity),
    ])

    assert len(result.conflicts) == 1
    assert result.records[0].disposition == "DEFERRED WITH CAUSE"
