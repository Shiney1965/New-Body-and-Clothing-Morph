from workstreams.release_master_ledger.models import CanonicalIdentityFields, Observation
from workstreams.release_master_ledger.reconcile import reconcile_observations


def identity(**overrides):
    values = {
        "source_module_uuid": "11111111-1111-1111-1111-111111111111",
        "source_profile_digest": "A" * 64,
        "creation_path_kind": "root_template",
        "root_template_uuid": "22222222-2222-2222-2222-222222222222",
        "stats_entry": "ARM_Test",
        "inheritance_digest": "B" * 64,
        "effective_slot": "Underwear",
        "body_tuple": ("Human", "Female", "BT1", "Regular", "HUM_F"),
        "ordered_source_vrs": ("vr-a",),
        "component_contract_digest": "C" * 64,
    }
    values.update(overrides)
    return CanonicalIdentityFields(**values)


def observation(observation_id, *, fields=None, authority="WORKSTREAM_EVIDENCE", payload=None, **payload_values):
    return Observation(
        observation_id=observation_id,
        observation_kind="SYNTHETIC",
        identity_fields=fields or identity(),
        source_reference=f"{observation_id}.json",
        evidence_files=(f"{observation_id}.json",),
        payload={"authority": authority, **(payload or {}), **payload_values},
    )


def test_same_canonical_identity_joins_observations_once():
    coverage = observation("coverage", source_route={"source": "coverage"})
    underwear = observation("underwear", source_route={"source": "underwear"})

    result = reconcile_observations([coverage, underwear])

    assert len(result.records) == 1
    assert result.records[0].evidence_paths == ("coverage.json", "underwear.json")
    assert result.observation_to_record == {
        "coverage": result.records[0].record_id,
        "underwear": result.records[0].record_id,
    }


def test_protected_fields_cannot_be_overwritten_by_nonprotected_evidence():
    protected = observation(
        "protected",
        authority="IMMUTABLE_V1",
        mode_routes={"bcb": {"target_paths": ["protected.gr2"]}},
        payload_hash="A" * 64,
    )
    proposed = observation(
        "proposed",
        mode_routes={"bcb": {"target_paths": ["replacement.gr2"]}},
        payload_hash="B" * 64,
    )

    result = reconcile_observations([proposed, protected])

    assert result.records[0].mode_routes["bcb"]["target_paths"] == ["protected.gr2"]
    assert result.records[0].transformation["payload_hash"] == "A" * 64
    assert "PROTECTED_ROUTE_CONFLICT" in result.records[0].blocker_codes
    assert result.conflicts == ("PROTECTED_ROUTE_CONFLICT",)
    assert result.records[0].evidence_paths == ("protected.json", "proposed.json")


def test_incomplete_identity_never_merges_on_display_name():
    first = observation(
        "first",
        fields=identity(root_template_uuid="root-a"),
        display_name="Same Name",
    )
    second = observation(
        "second",
        fields=identity(root_template_uuid="root-b"),
        display_name="Same Name",
    )

    result = reconcile_observations([first, second])

    assert len(result.records) == 2
    assert [record.record_id for record in result.records] == sorted(record.record_id for record in result.records)


def test_conflicting_nonprotected_route_is_retained_as_a_blocker():
    first = observation("first", mode_routes={"bcb": {"target_paths": ["first.gr2"]}})
    second = observation("second", mode_routes={"bcb": {"target_paths": ["second.gr2"]}})

    result = reconcile_observations([first, second])

    assert "ROUTE_CONFLICT" in result.records[0].blocker_codes
    assert result.records[0].mode_routes["bcb"]["target_paths"] == ["first.gr2"]
    assert result.records[0].evidence_paths == ("first.json", "second.json")
