import json
from pathlib import Path
import pytest

from workstreams.coverage_ledger.build_ledger import build_master_ledger, generate_class_queues
from workstreams.coverage_ledger import configuration, generate_test_cards
from workstreams.coverage_ledger.configuration import LocalConfigurationUnavailable
from workstreams.coverage_ledger.generate_test_cards import bounded_cards, publish_cards
from workstreams.coverage_ledger.models import GarmentRecord, RouteRecord
from workstreams.coverage_ledger.reconcile import Evidence, reconcile


def _local_configuration():
    from workstreams.coverage_ledger.configuration import LocalConfigurationUnavailable, load_local_configuration
    try:
        return load_local_configuration()
    except LocalConfigurationUnavailable as error:
        pytest.skip(str(error))


def _record() -> GarmentRecord:
    return GarmentRecord(
        identity="fixture-module|fixture-root|fixture-stats|VanityBody|fixture-vr|HUM_F",
        source_module={"name": "FixtureModule", "uuid": "fixture-module", "folder": "FixtureFolder"},
        root_template_uuid="root", stats_entry="stats", effective_slot="VanityBody",
        inheritance_chain=["stats"], source_visual_resource_uuid="vr",
        source_visual_resource_path="Generated/Public/Fixture/Assets/source.GR2", body_family="HUM_F",
        garment_family="Test", topology_family="UNASSESSED",
        routes={"source_native": RouteRecord("source_native", "vr", "source.GR2", "source")},
    )


def _complete_record(identity: str = "fixture-module|fixture-root|fixture-stats|VanityBody|fixture-vr|HUM_F") -> GarmentRecord:
    record = _record()
    record.identity = identity
    record.topology_family = "TOPOLOGY-A"
    record.component_contract = "COMPONENT-CONTRACT-A"
    record.known_defect = "NONE; bounded static preflight"
    record.protected_controls = ["control.md"]
    record.package_ownership = {"pak": "candidate.pak"}
    record.candidate_profile = {"profile_id": "fixture-profile-a", "dependencies": [{"folder": "FixtureFolder", "name": "FixtureModule", "uuid": "fixture-module", "version64": "1"}]}
    record.readiness_evidence = ["manifest.json"]
    record.routes = {
        "source_native": RouteRecord("source_native", "vr", "source.GR2", "source", "a" * 64),
        "Vanilla": RouteRecord("Vanilla", "van", "van.GR2", "fresh extraction", "b" * 64),
        "SBBF": RouteRecord("SBBF", "sbbf", "sbbf.GR2", "fresh extraction", "c" * 64),
        "BCB": RouteRecord("BCB", "bcb", "bcb.GR2", "fresh extraction", "d" * 64),
    }
    return record


def test_resolved_source_slot_without_complete_target_contract_is_deferred():
    record = build_master_ledger([_record()], [])[0]
    assert record.disposition == "DEFERRED WITH CAUSE"
    assert "target" in record.next_action.lower()


def test_root_only_evidence_can_annotate_but_cannot_control_a_concrete_route():
    record = _record()
    evidence = Evidence("legacy-card.md", "READY_FOR_TEST", "2026-08-27", {"root"})
    result = reconcile([record], [evidence])
    assert result.records[0].disposition == "DEFERRED WITH CAUSE"
    assert result.records[0].reconciliation["root_annotations"] == ["legacy-card.md"]


