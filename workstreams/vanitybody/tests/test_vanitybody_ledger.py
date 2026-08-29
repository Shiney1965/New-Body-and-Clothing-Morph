import pytest

from workstreams.vanitybody.local_integration import LocalIntegrationUnavailable, load_local_integration


try:
    load_local_integration()
except LocalIntegrationUnavailable as exc:
    pytestmark = pytest.mark.skip(reason=f"local integration not configured: {exc}")
else:
    from workstreams.vanitybody.inventory import build_ledger


def test_available_bcbpak_root_template_inventory_is_classified_and_contains_every_anchor():
    pytest.skip("integration ledger needs explicit local roots/stats/visual inputs from the local ledger manifest")
    assert ledger["scope"] == "BCBPak root-template VanityBody inventory only"
    assert ledger["records"]
    assert all(record["effective_slot"] == "VanityBody" for record in ledger["records"])
    assert all(record["disposition"] != "UNCLASSIFIED" for record in ledger["records"])
    assert all(
        record["disposition"] == "DEFERRED WITH CAUSE"
        for record in ledger["records"]
        if not record["source_visual_resource_uuid"]
    )
    roots = {record["root_uuid"] for record in ledger["records"]}
    assert {
        "50bf6831-84ff-42d1-aa18-a97dc3f96a6a",
        "50ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25",
        "17ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25",
        "82bf6831-84ff-42d1-aa18-a97dc3f96a6a",
    } <= roots
    wedding = next(record for record in ledger["records"] if record["root_uuid"] == "50bf6831-84ff-42d1-aa18-a97dc3f96a6a")
    assert wedding["source_visual_resource_uuid"] == "0e7e2bf3-216c-4686-8cd7-bc13baca2ec4"
    assert wedding["disposition"] == "CONFIRMED DEFECT / CORRECT"
