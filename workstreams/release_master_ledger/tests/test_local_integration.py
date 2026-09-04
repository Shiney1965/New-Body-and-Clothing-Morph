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
    "excluded_modes_with_proof",
    "excluded_with_proof",
    "exclusion_history_failures",
    "exclusion_validation_failures",
    "missing_from_ledger",
    "duplicate_identity",
    "unreferenced_prior_evidence",
    "packaged_without_ledger",
    "ledger_without_source",
    "in_scope_nonterminal",
}
SUPPORTING_INPUT_IDS = {
    "base_game_aggregate_census",
    "bcbscantily_class_ledger",
    "coverage_raw_registry_scoped",
    "protected_hash_manifest_v1",
    "source_profile_census_candidates",
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

    assert len(verified) == len(config.inputs) == 18
    assert config.exclusion_events_dir == WORKSTREAM_ROOT / "local" / "exclusion_events"
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
    assert ledger["summary"]["input_kind_counts"]["SUPPORTING_EVIDENCE"] == 8
    assert ledger["summary"]["observation_count"] == 3172
    assert len(ledger["records"]) == 3170
    assert all(
        record["mode_scope"] == {
            mode: {"advertised": True, "terminal_state": "NONTERMINAL"}
            for mode in ("vanilla", "sbbf", "bcb", "external")
        }
        and record["terminal_exclusion"] == {
            mode: None for mode in ("vanilla", "sbbf", "bcb", "external")
        }
        for record in ledger["records"]
    )

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
    assert "recluse_provider_contract_v2:recluse_provider_contract_v2:0" in audit["registered_inventories"]["source_observations"]

    soul_joined = [
        record for record in ledger["records"]
        if "input:soul_vest_alt_decision" in record["evidence_paths"]
        and "input:coverage_master_registry_scoped" in record["evidence_paths"]
    ]
    bard_joined = [
        record for record in ledger["records"]
        if "input:bard_findings" in record["evidence_paths"]
        and "input:coverage_master_registry_scoped" in record["evidence_paths"]
    ]
    padded_only = [
        record for record in ledger["records"]
        if record["evidence_paths"] == ["input:padded_findings"]
    ]
    assert soul_joined
    assert bard_joined
    assert len(padded_only) == 1
    assert all(record["disposition"] != "OUT_OF_SCOPE_WITH_PROOF" for record in (*soul_joined, *bard_joined, *padded_only))
    assert not any(
        record["evidence_paths"] == ["input:external_permission_manifest_v1"]
        and record["classification"].get("scope_mesh") == "UNKNOWN_PERMISSION_SCOPE"
        for record in ledger["records"]
    )

    source_profile_inventory = _json(by_id["source_profile_inventory"].path)
    census_candidates = _json(by_id["source_profile_census_candidates"].path)
    mod_freeze_bound = {
        f"SOURCE_PROFILE:{candidate['contract']['module']['uuid']}:{candidate['contract']['module']['version64']}"
        for candidate in census_candidates
    }
    base_game_census = _json(by_id["base_game_aggregate_census"].path)
    assert len(base_game_census) == 1
    assert base_game_census[0]["contract"]["profile_id"] == BASE_GAME_SOURCE_PROFILE_UNRESOLVED
    freeze_bound = set(mod_freeze_bound) | {BASE_GAME_SOURCE_PROFILE_UNRESOLVED}
    required_profiles = {
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
        *(
            f"SOURCE_PROFILE:{module['uuid']}:{module['version64']}"
            for module in source_profile_inventory["modules"]
        ),
        *mod_freeze_bound,
    }
    assert audit["required_source_profiles"] == sorted(required_profiles)
    # Freeze-bound census candidates become section-7.1-complete when independently
    # bound permission evidence fills admissible contracts. SCO (73928ffc) joins via
    # Alan's exact Nexus 2617 permissions-tab quote; BCB core trio (BCBPak/UniqueTav/
    # BCBScantily) joins via Alan 2026-07-11 Nexus 2351 review (Sindae required-dependency
    # grant). BCBPak vs BCBUniqueTav is body-path XOR / mutual exclusivity (not additive).
    # BASE_GAME closes from retained base_game_profile_20260902 capture digests via the
    # aggregate census release_profile_complete path (not a new mod package freeze).
    expected_complete = sorted(freeze_bound)
    assert audit["complete_source_profiles"] == expected_complete
    assert audit["missing_source_profiles"] == sorted(required_profiles - set(expected_complete))
    assert audit["required_source_profiles_complete"] is False
    assert audit["freeze_bound_source_profiles"] == sorted(freeze_bound)
    assert audit["freeze_missing_source_profiles"] == sorted(required_profiles - freeze_bound)
    assert audit["census_incomplete_source_profiles"] == []
    assert len(mod_freeze_bound) == 13
    assert len(expected_complete) == 14
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in expected_complete
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED not in audit["freeze_missing_source_profiles"]
    bcb_profiles = {
        "SOURCE_PROFILE:1d24059d-ff23-4a79-8892-57c85d512416:36028797018963968",
        "SOURCE_PROFILE:28c82588-4ad0-4907-afac-6567817c6b13:36028797018963968",
        "SOURCE_PROFILE:75934b95-f697-4d5b-890c-fe198b799484:36028797018963968",
    }
    assert bcb_profiles <= set(expected_complete)
    assert len(audit["registered_inventories"]["source_observations"]) == 3172
    assert audit["missing_from_ledger"] == []
    assert audit["duplicate_identity"] == []
    assert audit["ledger_without_source"] == []
    assert audit["source_complete"] is False
    assert len(audit["in_scope_nonterminal"]) == 3170
    assert audit["excluded_with_proof"] == []
    assert audit["excluded_modes_with_proof"] == []
    assert audit["exclusion_validation_failures"] == []
    assert audit["exclusion_history_failures"] == []
    assert audit["excluded_but_packaged"] == []

    assert manifest["inputs"] and len(manifest["inputs"]) == 18
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
