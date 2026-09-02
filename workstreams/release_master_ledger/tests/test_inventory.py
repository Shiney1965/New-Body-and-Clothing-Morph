from dataclasses import replace
import hashlib
import json

import pytest

from workstreams.release_master_ledger.adapters import adapt_coverage
from workstreams.release_master_ledger.audit import build_completeness_audit
from workstreams.release_master_ledger.configuration import VerifiedInput
from workstreams.release_master_ledger.inventory import (
    BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    InventoryIntegrityError,
    extract_independent_inventories,
)
from workstreams.release_master_ledger.reconcile import reconcile_observations


def verified_json(tmp_path, input_id, kind, payload, filename=None):
    path = tmp_path / (filename or f"{input_id}.json")
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(input_id, kind, path, len(content), digest, digest)


def full_profile(profile_id, uuid, version64):
    return {
        "schema": "clothmorph.source-profile",
        "schema_version": 1,
        "profile_id": profile_id,
        "module": {
            "pak_filename": "Source.pak",
            "folder": "Source",
            "name": "Source",
            "uuid": uuid,
            "version64": version64,
            "pak_sha256": "A" * 64,
        },
        "content_manifest_sha256": "B" * 64,
        "root_stats_visualbank_digest": "C" * 64,
        "required_dependencies": [],
        "forbidden_modules": [],
        "supported_body_tuples": [],
        "permission": {
            "state": "release_cleared",
            "evidence_sha256": "D" * 64,
            "credit_line": "Synthetic source",
            "distribution_limits": [],
        },
        "route_partition_digest": "E" * 64,
    }


def test_source_inventory_is_extracted_from_raw_rows_before_adapter(tmp_path):
    raw = [
        {"observation_id": "row-a", "disposition": "BLOCKED WITH CAUSE"},
        {"observation_id": "row-b", "disposition": "BLOCKED WITH CAUSE"},
    ]
    input_ = verified_json(tmp_path, "coverage", "COVERAGE", raw)

    inventories = extract_independent_inventories([input_])

    assert inventories.source_observations == frozenset({"coverage:row-a", "coverage:row-b"})


def test_source_row_drop_mutation_populates_missing_from_ledger(tmp_path):
    raw = [
        {"observation_id": "row-a", "root_template_uuid": "root-a", "disposition": "BLOCKED WITH CAUSE"},
        {"observation_id": "row-b", "root_template_uuid": "root-b", "disposition": "BLOCKED WITH CAUSE"},
    ]
    input_ = verified_json(tmp_path, "coverage", "COVERAGE", raw)
    inventories = extract_independent_inventories([input_])
    retained = adapt_coverage(raw[:1], input_)[0]
    result = reconcile_observations([replace(retained, observation_id="coverage:row-a")])

    audit = build_completeness_audit(result, inventories.to_audit_sets())

    assert audit["missing_from_ledger"] == ["coverage:row-b"]


def test_package_drop_mutation_populates_packaged_without_ledger(tmp_path):
    package_sha = "A4BB716CB70C8046FE87ECB94A8D081563D953AD1E07BA1F521B01765768E345"
    input_ = verified_json(tmp_path, "package", "PACKAGE", {
        "candidate_pak_sha256": package_sha,
        "source_mod_uuid": "module-1",
        "source_mod_version": "1",
    })
    inventories = extract_independent_inventories([input_])

    audit = build_completeness_audit(reconcile_observations([]), inventories.to_audit_sets())

    assert audit["packaged_without_ledger"] == [f"PACKAGE_SHA256:{package_sha}"]


def test_package_inventory_retains_raw_package_ownership_claims(tmp_path):
    package_sha = "A4BB716CB70C8046FE87ECB94A8D081563D953AD1E07BA1F521B01765768E345"
    input_ = verified_json(tmp_path, "package", "PACKAGE", {
        "observation_id": "package-row",
        "candidate_pak_sha256": package_sha,
        "source_mod_uuid": "module-1",
        "source_mod_version": "1",
    })

    inventories = extract_independent_inventories([input_])

    package_id = f"PACKAGE_SHA256:{package_sha}"
    assert inventories.package_claims == {
        ("OBSERVATION:package:package-row", mode): (
            f"package_id:{package_id}",
        )
        for mode in ("vanilla", "sbbf", "bcb", "external")
    }


