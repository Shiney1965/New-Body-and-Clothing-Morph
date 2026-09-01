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


EXPECTED_BARD_COMPONENTS = (
    {
        "name": "base",
        "visual_resource_uuid": "c4e56439-38a8-4b9a-bec2-4c603f7473cc",
        "source_file": "Generated/Public/BCBScantily/Assets/HUM_F_CLT_Bard_Dress_Base_KEL.GR2",
        "sha256": "AF11F500DF0CC18F255CDE6D7A96B50961DBEF4C9859B0B44022B0EF108797F7",
        "object_ids": (
            "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Blazer_Alt.0",
            "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Boots.1",
            "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Legging.2",
            "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Sleeves.3",
        ),
        "bone_count": 82,
    },
    {
        "name": "thong",
        "visual_resource_uuid": "24657ffb-4b65-446e-9884-3098f2440a98",
        "source_file": "Generated/Public/BCBScantily/Assets/HUM_F_CLT_Bard_Dress_Thong_KEL.GR2",
        "sha256": "F3CB8A47CF887B28C29F0689A4EAB4152710D5D303E44C73B58271E345BD814D",
        "object_ids": ("TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Belt_Alt.0",),
        "bone_count": 82,
    },
)
EXPECTED_AUTHORITY_MAIN = {
    "name": "authority_main",
    "visual_resource_uuid": "aec60cfa-c6a1-4a77-8148-b2fa01e4d988",
    "source_file": "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe.GR2",
    "sha256": "03E2EED348D29649E3E222E613592ACD497D49C8EE3B226E84B2072BAF1BC07B",
    "object_ids": (
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Gloves.0",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Knee.1",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Robe.2",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Sash.3",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Shawl.4",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Sleeve.5",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Stiletto.6",
        "HUM_F_ARM_Authority_Robe.HUM_F_NKD_Breast.7",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Skirt.8",
    ),
    "bone_count": 82,
}
EXPECTED_AUTHORITY_SKIRT = {
    "name": "authority_skirt",
    "visual_resource_uuid": "122d5812-e27d-4638-905d-5e520cc26202",
    "source_file": "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe_Skirt_KEL.GR2",
    "sha256": "20B32325E017682E1C2EC17CD858F7EDA15DF596F8EBDAD5EAAA4477BE4242AE",
    "object_ids": ("HUM_F_ARM_Authority_Robe_Skirt_KEL.HUM_F_ARM_Authority_Skirt.0",),
    "bone_count": 82,
}
EXPECTED_AUTHORITY_ROUTES = (
    ("56d78c52-e349-4386-81c0-d8ee8bc8f10e", "aec60cfa-c6a1-4a77-8148-b2fa01e4d988", None),
    ("3f869845-badc-4035-ad51-e4ed25f43068", "aec60cfa-c6a1-4a77-8148-b2fa01e4d988", "122d5812-e27d-4638-905d-5e520cc26202"),
    ("b8c94f92-e857-4725-a59a-5db58bb9a8e6", "aec60cfa-c6a1-4a77-8148-b2fa01e4d988", "122d5812-e27d-4638-905d-5e520cc26202"),
)
EXPECTED_FAILURE_EVIDENCE = {
    ("vanilla", "BodyTop"): (0, 0, 4, 0.20319298429926863),
    ("vanilla", "Footwear"): (39, 0, 4, 0.1655718748294266),
    ("vanilla", "Pants"): (1, 0, 1, 0.22793790846010978),
    ("vanilla", "Sleeves"): (179, 0, 59, 0.03589030264608348),
    ("vanilla", "Thong"): (181, 0, 20, 0.05640343759001028),
    ("sbbf", "Sleeves"): (0, 0, 1, 0.159049789992582),
    ("sbbf", "Thong"): (0, 0, 0, 0.5175596977399949),
}
EXPECTED_UNRESOLVED_AUTHORITY_GEOMETRY_IDS = {
    "a913de25-257e-4e42-a677-c663effbe25a",
    "f1f789d3-c09e-485b-8f84-173e41fe9f96",
    "9bebc3db-3e3a-4faf-85fe-f19f589c247d",
    "94e2bcb1-8c38-4687-9833-c761536f0b0a",
}


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
    assert tuple({
        "name": component.name,
        "visual_resource_uuid": component.visual_resource_uuid,
        "source_file": component.source_file,
        "sha256": component.sha256,
        "object_ids": component.object_ids,
        "bone_count": component.bone_count,
    } for component in bard.components) == EXPECTED_BARD_COMPONENTS
    assert bard.protected_bcb.replacement_routes == 0
    assert bard.protected_bcb.component_hashes == (
        EXPECTED_BARD_COMPONENTS[0]["sha256"],
        EXPECTED_BARD_COMPONENTS[1]["sha256"],
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

    actual = {
        (mode, stream): (
            evidence.flips,
            evidence.new_zero_area,
            evidence.below_area_floor,
            evidence.minimum_area_ratio,
        )
        for mode, stream, evidence in bard.failure_evidence
    }

    assert actual == EXPECTED_FAILURE_EVIDENCE


def test_authority_requires_the_bcb_nine_object_main_without_a_netherstone_substitute():
    authority = load_authority_contract()

    actual_main = {
        "name": authority.main_component.name,
        "visual_resource_uuid": authority.main_component.visual_resource_uuid,
        "source_file": authority.main_component.source_file,
        "sha256": authority.main_component.sha256,
        "object_ids": authority.main_component.object_ids,
        "bone_count": authority.main_component.bone_count,
    }
    assert actual_main == EXPECTED_AUTHORITY_MAIN
    assert authority.main_component.object_count == 9
    assert not any("Netherstone" in object_id for object_id in EXPECTED_AUTHORITY_MAIN["object_ids"])
    with pytest.raises(ContractViolation, match="AUTHORITY_NETHERSTONE_SUBSTITUTE_FORBIDDEN"):
        authority.require_main_candidate(
            EXPECTED_AUTHORITY_MAIN["object_ids"] + (
                "TIF_FS_ARM_Authority_Robe.TIF_FS_ARM_Authority_Netherstone.8",
            )
        )


def test_authority_preserves_the_optional_skirt_distinction_by_item_identity():
    authority = load_authority_contract()

    actual_skirt = {
        "name": authority.skirt_component.name,
        "visual_resource_uuid": authority.skirt_component.visual_resource_uuid,
        "source_file": authority.skirt_component.source_file,
        "sha256": authority.skirt_component.sha256,
        "object_ids": authority.skirt_component.object_ids,
        "bone_count": authority.skirt_component.bone_count,
    }
    assert actual_skirt == EXPECTED_AUTHORITY_SKIRT
    assert tuple((
        route.item_uuid,
        route.main.visual_resource_uuid,
        None if route.skirt is None else route.skirt.visual_resource_uuid,
    ) for route in authority.routes) == EXPECTED_AUTHORITY_ROUTES
    assert authority.require_main_candidate(EXPECTED_AUTHORITY_MAIN["object_ids"]) == EXPECTED_AUTHORITY_MAIN["object_ids"]


def test_authority_fails_closed_for_every_current_unresolved_geometry_id():
    authority = load_authority_contract()

    assert set(authority.unresolved_geometry_ids) == EXPECTED_UNRESOLVED_AUTHORITY_GEOMETRY_IDS
    for geometry_id in EXPECTED_UNRESOLVED_AUTHORITY_GEOMETRY_IDS:
        with pytest.raises(ContractViolation, match=f"AUTHORITY_UNRESOLVED_GEOMETRY:{geometry_id}"):
            authority.require_geometry_admitted((geometry_id,))
    assert authority.require_geometry_admitted((EXPECTED_AUTHORITY_MAIN["visual_resource_uuid"],)) == (
        EXPECTED_AUTHORITY_MAIN["visual_resource_uuid"],
    )
