import json
from collections import Counter

import pytest

from workstreams.release_master_ledger.configuration import (
    WORKSTREAM_ROOT,
    load_local_configuration,
    verify_evidence_inputs,
)
from workstreams.release_master_ledger.generate import generate
from workstreams.release_master_ledger.inventory import BASE_GAME_SOURCE_PROFILE_UNRESOLVED
from workstreams.release_master_ledger.validation import validate_generated_ledger


CONFIG_PATH = WORKSTREAM_ROOT / "local" / "config.json"
AUDIT_SET_NAMES = {
    "excluded_but_packaged",
    "excluded_with_proof",
    "exclusion_validation_failures",
    "missing_from_ledger",
    "duplicate_identity",
    "unreferenced_prior_evidence",
    "packaged_without_ledger",
    "ledger_without_source",
    "in_scope_nonterminal",
}
SUPPORTING_INPUT_IDS = {
    "bcbscantily_class_ledger",
    "coverage_raw_registry_scoped",
    "protected_hash_manifest_v1",
    "source_profile_inventory",
    "true_underwear_route_audit",
    "vanitybody_route_protection",
}
RECLUSE_PACKAGE_SHA256 = "A4BB716CB70C8046FE87ECB94A8D081563D953AD1E07BA1F521B01765768E345"
RECLUSE_PACKAGE_ID = f"PACKAGE_SHA256:{RECLUSE_PACKAGE_SHA256}"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.mark.integration
def test_current_hash_locked_evidence_generates_truthful_master_ledger():
    if not CONFIG_PATH.is_file():
        pytest.skip("canonical hash-locked local config is absent")

    config = load_local_configuration()
    verified = verify_evidence_inputs(config)
    by_id = {item.input_id: item for item in verified}

    assert len(verified) == len(config.inputs) == 16
    assert all(item.actual_sha256 == item.expected_sha256 for item in verified)

    registry = _json(by_id["protected_registry_v1"].path)
    protected_manifest = _json(by_id["protected_hash_manifest_v1"].path)
    assert registry["entry_count"] == len(registry["entries"]) == 32
    assert protected_manifest["file_count"] == len(protected_manifest["files"]) == 32
    assert Counter(item["acceptance_status"] for item in registry["entries"]) == {
        "GAMEPLAY_PASS": 25,
        "USER_ACCEPTED_RESIDUAL": 1,
        "PROTECTED_SOURCE_NATIVE": 2,
        "PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY": 4,
    }

    assert len(_json(by_id["coverage_master_registry_scoped"].path)) == 2534
    assert len(_json(by_id["coverage_raw_registry_scoped"].path)) == 2534
    assert len(_json(by_id["true_underwear_ledger_v2"].path)["records"]) == 68
    assert len(_json(by_id["vanitybody_ledger_bcbpak"].path)["records"]) == 271

    result = generate(config)
    ledger = _json(result.ledger_path)
    audit = _json(result.audit_path)
    manifest = _json(result.manifest_path)

    protected_records = [
        record for record in ledger["records"]
        if set(record["evidence_paths"]) == {
            "input:protected_registry_v1", "input:protected_hash_manifest_v1",
        }
    ]
    assert len(protected_records) == 32
    assert Counter(record["disposition"] for record in protected_records) == {
        "ACCEPTED_PROTECTED": 26,
        "SOURCE_NATIVE_PROTECTED": 2,
        "PACKAGE_ONLY_PROTECTED": 4,
    }
    assert all(
        record["release_blocking"] is True
        and "GAMEPLAY_UNASSESSED_PACKAGE_ONLY" in record["blocker_codes"]
        for record in protected_records
        if record["disposition"] == "PACKAGE_ONLY_PROTECTED"
    )
    registry_by_id = {entry["id"]: entry for entry in registry["entries"]}
    for record in protected_records:
        registry_id = record["protected_relations"]["registry_ids"][0]
        relation = record["protected_relations"]["hash_manifest_entries"]
        assert len(relation) == 1
        assert relation[0]["registry_id"] == registry_id
        assert relation[0]["input_id"] == "protected_hash_manifest_v1"
        assert relation[0]["input_sha256"] == by_id["protected_hash_manifest_v1"].actual_sha256
        assert relation[0]["protected_path"] == registry_by_id[registry_id]["protected_file"]["path"]
        assert relation[0]["bytes"] == registry_by_id[registry_id]["protected_file"]["bytes"]
        assert relation[0]["sha256"] == registry_by_id[registry_id]["protected_file"]["sha256"]

    assert set(ledger["summary"]["input_observation_counts"]) == set(by_id)
    assert all(
        ledger["summary"]["input_observation_counts"][input_id] == 0
        for input_id in SUPPORTING_INPUT_IDS
    )
    assert "SUPPORTING_EVIDENCE_REFERENCE" not in ledger["summary"]["observation_kind_counts"]
    assert ledger["summary"]["input_kind_counts"]["SUPPORTING_EVIDENCE"] == 6
    assert ledger["summary"]["observation_count"] == len(ledger["records"]) == 3173

    supporting_records = [
        record for record in ledger["records"]
        if len(record["evidence_paths"]) == 1
        and record["evidence_paths"][0].removeprefix("input:") in SUPPORTING_INPUT_IDS
    ]
    assert supporting_records == []
    assert audit["registered_inventories"]["prior_evidence"] == [
        f"input:{input_id}" for input_id in sorted(SUPPORTING_INPUT_IDS)
    ]
    assert audit["unreferenced_prior_evidence"] == [
        f"input:{input_id}"
        for input_id in sorted(SUPPORTING_INPUT_IDS - {"protected_hash_manifest_v1"})
    ]

    recluse_records = [
        record for record in ledger["records"]
        if record["evidence_paths"] == ["input:recluse_provider_contract_v2"]
    ]
    assert len(recluse_records) == 1
    recluse = recluse_records[0]
    assert recluse["source_module"]["uuid"] == "096665c7-75aa-4747-9548-6ccafba985c8"
    assert recluse["source_module"]["version64"] == "36028797018963968"
    assert recluse["source_module"]["pak"] == RECLUSE_PACKAGE_ID
    assert recluse["source_module"]["pak_sha256"] == RECLUSE_PACKAGE_SHA256
    assert recluse["transformation"]["payload_hash"] == RECLUSE_PACKAGE_SHA256
    assert recluse["shipped_package_id"] == RECLUSE_PACKAGE_ID
    assert recluse["disposition"] == "PACKAGE_READY_GAMEPLAY_UNASSESSED"
    assert recluse["release_blocking"] is True
    assert "GAMEPLAY_UNASSESSED_PACKAGE_ONLY" in recluse["blocker_codes"]
    assert audit["registered_inventories"]["packaged_records"] == [RECLUSE_PACKAGE_ID]
    assert audit["packaged_without_ledger"] == []

    source_profile_inventory = _json(by_id["source_profile_inventory"].path)
    required_profiles = {
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
        *(
            f"SOURCE_PROFILE:{module['uuid']}:{module['version64']}"
            for module in source_profile_inventory["modules"]
        ),
    }
    assert audit["required_source_profiles"] == sorted(required_profiles)
    assert audit["complete_source_profiles"] == []
    assert audit["missing_source_profiles"] == sorted(required_profiles)
    assert audit["required_source_profiles_complete"] is False
    assert len(audit["registered_inventories"]["source_observations"]) == 2965
    assert audit["missing_from_ledger"] == []
    assert audit["duplicate_identity"] == []
    assert len(audit["ledger_without_source"]) == 208
    assert len(audit["in_scope_nonterminal"]) == 3173
    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == []
    assert audit["excluded_but_packaged"] == []

    assert manifest["inputs"] and len(manifest["inputs"]) == 16
    assert validate_generated_ledger(ledger) == []
    assert audit["unclassified_count"] == 0
    assert AUDIT_SET_NAMES <= audit.keys()
    assert all(isinstance(audit[name], list) for name in AUDIT_SET_NAMES)
    assert audit["release_complete"] is False
    assert all(
        blocker["code"].replace("_", "").isalnum()
        and blocker["code"] == blocker["code"].upper()
        and blocker["evidence_pointers"]
        and blocker["owner"]
        and blocker["next_admissible_action"]
        and isinstance(blocker["release_blocking"], bool)
        for blocker in ledger["blockers"]
    )
