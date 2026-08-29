from true_underwear.inventory import GarmentRecord
from true_underwear.route_audit import audit_one, audit_routes


def garment(slot: str, source: str = "FIXTURE_SOURCE") -> GarmentRecord:
    return GarmentRecord(
        source=source, module_folder=source, module_name=source,
        module_uuid="id", version64="1", display_name="Test", root_template_uuid="root",
        stats_entry="STAT", root_stats_entry="STAT", creation_path="named_stats",
        effective_slot=slot, inheritance=("STAT",), source_visual_resource_uuid="source-vr",
    )


def test_audit_rejects_vanity_source_in_true_underwear_package():
    audit = audit_routes([garment("VanityBody")], {}, {})

    assert audit[0].status == "OUT_OF_SCOPE"


def test_bcb_module_name_alone_does_not_prove_native_passthrough():
    result = audit_one(garment("Underwear"), {}, {})

    assert result.bcb.target_vr == ""
    assert result.bcb.protected is False


def test_target_vrs_without_path_hash_and_evidence_are_not_ready():
    routes = {
        mode: {"source-vr": {"target_vr": f"{mode}-target"}}
        for mode in ("Vanilla", "SBBF", "BCB")
    }

    result = audit_one(garment("Underwear"), {}, routes)

    assert result.status == "MISSING ROUTE / BUILD"


def complete_routes(evidence_status: str):
    return {
        mode: {
            "source-vr": {
                "target_vr": f"{mode}-target",
                "target_path": f"Fixture/{mode}.GR2",
                "target_sha256": "a" * 64,
                "evidence_status": evidence_status,
            }
        }
        for mode in ("Vanilla", "SBBF", "BCB")
    }


def test_unknown_evidence_status_is_not_ready():
    result = audit_one(garment("Underwear"), {}, complete_routes("TYPO"))

    assert result.status == "MISSING ROUTE / BUILD"


def test_provenance_validated_evidence_status_is_ready_with_complete_contracts():
    result = audit_one(garment("Underwear"), {}, complete_routes("PROVENANCE_VALIDATED"))

    assert result.status == "READY FOR TEST"
