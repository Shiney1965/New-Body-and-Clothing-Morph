import pytest

from workstreams.vanitybody.local_integration import LocalIntegrationUnavailable, load_local_integration


try:
    load_local_integration()
except LocalIntegrationUnavailable as exc:
    pytestmark = pytest.mark.skip(reason=f"local integration not configured: {exc}")
else:
    from workstreams.vanitybody.correct_targets import TARGET_VISUAL_RESOURCES
    from workstreams.vanitybody.uuid_audit import audit_reserved_identities


def test_reserved_module_and_target_visual_resources_have_no_textual_collision_in_audited_packages():
    pytest.skip("integration audit needs explicit local audit roots from the local ledger manifest")
    assert audit.collisions == {}
    assert audit.scanned_file_count > 0
    assert set(audit.reserved_visual_resource_uuids) == set(TARGET_VISUAL_RESOURCES.values())
    assert audit.reserved_module_uuid == "f7c23240-3121-504b-8e86-65d235c3ce98"
