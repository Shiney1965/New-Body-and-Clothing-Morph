import hashlib
import json
from pathlib import Path

import pytest

from workstreams.release_master_ledger.adapters import (
    adapt_one_protected,
    adapt_protected_manifest,
    adapt_protected_registry,
    read_observations,
)
from workstreams.release_master_ledger.configuration import VerifiedInput


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def verified_fixture(name, kind):
    path = FIXTURES / name
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(
        input_id=f"fixture-{kind.lower()}",
        kind=kind,
        path=path,
        bytes=len(content),
        expected_sha256=digest,
        actual_sha256=digest,
    )


VERIFIED_REGISTRY = verified_fixture("protected_registry.json", "PROTECTED_REGISTRY")


def protected_fixture(**overrides):
    fixture = load_fixture("protected_registry.json")[0]
    fixture.update(overrides)
    return fixture


def test_protected_adapter_preserves_status_and_route_fingerprint():
    observations = adapt_protected_registry(load_fixture("protected_registry.json"), VERIFIED_REGISTRY)
    protected = observations[0]

    assert protected.authority == "IMMUTABLE_V1"
    assert protected.protected_relations["registry_ids"] == ["fixture-protected-1"]
    assert protected.protected_relations["route_fingerprint"] == "D" * 64
    assert protected.disposition == "ACCEPTED_PROTECTED"
    assert protected.raw_evidence == load_fixture("protected_registry.json")[0]


def test_package_only_protection_does_not_become_gameplay_acceptance():
    observation = protected_fixture(status="PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY")

    normalized = adapt_one_protected(observation, VERIFIED_REGISTRY)

    assert normalized.disposition == "PACKAGE_ONLY_PROTECTED"
    assert normalized.release_blocking is True
    assert normalized.evidence_status == "GAMEPLAY_UNASSESSED_PACKAGE_ONLY"


def test_protected_status_mapping_preserves_native_and_residual_categories():
    native = adapt_one_protected(
        protected_fixture(status="PROTECTED_SOURCE_NATIVE"), VERIFIED_REGISTRY
    )
    residual = adapt_one_protected(
        protected_fixture(status="USER_ACCEPTED_RESIDUAL"), VERIFIED_REGISTRY
    )

    assert native.disposition == "SOURCE_NATIVE_PROTECTED"
    assert native.release_blocking is False
    assert residual.disposition == "ACCEPTED_PROTECTED"
    assert residual.release_blocking is False


def test_protected_manifest_and_verified_reader_keep_input_fingerprint():
    verified = verified_fixture("protected_manifest.json", "PROTECTED_MANIFEST")
    manifest_observation = adapt_protected_manifest(load_fixture("protected_manifest.json"), verified)[0]
    read_observation = read_observations(verified)[0]

    assert manifest_observation.input_id == verified.input_id
    assert manifest_observation.input_sha256 == verified.actual_sha256
    assert read_observation.disposition == "SOURCE_NATIVE_PROTECTED"


def test_protected_records_without_explicit_ids_remain_distinct():
    first = protected_fixture(observation_id="")
    second = protected_fixture(observation_id="", registry_ids=["fixture-protected-2"])

    observations = adapt_protected_registry([first, second], VERIFIED_REGISTRY)

    assert [observation.observation_id for observation in observations] == [
        "fixture-protected_registry:0", "fixture-protected_registry:1"
    ]


def test_reader_rejects_bytes_mutated_after_verification(tmp_path):
    path = tmp_path / "protected.json"
    original = json.dumps(load_fixture("protected_registry.json"))
    path.write_text(original, encoding="utf-8")
    original_bytes = path.read_bytes()
    digest = hashlib.sha256(original_bytes).hexdigest().upper()
    verified = VerifiedInput(
        input_id="mutation-guard", kind="PROTECTED_REGISTRY", path=path,
        bytes=len(original_bytes), expected_sha256=digest, actual_sha256=digest,
    )
    path.write_text(json.dumps([protected_fixture(status="PROTECTED_SOURCE_NATIVE")]), encoding="utf-8")

    with pytest.raises(ValueError, match="EVIDENCE_INPUT_HASH_MISMATCH:mutation-guard"):
        read_observations(verified)


def test_reader_rejects_forged_matching_declared_hashes(tmp_path):
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(load_fixture("protected_registry.json")), encoding="utf-8")
    forged = VerifiedInput(
        input_id="forged-input", kind="PROTECTED_REGISTRY", path=path,
        bytes=path.stat().st_size, expected_sha256="A" * 64, actual_sha256="A" * 64,
    )

    with pytest.raises(ValueError, match="EVIDENCE_INPUT_HASH_MISMATCH:forged-input"):
        read_observations(forged)


def test_malformed_list_member_fails_closed_with_its_index():
    with pytest.raises(ValueError, match="EVIDENCE_RECORD_INVALID:1"):
        adapt_protected_registry([protected_fixture(), "not a record"], VERIFIED_REGISTRY)


def test_records_wrapper_requires_a_list():
    with pytest.raises(ValueError, match="EVIDENCE_RECORDS_NOT_LIST"):
        adapt_protected_registry({"records": {"not": "a list"}}, VERIFIED_REGISTRY)