def test_schema_requires_full_route_and_readiness_contract():
    schema = json.loads((Path(__file__).resolve().parents[1] / "schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {"inheritance_chain", "source_visual_resource_path", "routes", "garment_family", "topology_family", "protected_controls", "package_ownership", "candidate_profile", "readiness_evidence", "next_action"} <= required
    assert "garment_family" in schema["properties"]
    assert {"source_native", "Vanilla", "SBBF", "BCB"} <= set(schema["properties"]["routes"]["required"])
    assert {"mode", "visual_resource_uuid", "path", "provenance", "mesh_sha256", "gameplay_result"} <= set(schema["$defs"]["route"]["required"])


@pytest.mark.integration
def test_delivery_directory_equals_current_card_index():
    configuration = _local_configuration()
    cards = json.loads((configuration.evidence_dir / "CLASS_TEST_CARDS.json").read_text(encoding="utf-8"))
    indexed = {f"{card['card_id']}.md" for card in cards}
    actual = {path.name for path in configuration.card_dir.glob("Q*.md")}
    assert actual == indexed


@pytest.mark.integration
def test_master_records_carry_explicit_target_route_slots_even_when_unresolved():
    configuration = _local_configuration()
    master = json.loads((configuration.evidence_dir / "SCO_SINDAE_MASTER_GARMENT_LEDGER.json").read_text(encoding="utf-8"))
    assert all({"source_native", "Vanilla", "SBBF", "BCB"} <= set(record["routes"]) for record in master)


@pytest.mark.integration
def test_rejected_routes_never_bypass_into_ready_or_correction_dispositions():
    evidence = _local_configuration().evidence_dir
    master = json.loads((evidence / "SCO_SINDAE_MASTER_GARMENT_LEDGER.json").read_text(encoding="utf-8"))
    rejections = json.loads((evidence / "SCAN_REJECTIONS.json").read_text(encoding="utf-8"))
    rejected = {(item["source_module_uuid"], item["root_template_uuid"], item["stats_entry"], item["visual_resource_uuid"]) for item in rejections}
    bypasses = [
        record for record in master
        if (record["source_module"]["uuid"], record["root_template_uuid"], record["stats_entry"], record["source_visual_resource_uuid"]) in rejected
        and record["disposition"] in {"READY FOR TEST", "CONFIRMED DEFECT / CORRECT"}
    ]
    assert bypasses == []


def test_exact_gameplay_pass_remains_accepted_and_never_enters_card_queue():
    record = _complete_record()
    accepted = build_master_ledger([record], [Evidence("pass.md", "GAMEPLAY_PASS", "2026-08-29", set(), record.identity)])[0]
    assert accepted.disposition == "ACCEPTED / PROTECT"
    assert bounded_cards([accepted]) == []


def test_cards_split_records_with_distinct_topology_or_profile_contracts():
    first = _complete_record("fixture-module|fixture-root1|fixture-stats|VanityBody|fixture-vr1|HUM_F")
    second = _complete_record("fixture-module|fixture-root2|fixture-stats|VanityBody|fixture-vr2|HUM_F")
    second.topology_family = "TOPOLOGY-B"
    second.candidate_profile = {"profile_id": "fixture-profile-b", "dependencies": [{"folder": "FixtureFolder", "name": "FixtureModule", "uuid": "fixture-module", "version64": "2"}]}
    first.disposition = "READY FOR TEST"
    second.disposition = "READY FOR TEST"
    cards = bounded_cards([first, second])
    assert len(cards) == 2


def test_queues_split_records_with_distinct_component_contracts():
    first = _complete_record("fixture-module|fixture-root1|fixture-stats|VanityBody|fixture-vr1|HUM_F")
    second = _complete_record("fixture-module|fixture-root2|fixture-stats|VanityBody|fixture-vr2|HUM_F")
    second.component_contract = "COMPONENT-CONTRACT-B"
    first.disposition = "READY FOR TEST"
    second.disposition = "READY FOR TEST"
    assert len(generate_class_queues([first, second])) == 2


def test_card_publication_replaces_obsolete_delivery_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_dir = tmp_path / "local"
    monkeypatch.setattr(configuration, "LOCAL_OUTPUT_ROOT", local_dir)
    card_dir = local_dir / "cards"
    stale = card_dir / "Q999.md"
    card_dir.mkdir(parents=True)
    stale.write_text("obsolete", encoding="utf-8")
    publish_cards([], {}, card_dir)
    assert list(card_dir.glob("Q*.md")) == []


def test_card_publication_rejects_outside_directory_without_touching_sentinel(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "Q999.md"
    sentinel.write_text("do-not-delete", encoding="utf-8")

    with pytest.raises(LocalConfigurationUnavailable, match="generated output.*local"):
        publish_cards([], {}, outside)

    assert sentinel.read_text(encoding="utf-8") == "do-not-delete"


def test_deserialized_ready_record_renders_all_route_columns():
    record = _complete_record()
    record.disposition = "READY FOR TEST"
    restored = generate_test_cards._records_from_json([record.to_dict()])
    card = bounded_cards(restored)[0]

    rendered = generate_test_cards._render(card, {item.identity: item for item in restored})

    for mode in ("source_native", "Vanilla", "SBBF", "BCB"):
        assert restored[0].routes[mode] == record.routes[mode]
    assert "van.GR2" in rendered
    assert "sbbf.GR2" in rendered
    assert "bcb.GR2" in rendered