@pytest.mark.parametrize(
    ("input_id", "payload", "error"),
    [
        pytest.param(
            "provider_claim_inventory",
            {"schema": "clothmorph.provider-claims-inventory", "schema_version": 1, "routes": []},
            "PROVIDER_CLAIM_INVENTORY_SCHEMA_INVALID",
            id="provider-near-miss-schema",
        ),
        pytest.param(
            "provider_claim_inventory",
            {"schema": "clothmorph.provider-claim-inventory", "schema_version": 2, "routes": []},
            "PROVIDER_CLAIM_INVENTORY_SCHEMA_INVALID",
            id="provider-version",
        ),
        pytest.param(
            "provider_claim_inventory",
            {"schema": "clothmorph.provider-claim-inventory", "schema_version": 1, "routes": [], "unexpected": True},
            "PROVIDER_CLAIM_INVENTORY_UNEXPECTED_KEY:unexpected",
            id="provider-top-level-key",
        ),
        pytest.param(
            "provider_claim_inventory",
            {
                "schema": "clothmorph.provider-claim-inventory", "schema_version": 1,
                "routes": [{
                    "record_id": "LEDGER_" + "A" * 64, "mode": "sbbf",
                    "provider_ids": ["TYPO"],
                }],
            },
            "PROVIDER_CLAIM_INVENTORY_ROUTE_UNEXPECTED_KEY:provider_ids",
            id="provider-route-typo",
        ),
        pytest.param(
            "provider_claim_inventory",
            {
                "schema": "clothmorph.provider-claim-inventory", "schema_version": 1,
                "routes": [{
                    "canonical_source_key": "not-canonical", "mode": "sbbf",
                    "provider_id": "PROVIDER",
                }],
            },
            "CLAIM_INVENTORY_CANONICAL_SOURCE_KEY_INVALID",
            id="provider-unresolvable-canonical-key",
        ),
        pytest.param(
            "package_claim_inventory",
            {"schema": "clothmorph.package-claims-inventory", "schema_version": 1, "routes": []},
            "PACKAGE_CLAIM_INVENTORY_SCHEMA_INVALID",
            id="package-near-miss-schema",
        ),
        pytest.param(
            "package_claim_inventory",
            {"schema": "clothmorph.package-claim-inventory", "schema_version": 2, "routes": []},
            "PACKAGE_CLAIM_INVENTORY_SCHEMA_INVALID",
            id="package-version",
        ),
        pytest.param(
            "package_claim_inventory",
            {"schema": "clothmorph.package-claim-inventory", "schema_version": 1, "routes": [], "unexpected": True},
            "PACKAGE_CLAIM_INVENTORY_UNEXPECTED_KEY:unexpected",
            id="package-top-level-key",
        ),
        pytest.param(
            "package_claim_inventory",
            {
                "schema": "clothmorph.package-claim-inventory", "schema_version": 1,
                "routes": [{
                    "record_id": "LEDGER_" + "A" * 64, "mode": "sbbf",
                    "package_id": "PACKAGE_SHA256:" + "B" * 64,
                }],
            },
            "PACKAGE_CLAIM_INVENTORY_ROUTE_UNEXPECTED_KEY:package_id",
            id="package-route-typo",
        ),
    ],
)
def test_claim_authority_schemas_are_closed(tmp_path, input_id, payload, error):
    input_ = verified_json(tmp_path, input_id, "SUPPORTING_EVIDENCE", payload)

    with pytest.raises(InventoryIntegrityError, match=error):
        extract_independent_inventories([input_])


