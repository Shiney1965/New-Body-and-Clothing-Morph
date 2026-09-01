import json
from collections import Counter

import pytest

from workstreams.release_master_ledger.configuration import (
    WORKSTREAM_ROOT,
    load_local_configuration,
    verify_evidence_inputs,
)
from workstreams.release_master_ledger.generate import generate


CONFIG_PATH = WORKSTREAM_ROOT / "local" / "config.json"
AUDIT_SET_NAMES = {
    "missing_from_ledger",
    "duplicate_identity",
    "unreferenced_prior_evidence",
    "packaged_without_ledger",
    "ledger_without_source",
    "in_scope_nonterminal",
}


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
        if record["evidence_paths"] == ["input:protected_registry_v1"]
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

    assert manifest["inputs"] and len(manifest["inputs"]) == 16
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
