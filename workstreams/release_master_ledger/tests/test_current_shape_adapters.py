import hashlib

from workstreams.release_master_ledger.adapters import (
    adapt_bcbscantily,
    adapt_coverage,
    adapt_package_evidence,
    adapt_protected_registry,
    adapt_true_underwear,
    adapt_vanitybody,
    read_observations,
)
from workstreams.release_master_ledger.configuration import VerifiedInput


def verified(path, *, input_id="current", kind="JSON_EVIDENCE"):
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(input_id, kind, path, len(content), digest, digest)


def test_current_protected_entries_preserve_acceptance_and_exact_route(tmp_path):
    evidence = VerifiedInput(
        "protected_registry_v1", "PROTECTED_REGISTRY", tmp_path / "registry.json", 0, "A" * 64, "A" * 64
    )
    payload = {
        "entries": [{
            "id": "protected-1",
            "acceptance_status": "PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY",
            "source_module": {"uuid": "module-1", "version_identity": "B" * 64, "name": "Provider"},
            "item_contract": {"root_template": "root-1", "stats": "ARM_Test", "slot": "Body"},
            "route": {"mode": "bcb", "source_visual_resource": "source-vr", "source_path": "source.gr2", "target_visual_resource": "target-vr", "target_path": "target.gr2"},
            "protected_file": {"path": "target.gr2", "sha256": "C" * 64},
            "component_topology_contract": {"family": "hum_f"},
            "shared_consumers": ["consumer-1"],
            "permitted_future_action": "Obtain explicit gameplay acceptance.",
            "route_fingerprint_sha256": "D" * 64,
        }]
    }

    observations = adapt_protected_registry(payload, evidence)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.observation_id == "protected-1"
    assert observation.disposition == "PACKAGE_ONLY_PROTECTED"
    assert observation.identity_fields.source_module_uuid == "module-1"
    assert observation.identity_fields.ordered_source_vrs == ("source-vr",)
    assert observation.payload["mode_routes"]["bcb"]["target_paths"] == ["target.gr2"]
    assert observation.payload["payload_hash"] == "C" * 64
    assert observation.payload["source_route"]["ordered_file_hashes"] == ["UNKNOWN_SOURCE_FILE_HASH"]
    assert observation.protected_relations["route_fingerprint"] == "D" * 64


def test_sparse_protected_shape_uses_nonblank_source_route_placeholders(tmp_path):
    evidence = VerifiedInput(
        "protected_registry_v1", "PROTECTED_REGISTRY", tmp_path / "registry.json", 0, "A" * 64, "A" * 64
    )

    observation = adapt_protected_registry({"entries": [{"status": "GAMEPLAY_PASS"}]}, evidence)[0]

    assert observation.payload["source_route"]["ordered_paths"] == ["UNKNOWN_SOURCE_PATH"]


def test_current_coverage_shape_binds_native_identity_and_routes(tmp_path):
    record = {
        "identity": "stable-source-observation",
        "source_module": {"folder": "Folder", "name": "Name", "uuid": "module-1"},
        "root_template_uuid": "root-1",
        "stats_entry": "ARM_Test",
        "inheritance_chain": ["ARM_Test", "_Base"],
        "effective_slot": "VanityBody",
        "body_family": "HUM_F",
        "source_visual_resource_uuid": "source-vr",
        "source_visual_resource_path": "source.gr2",
        "component_contract": "UNASSESSED",
        "routes": {"BCB": {"visual_resource_uuid": "target-vr", "path": "target.gr2", "mesh_sha256": "E" * 64}},
        "disposition": "DEFERRED WITH CAUSE",
        "next_action": "Resolve the bounded route.",
    }
    evidence = VerifiedInput("coverage", "COVERAGE", tmp_path / "coverage.json", 0, "A" * 64, "A" * 64)

    observation = adapt_coverage([record], evidence)[0]

    assert observation.observation_id == "stable-source-observation"
    assert observation.identity_fields.source_module_uuid == "module-1"
    assert observation.identity_fields.root_template_uuid == "root-1"
    assert observation.identity_fields.stats_entry == "ARM_Test"
    assert observation.identity_fields.effective_slot == "VanityBody"
    assert observation.identity_fields.ordered_source_vrs == ("source-vr",)
    assert observation.payload["source_route"]["ordered_paths"] == ["source.gr2"]
    assert observation.payload["mode_routes"]["bcb"]["target_vrs"] == ["target-vr"]
    assert observation.payload["next_admissible_action"] == "Resolve the bounded route."


def test_unresolved_current_route_does_not_emit_blank_binding_sequences(tmp_path):
    evidence = VerifiedInput("coverage", "COVERAGE", tmp_path / "coverage.json", 0, "A" * 64, "A" * 64)
    observation = adapt_coverage([{
        "identity": "unresolved-route",
        "root_template_uuid": "root-1",
        "routes": {"Vanilla": {"visual_resource_uuid": None, "path": None, "mesh_sha256": None}},
        "disposition": "DEFERRED WITH CAUSE",
    }], evidence)[0]

    assert observation.payload["mode_routes"]["vanilla"] == {}


