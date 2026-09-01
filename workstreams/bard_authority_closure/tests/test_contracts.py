import hashlib
import json
from pathlib import Path

import pytest

from workstreams.bard_authority_closure import configuration
from workstreams.bard_authority_closure.configuration import (
    ConfigurationError,
    EvidenceInput,
    EvidenceIntegrityError,
    LocalConfiguration,
    load_local_configuration,
    verify_evidence_inputs,
)
from workstreams.bard_authority_closure.contracts import (
    ContractViolation,
    load_authority_contract,
    load_bard_contract,
)


def _configuration_for(evidence: Path, expected_sha256: str) -> LocalConfiguration:
    return LocalConfiguration(
        inputs=(
            EvidenceInput(
                input_id="synthetic_contract_evidence",
                kind="SYNTHETIC",
                path=evidence,
                expected_sha256=expected_sha256,
            ),
        ),
    )


def test_hash_locked_configuration_accepts_only_matching_synthetic_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    workstream_root = tmp_path / "bard_authority_closure"
    evidence = workstream_root / "local" / "current-evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"current":"evidence"}', encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest().upper()
    (evidence.parent / "config.json").write_text(json.dumps({
        "inputs": [{
            "input_id": "synthetic_contract_evidence",
            "kind": "SYNTHETIC",
            "path": "current-evidence.json",
            "expected_sha256": digest,
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "WORKSTREAM_ROOT", workstream_root)

    configured = load_local_configuration()
    verified = verify_evidence_inputs(configured)

    assert configured.inputs[0].path == evidence
    assert verified[0].actual_sha256 == digest
    assert verified[0].bytes == len(b'{"current":"evidence"}')


def test_hash_mismatch_fails_before_contract_evidence_can_be_read(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("tampered", encoding="utf-8")

    with pytest.raises(EvidenceIntegrityError, match="EVIDENCE_HASH_MISMATCH"):
        verify_evidence_inputs(_configuration_for(evidence, "0" * 64))


def test_canonical_local_config_fails_closed_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(configuration, "WORKSTREAM_ROOT", tmp_path / "bard_authority_closure")

    with pytest.raises(ConfigurationError, match="CANONICAL_LOCAL_CONFIG_MISSING"):
        load_local_configuration()


def test_bard_contract_keeps_exact_two_component_82_bone_bcb_protected_identity():
    bard = load_bard_contract()

    assert bard.item_uuid == "42092137-4e81-4598-bb18-34939fbb8719"
    assert tuple(component.name for component in bard.components) == ("base", "thong")
    assert bard.components[0].sha256 == "AF11F500DF0CC18F255CDE6D7A96B50961DBEF4C9859B0B44022B0EF108797F7"
    assert bard.components[1].sha256 == "F3CB8A47CF887B28C29F0689A4EAB4152710D5D303E44C73B58271E345BD814D"
    assert all(component.bone_count == 82 for component in bard.components)
    assert bard.protected_bcb.replacement_routes == 0
    assert bard.protected_bcb.component_hashes == (
        "AF11F500DF0CC18F255CDE6D7A96B50961DBEF4C9859B0B44022B0EF108797F7",
        "F3CB8A47CF887B28C29F0689A4EAB4152710D5D303E44C73B58271E345BD814D",
    )


def test_bard_requires_an_atomic_non_bcb_base_and_thong_pair_before_any_emission():
    bard = load_bard_contract()

    with pytest.raises(ContractViolation, match="BARD_INCOMPLETE_COMPONENT_PAIR"):
        bard.require_emittable_pair("sbbf", ("base",))
    with pytest.raises(ContractViolation, match="BARD_BCB_PROTECTED_NO_REPLACEMENT"):
        bard.require_emittable_pair("bcb", ("base", "thong"))

    assert bard.require_emittable_pair("vanilla", ("base", "thong")) == ("base", "thong")


def test_bard_current_vanilla_and_sbbf_failure_evidence_remains_explicit():
    bard = load_bard_contract()

    assert bard.failure("vanilla", "BodyTop").below_area_floor == 4
    assert bard.failure("vanilla", "Sleeves").flips == 179
    assert bard.failure("vanilla", "Thong").minimum_area_ratio == 0.05640343759001028
    assert bard.failure("sbbf", "Sleeves").below_area_floor == 1
    assert bard.failure("sbbf", "Sleeves").minimum_area_ratio == 0.159049789992582
    assert bard.failure("sbbf", "Thong").minimum_area_ratio == 0.5175596977399949


def test_authority_requires_the_bcb_nine_object_main_without_a_netherstone_substitute():
    authority = load_authority_contract()

    assert authority.main_component.object_count == 9
    assert authority.main_component.sha256 == "03E2EED348D29649E3E222E613592ACD497D49C8EE3B226E84B2072BAF1BC07B"
    assert not any("Netherstone" in object_id for object_id in authority.main_component.object_ids)
    with pytest.raises(ContractViolation, match="AUTHORITY_NETHERSTONE_SUBSTITUTE_FORBIDDEN"):
        authority.require_main_candidate(
            authority.main_component.object_ids + ("TIF_FS_ARM_Authority_Robe.TIF_FS_ARM_Authority_Netherstone.8",)
        )


def test_authority_preserves_the_optional_skirt_distinction_by_item_identity():
    authority = load_authority_contract()

    assert authority.route_for_item("56d78c52-e349-4386-81c0-d8ee8bc8f10e").skirt is None
    skirt_route = authority.route_for_item("3f869845-badc-4035-ad51-e4ed25f43068")
    assert skirt_route.main == authority.main_component
    assert skirt_route.skirt is not None
    assert skirt_route.skirt.object_count == 1
    assert authority.route_for_item("b8c94f92-e857-4725-a59a-5db58bb9a8e6").skirt == skirt_route.skirt


def test_authority_fails_closed_for_every_current_unresolved_geometry_id():
    authority = load_authority_contract()
    expected = {
        "a913de25-257e-4e42-a677-c663effbe25a",
        "f1f789d3-c09e-485b-8f84-173e41fe9f96",
        "9bebc3db-3e3a-4faf-85fe-f19f589c247d",
        "94e2bcb1-8c38-4687-9833-c761536f0b0a",
    }

    assert set(authority.unresolved_geometry_ids) == expected
    for geometry_id in expected:
        with pytest.raises(ContractViolation, match=f"AUTHORITY_UNRESOLVED_GEOMETRY:{geometry_id}"):
            authority.require_geometry_admitted((geometry_id,))
    assert authority.require_geometry_admitted((authority.main_component.visual_resource_uuid,)) == (
        authority.main_component.visual_resource_uuid,
    )