@pytest.mark.parametrize(
    ("role", "route", "error"),
    [
        pytest.param(
            "provider", {"record_id": None, "mode": "sbbf", "provider_id": "P"},
            "CLAIM_INVENTORY_IDENTITY_INVALID", id="provider-null-record-id",
        ),
        pytest.param(
            "provider", {"record_id": "LEDGER_" + "A" * 64, "mode": None, "provider_id": "P"},
            "CLAIM_INVENTORY_MODE_INVALID", id="provider-null-mode",
        ),
        pytest.param(
            "provider", {"record_id": "LEDGER_" + "A" * 64, "mode": "sbbf", "provider_id": None},
            "CLAIM_INVENTORY_PROVIDER_ID_INVALID", id="provider-null-provider-id",
        ),
        pytest.param(
            "provider", {"record_id": "LEDGER_" + "A" * 64, "mode": "sbbf", "target_vrs": None},
            "CLAIM_INVENTORY_TARGET_VRS_INVALID", id="provider-null-target-vrs",
        ),
        pytest.param(
            "provider", {"record_id": "LEDGER_" + "A" * 64, "mode": "sbbf", "target_paths": None},
            "CLAIM_INVENTORY_TARGET_PATHS_INVALID", id="provider-null-target-paths",
        ),
        pytest.param(
            "provider", {"record_id": "LEDGER_" + "A" * 64, "mode": "sbbf", "payload_hashes": None},
            "CLAIM_INVENTORY_PAYLOAD_HASHES_INVALID", id="provider-null-payload-hashes",
        ),
        pytest.param(
            "provider", {"record_id": "LEDGER_" + "A" * 64, "mode": "sbbf", "provenance": None},
            "CLAIM_INVENTORY_PROVENANCE_INVALID", id="provider-null-provenance",
        ),
        pytest.param(
            "package", {"record_id": None, "mode": "bcb", "package_ids": []},
            "CLAIM_INVENTORY_IDENTITY_INVALID", id="package-null-record-id",
        ),
        pytest.param(
            "package", {"record_id": "LEDGER_" + "A" * 64, "mode": None, "package_ids": []},
            "CLAIM_INVENTORY_MODE_INVALID", id="package-null-mode",
        ),
        pytest.param(
            "package", {"record_id": "LEDGER_" + "A" * 64, "mode": "bcb", "package_ids": None},
            "CLAIM_INVENTORY_PACKAGE_IDS_INVALID", id="package-null-package-ids",
        ),
        pytest.param(
            "package", {"record_id": "LEDGER_" + "A" * 64, "mode": "bcb", "shipped_package_id": None},
            "CLAIM_INVENTORY_PACKAGE_ID_INVALID", id="package-null-shipped-package-id",
        ),
    ],
)
def test_claim_authority_explicit_nulls_are_invalid(tmp_path, role, route, error):
    input_id = f"{role}_claim_inventory"
    payload = {
        "schema": f"clothmorph.{role}-claim-inventory",
        "schema_version": 1,
        "routes": [route],
    }
    input_ = verified_json(tmp_path, input_id, "SUPPORTING_EVIDENCE", payload)

    with pytest.raises(InventoryIntegrityError, match=error):
        extract_independent_inventories([input_])


@pytest.mark.parametrize(
    ("role", "route"),
    [
        pytest.param(
            "provider",
            {
                "record_id": "LEDGER_" + "A" * 64,
                "canonical_source_key": None,
                "mode": "sbbf",
                "provider_id": "P",
            },
            id="provider-record-id-plus-null-canonical-key",
        ),
        pytest.param(
            "provider",
            {
                "record_id": None,
                "canonical_source_key": "OBSERVATION:coverage:row-a",
                "mode": "sbbf",
                "provider_id": "P",
            },
            id="provider-canonical-key-plus-null-record-id",
        ),
        pytest.param(
            "package",
            {
                "record_id": "LEDGER_" + "A" * 64,
                "canonical_source_key": None,
                "mode": "bcb",
                "package_ids": [],
            },
            id="package-record-id-plus-null-canonical-key",
        ),
        pytest.param(
            "package",
            {
                "record_id": None,
                "canonical_source_key": "OBSERVATION:coverage:row-a",
                "mode": "bcb",
                "package_ids": [],
            },
            id="package-canonical-key-plus-null-record-id",
        ),
    ],
)
def test_claim_authority_redundant_null_identity_key_is_invalid(tmp_path, role, route):
    input_ = verified_json(tmp_path, f"{role}_claim_inventory", "SUPPORTING_EVIDENCE", {
        "schema": f"clothmorph.{role}-claim-inventory",
        "schema_version": 1,
        "routes": [route],
    })

    with pytest.raises(InventoryIntegrityError, match="^CLAIM_INVENTORY_IDENTITY_INVALID$"):
        extract_independent_inventories([input_])


