from workstreams.release_master_ledger.identity import (
    build_identity,
    canonical_json,
    sha256_text,
)
from workstreams.release_master_ledger.models import (
    CanonicalIdentityFields,
    LedgerRecord,
    Observation,
)


def identity_fixture(**overrides):
    values = {
        "source_module_uuid": "11111111-1111-1111-1111-111111111111",
        "source_profile_digest": "A" * 64,
        "creation_path_kind": "root_template",
        "root_template_uuid": "22222222-2222-2222-2222-222222222222",
        "stats_entry": "ARM_Test",
        "inheritance_digest": "B" * 64,
        "effective_slot": "Underwear",
        "body_tuple": ("Human", "Female", "BT1", "Regular", "HUM_F"),
        "ordered_source_vrs": ("vr-a", "vr-b"),
        "component_contract_digest": "C" * 64,
    }
    values.update(overrides)
    return CanonicalIdentityFields(**values)


def test_identity_is_order_stable_and_binds_every_spec_field():
    fields = identity_fixture(
        ordered_source_vrs=("33333333-3333-3333-3333-333333333333",),
    )

    canonical, digest = build_identity(fields)

    assert canonical == canonical_json(fields.to_dict())
    assert len(digest) == 64
    assert digest == sha256_text(canonical)


def test_identity_changes_when_ordered_source_vrs_change_order():
    first = identity_fixture(ordered_source_vrs=("vr-a", "vr-b"))
    second = identity_fixture(ordered_source_vrs=("vr-b", "vr-a"))

    assert build_identity(first)[1] != build_identity(second)[1]


def test_identity_fields_emit_ordered_sequences_as_json_arrays():
    fields = identity_fixture()

    assert fields.to_dict()["body_tuple"] == ["Human", "Female", "BT1", "Regular", "HUM_F"]
    assert fields.to_dict()["ordered_source_vrs"] == ["vr-a", "vr-b"]


def test_observation_and_ledger_record_emit_deterministic_section_9_2_fields():
    fields = identity_fixture()
    canonical_identity, identity_sha256 = build_identity(fields)
    observation = Observation(
        observation_id="obs-1",
        observation_kind="SYNTHETIC",
        identity_fields=fields,
        source_reference="fixture.json",
        payload={"zeta": {"beta": 2, "alpha": 1}, "alpha": ["a"]},
    )
    record = LedgerRecord(
        record_id="SYNTHETIC_RECORD_001",
        canonical_identity=canonical_identity,
        identity_sha256=identity_sha256,
        source_module={"uuid": fields.source_module_uuid, "zeta": 1, "alpha": 2},
        permission={"state": "PERMISSION_UNASSESSED"},
        creation_path={"kind": "root_template"},
        classification={"effective_slot": "Underwear"},
        body_tuple={"race": "Human"},
        source_route={"ordered_vrs": ["vr-a", "vr-b"]},
        mode_routes={"vanilla": {"zeta": 1, "alpha": 2}},
        protected_relations={"registry_ids": ["SYNTHETIC"]},
        transformation={"strategy": "UNASSESSED"},
        gates={"gameplay": "UNASSESSED"},
        evidence_paths=("fixture.json",),
        evidence_hashes=("D" * 64,),
        disposition="DEFERRED_WITH_CAUSE",
        blocker_codes=("SYNTHETIC_BLOCKER",),
        release_blocking=True,
        next_admissible_action="Obtain a bounded synthetic result.",
        acceptance_event_id="UNKNOWN_ACCEPTANCE_EVENT",
        shipped_package_id="UNKNOWN_SHIPPED_PACKAGE",
    )

    assert list(observation.to_dict()["payload"]) == ["alpha", "zeta"]
    assert list(observation.to_dict()["payload"]["zeta"]) == ["alpha", "beta"]
    assert list(record.to_dict()["mode_routes"]["vanilla"]) == ["alpha", "zeta"]
    assert list(record.to_dict()) == [
        "record_id",
        "canonical_identity",
        "identity_sha256",
        "source_module",
        "permission",
        "creation_path",
        "classification",
        "body_tuple",
        "source_route",
        "mode_routes",
        "protected_relations",
        "transformation",
        "gates",
        "evidence_paths",
        "evidence_hashes",
        "disposition",
        "blocker_codes",
        "release_blocking",
        "next_admissible_action",
        "acceptance_event_id",
        "shipped_package_id",
    ]
