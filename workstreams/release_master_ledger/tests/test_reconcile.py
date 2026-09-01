from workstreams.release_master_ledger.models import CanonicalIdentityFields, Observation
from workstreams.release_master_ledger.reconcile import reconcile_observations
from workstreams.release_master_ledger.validation import validate_record
import pytest


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
    assert "PROTECTED_PAYLOAD_HASH_CONFLICT" in result.records[0].blocker_codes
    assert result.conflicts == ("PROTECTED_PAYLOAD_HASH_CONFLICT", "PROTECTED_ROUTE_CONFLICT")
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


def test_unresolved_placeholder_identity_is_provisional_per_observation_without_display_name_join():
    unresolved = identity(
        source_module_uuid="UNKNOWN_SOURCE_MODULE_UUID",
        root_template_uuid="UNKNOWN_ROOT_TEMPLATE_UUID",
        effective_slot="AMBIGUOUS_SLOT",
    )
    first = observation("first-unresolved", fields=unresolved, display_name="Same Name")
    second = observation("second-unresolved", fields=unresolved, display_name="Different Name")

    result = reconcile_observations([first, second])

    assert len(result.records) == 2
    assert all("IDENTITY_FIELDS_UNRESOLVED" in record.blocker_codes for record in result.records)
    assert result.observation_to_record["first-unresolved"] != result.observation_to_record["second-unresolved"]


def test_duplicate_observation_id_is_rejected_before_reconciliation():
    duplicate_id = "duplicate-observation"

    with pytest.raises(ValueError, match="^DUPLICATE_OBSERVATION_ID:duplicate-observation$"):
        reconcile_observations([
            observation(duplicate_id),
            observation(duplicate_id, fields=identity(root_template_uuid="different-root")),
        ])


@pytest.mark.parametrize(
    ("field_name", "placeholder"),
    [
        ("source_profile_digest", "AMBIGUOUS_SOURCE_PROFILE_DIGEST"),
        ("inheritance_digest", "UNKNOWN_INHERITANCE_DIGEST"),
        ("component_contract_digest", "AMBIGUOUS_COMPONENT_CONTRACT_DIGEST"),
    ],
)
def test_unresolved_hash_identity_field_becomes_distinct_valid_provisional_records(field_name, placeholder):
    fields = identity(**{field_name: placeholder})

    result = reconcile_observations([
        observation(f"{field_name}-first", fields=fields, display_name="First"),
        observation(f"{field_name}-second", fields=fields, display_name="Second"),
    ])

    assert len(result.records) == 2
    assert all(record.release_blocking is True for record in result.records)
    assert all("IDENTITY_FIELDS_UNRESOLVED" in record.blocker_codes for record in result.records)
    assert all(validate_record(record.to_dict()) == [] for record in result.records)