def test_current_underwear_and_vanity_shapes_bind_native_fields(tmp_path):
    underwear_input = VerifiedInput("underwear", "TRUE_UNDERWEAR", tmp_path / "u.json", 0, "A" * 64, "A" * 64)
    vanity_input = VerifiedInput("vanity", "VANITYBODY", tmp_path / "v.json", 0, "B" * 64, "B" * 64)

    underwear = adapt_true_underwear({"records": [{
        "module_uuid": "underwear-module", "root_template_uuid": "underwear-root",
        "stats_entry": "ARM_Underwear", "creation_path": "named_stats",
        "effective_slot": "Underwear", "inheritance": ["ARM_Underwear", "_Underwear"],
        "source_visual_resource_uuid": "MISSING", "disposition": "MISSING ROUTE / BUILD",
    }]}, underwear_input)[0]
    vanity = adapt_vanitybody({"records": [{
        "root_uuid": "vanity-root", "root_name": "ARM_Vanity", "effective_slot": "VanityBody",
        "named_stats_entry": "ARM_Vanity", "named_stats_using": "ARM_Camp_Body",
        "source_visual_resource_uuid": "", "disposition": "DEFERRED WITH CAUSE",
    }]}, vanity_input)[0]

    assert underwear.identity_fields.source_module_uuid == "underwear-module"
    assert underwear.identity_fields.root_template_uuid == "underwear-root"
    assert underwear.identity_fields.creation_path_kind == "named_stats"
    assert vanity.identity_fields.root_template_uuid == "vanity-root"
    assert vanity.identity_fields.stats_entry == "ARM_Vanity"


def test_current_bcbscantily_items_container_emits_each_item(tmp_path):
    evidence = VerifiedInput("items", "BCBSCANTILY", tmp_path / "items.json", 0, "A" * 64, "A" * 64)
    payload = {"items": [
        {"item_uuid": "item-1", "name": "First", "equipment_slot": "Body", "route_contracts": []},
        {"item_uuid": "item-2", "name": "Second", "equipment_slot": "Underwear", "route_contracts": []},
    ]}

    observations = adapt_bcbscantily(payload, evidence)

    assert len(observations) == 2
    assert [item.identity_fields.root_template_uuid for item in observations] == ["item-1", "item-2"]


def test_hash_verified_named_target_markdown_is_one_blocking_observation(tmp_path):
    document = tmp_path / "findings.md"
    document.write_text("# Padded Findings\n\nNo safe geometry.\n", encoding="utf-8")

    observations = read_observations(verified(document, input_id="padded_findings", kind="NAMED_TARGET"))

    assert len(observations) == 1
    assert observations[0].observation_kind == "NAMED_TARGET_EVIDENCE"
    assert observations[0].disposition == "DEFERRED_WITH_CAUSE"
    assert "NAMED_TARGET_UNRESOLVED" in observations[0].blocker_codes


def test_supporting_evidence_is_hash_checked_without_emitting_a_ledger_observation(tmp_path):
    evidence_file = tmp_path / "support.json"
    evidence_file.write_text('{"files": [{"sha256": "A"}]}\n', encoding="utf-8")

    observations = read_observations(verified(evidence_file, kind="SUPPORTING_EVIDENCE"))

    assert observations == []


def test_current_recluse_package_contract_preserves_exact_package_and_module_facts(tmp_path):
    evidence = VerifiedInput(
        "recluse_provider_contract_v2", "PACKAGE", tmp_path / "provider_contract.json",
        0, "A" * 64, "A" * 64,
    )
    package_sha = "A4BB716CB70C8046FE87ECB94A8D081563D953AD1E07BA1F521B01765768E345"
    payload = {
        "candidate_pak_sha256": package_sha,
        "source_mod_uuid": "096665c7-75aa-4747-9548-6ccafba985c8",
        "source_mod_version": "36028797018963968",
        "source_name": "SindaeImportedOutfitsRecluseWave2TEST",
        "live_registration_contract": "UNASSESSED",
    }

    observation = adapt_package_evidence(payload, evidence)[0]
    package_id = f"PACKAGE_SHA256:{package_sha}"

    assert observation.identity_fields.source_module_uuid == "096665c7-75aa-4747-9548-6ccafba985c8"
    assert observation.payload["source_module"] == {
        "name": "SindaeImportedOutfitsRecluseWave2TEST",
        "pak": package_id,
        "pak_sha256": package_sha,
        "uuid": "096665c7-75aa-4747-9548-6ccafba985c8",
        "version64": "36028797018963968",
    }
    assert observation.payload["payload_hash"] == package_sha
    assert observation.payload["shipped_package_id"] == package_id
    assert observation.disposition == "PACKAGE_READY_GAMEPLAY_UNASSESSED"
    assert observation.release_blocking is True
    assert "GAMEPLAY_UNASSESSED_PACKAGE_ONLY" in observation.blocker_codes
