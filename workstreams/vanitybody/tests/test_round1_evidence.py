import pytest

from workstreams.vanitybody.local_integration import LocalIntegrationUnavailable, load_local_integration


try:
    INTEGRATION = load_local_integration()
except LocalIntegrationUnavailable as exc:
    pytestmark = pytest.mark.skip(reason=f"local integration not configured: {exc}")
else:
    from workstreams.vanitybody.anchors import load_anchor_contracts
    from workstreams.vanitybody.real_structure import inspect_glb, wedding_boundary
    from workstreams.vanitybody.route_evidence import load_route_evidence


def test_every_anchor_has_current_offline_target_and_protected_payload_evidence():
    evidence = load_route_evidence(INTEGRATION)
    for anchor in load_anchor_contracts():
        current = evidence[(anchor.root_uuid, anchor.mode)]
        assert current.target_visual_resource_uuid
        assert current.target_path
        assert len(current.target_sha256) == 64
        for mode in anchor.protected_modes:
            protected = current.protected_payloads[mode]
            assert protected.visual_resource_uuid
            assert protected.path
            assert len(protected.sha256) == 64
        assert current.visual_evidence_pointer
        assert current.route_evidence_pointer


def test_real_wedding_source_structure_proves_no_garment_only_boundary():
    profile = inspect_glb(INTEGRATION.glb_directory / "Wedding.glb")
    assert profile.components == (("HUM_F_NKD_Body_A_Mesh", 7996, 0),)
    assert profile.file_sha256 == "EBF62A0029258D212740D67E4D0517A7A604FB235EAFAFC820AFDC5A2725F597"
    assert profile.position_sha256 == "5605B44D13FB6A63ACAC90C8B3598B0A0D32CBC4A868648DBE91DF1D68D5ACC7"
    assert wedding_boundary(profile).status == "UNPROVEN_EMBEDDED_BODY"
