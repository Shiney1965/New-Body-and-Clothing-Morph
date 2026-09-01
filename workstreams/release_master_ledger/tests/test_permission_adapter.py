import hashlib
import json
from pathlib import Path

from workstreams.release_master_ledger.adapters import adapt_permission_manifest
from workstreams.release_master_ledger.configuration import VerifiedInput


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def verified_fixture(name, kind):
    path = FIXTURES / name
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(
        input_id=f"fixture-{kind.lower()}", kind=kind, path=path, bytes=len(content),
        expected_sha256=digest, actual_sha256=digest,
    )


VERIFIED_PERMISSION = verified_fixture("permission_records.json", "PERMISSION")


def permission_fixture(**overrides):
    fixture = load_fixture("permission_records.json")
    fixture.update(overrides)
    return fixture


def test_permission_scope_mesh_is_an_observation_not_a_garment_assumption():
    observations = adapt_permission_manifest(
        permission_fixture(scope_resolved=["HUM_F_Test.GR2"]), VERIFIED_PERMISSION
    )

    assert observations[0].observation_kind == "PERMISSION_SCOPE_MESH"
    assert observations[0].classification["effective_slot"] == "AMBIGUOUS_SLOT"
    assert "ITEM_CONTRACT_UNRESOLVED" in observations[0].blocker_codes


def test_permission_mesh_name_is_retained_as_raw_evidence_not_a_route():
    manifest = permission_fixture(scope_resolved=["HUM_F_Test.GR2"])
    observation = adapt_permission_manifest(manifest, VERIFIED_PERMISSION)[0]

    assert observation.raw_evidence == manifest
    assert observation.classification["scope_mesh"] == "HUM_F_Test.GR2"
    assert observation.identity_fields.ordered_source_vrs == ("UNKNOWN_SOURCE_VR",)
    assert observation.disposition == "DEFERRED_WITH_CAUSE"


def test_permission_scope_fallback_ids_are_unique_across_manifests_and_scopes():
    manifests = [
        permission_fixture(observation_id="", scope_resolved=["first-a", "first-b"]),
        permission_fixture(observation_id="", scope_resolved=["second-a", "second-b"]),
    ]

    observations = adapt_permission_manifest(manifests, VERIFIED_PERMISSION)

    assert [observation.observation_id for observation in observations] == [
        "fixture-permission:0:0", "fixture-permission:0:1",
        "fixture-permission:1:0", "fixture-permission:1:1",
    ]