@pytest.mark.parametrize(
    ("role", "route", "expected_claims"),
    [
        pytest.param(
            "provider",
            {
                "record_id": "LEDGER_" + "A" * 64,
                "mode": "sbbf",
                "provider_id": "P",
            },
            {("LEDGER_" + "A" * 64, "sbbf"): ("provider_id:P",)},
            id="provider-record-id-only",
        ),
        pytest.param(
            "provider",
            {
                "canonical_source_key": "OBSERVATION:coverage:row-a",
                "mode": "sbbf",
                "provider_id": "P",
            },
            {("OBSERVATION:coverage:row-a", "sbbf"): ("provider_id:P",)},
            id="provider-canonical-key-only",
        ),
        pytest.param(
            "package",
            {
                "record_id": "LEDGER_" + "A" * 64,
                "mode": "bcb",
                "package_ids": ["PACKAGE_SHA256:" + "B" * 64],
            },
            {
                ("LEDGER_" + "A" * 64, "bcb"):
                    ("package_id:PACKAGE_SHA256:" + "B" * 64,)
            },
            id="package-record-id-only",
        ),
        pytest.param(
            "package",
            {
                "canonical_source_key": "OBSERVATION:coverage:row-a",
                "mode": "bcb",
                "package_ids": ["PACKAGE_SHA256:" + "B" * 64],
            },
            {
                ("OBSERVATION:coverage:row-a", "bcb"):
                    ("package_id:PACKAGE_SHA256:" + "B" * 64,)
            },
            id="package-canonical-key-only",
        ),
    ],
)
def test_claim_authority_accepts_exactly_one_valid_identity_key(
    tmp_path, role, route, expected_claims,
):
    input_ = verified_json(tmp_path, f"{role}_claim_inventory", "SUPPORTING_EVIDENCE", {
        "schema": f"clothmorph.{role}-claim-inventory",
        "schema_version": 1,
        "routes": [route],
    })

    inventories = extract_independent_inventories([input_])

    claims = (
        inventories.provider_claims
        if role == "provider"
        else inventories.package_claims
    )
    assert claims == expected_claims
    assert getattr(inventories, f"{role}_authority_present") is True
    assert getattr(inventories, f"{role}_authority_complete") is True


def test_prior_evidence_join_drop_mutation_populates_unreferenced_set(tmp_path):
    input_ = verified_json(tmp_path, "support", "SUPPORTING_EVIDENCE", {"records": []})
    inventories = extract_independent_inventories([input_])

    audit = build_completeness_audit(reconcile_observations([]), inventories.to_audit_sets())

    assert audit["unreferenced_prior_evidence"] == [str(input_.path)]


def protected_pair(tmp_path, *, registry_entries=None, manifest_files=None):
    sha = "F" * 64
    entries = registry_entries if registry_entries is not None else [{
        "id": "protected-1",
        "protected_file": {"path": "protected.gr2", "bytes": 123, "sha256": sha},
    }]
    files = manifest_files if manifest_files is not None else [{
        "path": "protected.gr2", "bytes": 123, "sha256": sha, "consumers": ["protected-1"],
    }]
    return (
        verified_json(tmp_path, "protected_registry_v1", "PROTECTED_REGISTRY", {
            "entry_count": len(entries), "entries": entries,
        }),
        verified_json(tmp_path, "protected_hash_manifest_v1", "SUPPORTING_EVIDENCE", {
            "file_count": len(files), "files": files,
        }),
    )


def test_protected_manifest_metadata_reconciles_one_to_one_without_payload_access(tmp_path):
    registry, manifest = protected_pair(tmp_path)

    inventories = extract_independent_inventories([registry, manifest])

    relation = inventories.protected_manifest_relations["protected-1"]
    assert relation.protected_path == "protected.gr2"
    assert relation.bytes == 123
    assert relation.sha256 == "F" * 64
    assert relation.manifest_evidence_path == str(manifest.path)


@pytest.mark.parametrize(
    ("entries", "files", "error"),
    [
        ([{"id": "protected-1", "protected_file": {"path": "protected.gr2", "bytes": 123, "sha256": "F" * 64}}], [], "PROTECTED_MANIFEST_COUNT_MISMATCH"),
        ([{"id": "protected-1", "protected_file": {"path": "protected.gr2", "bytes": 123, "sha256": "F" * 64}}] * 2, [{"path": "protected.gr2", "bytes": 123, "sha256": "F" * 64, "consumers": ["protected-1"]}], "PROTECTED_REGISTRY_DUPLICATE_ID"),
        ([{"id": "protected-1", "protected_file": {"path": "protected.gr2", "bytes": 123, "sha256": "F" * 64}}], [{"path": "protected.gr2", "bytes": 123, "sha256": "E" * 64, "consumers": ["protected-1"]}], "PROTECTED_MANIFEST_METADATA_CONFLICT"),
    ],
)
def test_protected_manifest_missing_duplicate_or_conflicting_relationship_fails_closed(tmp_path, entries, files, error):
    registry, manifest = protected_pair(tmp_path, registry_entries=entries, manifest_files=files)

    with pytest.raises(InventoryIntegrityError, match=error):
        extract_independent_inventories([registry, manifest])


def test_required_profiles_come_from_module_rows_and_include_base_game(tmp_path):
    module = {"uuid": "module-1", "version64": "7"}
    input_ = verified_json(tmp_path, "source_profile_inventory", "SUPPORTING_EVIDENCE", {"modules": [module]})

    inventories = extract_independent_inventories([input_])

    assert inventories.required_source_profiles == frozenset({
        "SOURCE_PROFILE:module-1:7",
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    })
    assert inventories.complete_source_profiles == frozenset()


def test_incomplete_profile_contract_is_not_complete(tmp_path):
    module = {"uuid": "module-1", "version64": "7"}
    incomplete = full_profile("SOURCE_PROFILE:module-1:7", "module-1", "7")
    del incomplete["route_partition_digest"]
    input_ = verified_json(tmp_path, "source_profile_inventory", "SUPPORTING_EVIDENCE", {
        "modules": [module], "source_profiles": [incomplete],
    })

    inventories = extract_independent_inventories([input_])

    assert inventories.required_source_profiles == frozenset({
        "SOURCE_PROFILE:module-1:7", BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    })
    assert inventories.complete_source_profiles == frozenset()


def test_base_game_profile_remains_explicitly_missing_without_full_contract(tmp_path):
    module = {"uuid": "module-1", "version64": "7"}
    profile_id = "SOURCE_PROFILE:module-1:7"
    input_ = verified_json(tmp_path, "source_profile_inventory", "SUPPORTING_EVIDENCE", {
        "modules": [module], "source_profiles": [full_profile(profile_id, "module-1", "7")],
    })

    inventories = extract_independent_inventories([input_])

    assert inventories.complete_source_profiles == frozenset({profile_id})
    assert inventories.missing_source_profiles == (BASE_GAME_SOURCE_PROFILE_UNRESOLVED,)


def test_fully_complete_synthetic_profiles_have_a_true_audit_path(tmp_path):
    module = {"uuid": "module-1", "version64": "7"}
    profile_id = "SOURCE_PROFILE:module-1:7"
    input_ = verified_json(tmp_path, "source_profile_inventory", "SUPPORTING_EVIDENCE", {
        "modules": [module],
        "source_profiles": [
            full_profile(profile_id, "module-1", "7"),
            full_profile(BASE_GAME_SOURCE_PROFILE_UNRESOLVED, "base-game", "1"),
        ],
    })
    source_input = verified_json(tmp_path, "coverage", "COVERAGE", [{
        "observation_id": "source-row",
        "root_template_uuid": "root-source",
        "disposition": "BLOCKED WITH CAUSE",
    }])

    inventories = extract_independent_inventories([input_, source_input])
    source = adapt_coverage(json.loads(source_input.path.read_text(encoding="utf-8")), source_input)[0]
    payload = dict(source.payload)
    payload["evidence_pointers"] = (*source.evidence_pointers, str(input_.path))
    source = replace(source, observation_id="coverage:source-row", payload=payload)
    audit = build_completeness_audit(
        reconcile_observations([source]), inventories.to_audit_sets()
    )

    assert inventories.required_source_profiles == frozenset({
        profile_id, BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    })
    assert inventories.complete_source_profiles == inventories.required_source_profiles
    assert audit["required_source_profiles_complete"] is True
    assert audit["source_complete"] is True
