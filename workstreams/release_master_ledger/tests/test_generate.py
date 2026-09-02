import hashlib
import importlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import time

import pytest

from workstreams.release_master_ledger.adapters import adapt_coverage
from workstreams.release_master_ledger.configuration import EvidenceInput, LocalConfiguration, VerifiedInput
from workstreams.release_master_ledger.exclusions import RELEASE_MODES, exclusion_event_id
from workstreams.release_master_ledger.generate import _stable_evidence_references, generate
from workstreams.release_master_ledger.reconcile import reconcile_observations
from workstreams.release_master_ledger.reconcile import ReconciliationResult


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest().upper()


def synthetic_config(root: Path, *, record_count: int = 1) -> LocalConfiguration:
    evidence = root / "evidence" / "coverage.json"
    records = [
        {
            "observation_id": f"synthetic-{index}",
            "disposition": "BLOCKED WITH CAUSE",
            "root_template_uuid": f"root-{index}",
        }
        for index in range(record_count)
    ]
    digest = _write_json(evidence, {"records": records})
    return LocalConfiguration(
        inputs=(EvidenceInput("synthetic_coverage", "COVERAGE", evidence, digest),),
        output_path=root / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )


def lifecycle_generate_fixture(
    root: Path, *, provider_routes=(), package_routes=(), extra_inputs=(),
    include_provider_authority=True, include_package_authority=True,
) -> tuple[LocalConfiguration, str]:
    local = root / "local"
    evidence_root = local / "evidence"
    event_root = local / "exclusion_events"
    coverage_path = evidence_root / "coverage.json"
    coverage_record = {
        "observation_id": "lifecycle-record",
        "disposition": "DEFERRED WITH CAUSE",
        "source_module_uuid": "11111111-1111-1111-1111-111111111111",
        "source_profile_digest": "C" * 64,
        "creation_path_kind": "root_template",
        "root_template_uuid": "22222222-2222-2222-2222-222222222222",
        "stats_entry": "ARM_Lifecycle",
        "inheritance_digest": "D" * 64,
        "effective_slot": "Underwear",
        "body_tuple": ["Human", "Female", "BT1", "Regular", "HUM_F"],
        "ordered_source_vrs": ["33333333-3333-3333-3333-333333333333"],
        "component_contract_digest": "E" * 64,
        "source_module": {
            "pak": "Synthetic.pak",
            "folder": "SYNTHETIC_PROFILE",
            "name": "Synthetic",
            "uuid": "11111111-1111-1111-1111-111111111111",
            "version64": "1",
            "pak_sha256": "F" * 64,
            "profile_digest": "C" * 64,
        },
        "protected_relations": {
            "registry_ids": ["REGISTRY_REVIEWED"],
            "protected_consumers": ["UNACCEPTED_CONSUMER"],
            "shared_assets": ["Public/Synthetic/Shared.GR2"],
            "forbidden_targets": ["EMBEDDED_BODY_DATA"],
        },
    }
    coverage_sha = _write_json(coverage_path, {"records": [coverage_record]})
    coverage_verified = VerifiedInput(
        "coverage", "COVERAGE", coverage_path, coverage_path.stat().st_size,
        coverage_sha, coverage_sha,
    )
    record = reconcile_observations(
        adapt_coverage([coverage_record], coverage_verified)
    ).records[0]
    bound_provider_routes = [
        {
            **route,
            "record_id": (
                record.record_id
                if route.get("record_id") == "$RECORD_ID"
                else route.get("record_id")
            ),
        }
        for route in provider_routes
    ]
    bound_package_routes = [
        {
            **route,
            "record_id": (
                record.record_id
                if route.get("record_id") == "$RECORD_ID"
                else route.get("record_id")
            ),
        }
        for route in package_routes
    ]

    proof_path = evidence_root / "source-audit.json"
    proof_sha = _write_json(proof_path, {"result": "COMPLETE_ZERO_ROUTE"})
    provider_path = evidence_root / "provider-claims.json"
    provider_sha = _write_json(provider_path, {
        "schema": "clothmorph.provider-claim-inventory",
        "schema_version": 1,
        "routes": bound_provider_routes,
    })
    package_path = evidence_root / "package-claims.json"
    package_sha = _write_json(package_path, {
        "schema": "clothmorph.package-claim-inventory",
        "schema_version": 1,
        "routes": bound_package_routes,
    })

    for index, mode in enumerate(RELEASE_MODES):
        event = {
            "schema": "clothmorph.terminal-exclusion",
            "schema_version": 1,
            "record_id": record.record_id,
            "identity_sha256": record.identity_sha256,
            "source_profile_id": "SYNTHETIC_PROFILE",
            "mode": mode,
            "reason": "SOURCE_ABSENT_EXACT_PROFILE",
            "reason_proof": {
                "exact_profile": {
                    "id": "SYNTHETIC_PROFILE", "version": "1",
                    "sha256": "C" * 64,
                },
                "complete_source_inventory": {
                    "result": "COMPLETE", "evidence_path": "evidence/source-audit.json",
                    "evidence_sha256": proof_sha,
                },
                "zero_route_result": {
                    "result": "ZERO_ROUTE", "evidence_path": "evidence/source-audit.json",
                    "evidence_sha256": proof_sha,
                },
                "anti_omission": {
                    "result": "PASS", "evidence_path": "evidence/source-audit.json",
                    "evidence_sha256": proof_sha,
                },
            },
            "scope_statement": f"Exclude only the synthetic {mode} route.",
            "attempted_architectures": [],
            "fixed_acceptance_gates": {},
            "evidence": [{
                "path": "evidence/source-audit.json", "sha256": proof_sha,
                "claim": "source audit",
            }],
            "protected_impact": {
                "registry_ids": ["REGISTRY_REVIEWED"],
                "shared_consumers": ["UNACCEPTED_CONSUMER"],
                "shared_assets": ["Public/Synthetic/Shared.GR2"],
                "forbidden_targets": ["EMBEDDED_BODY_DATA"],
                "result": "NO_PROTECTED_MUTATION",
            },
            "next_project_if_reopened": "Recover the exact source profile.",
            "approved_by": "Alan",
            "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
            "created_utc": f"2026-09-02T12:0{index}:00Z",
        }
        event["event_id"] = exclusion_event_id(event)
        _write_json(event_root / f"{mode}.json", event)

    inputs = [
        EvidenceInput("coverage", "COVERAGE", coverage_path, coverage_sha),
        EvidenceInput("source_audit", "SUPPORTING_EVIDENCE", proof_path, proof_sha),
    ]
    if include_provider_authority:
        inputs.append(EvidenceInput(
            "provider_claim_inventory", "SUPPORTING_EVIDENCE",
            provider_path, provider_sha,
        ))
    if include_package_authority:
        inputs.append(EvidenceInput(
            "package_claim_inventory", "SUPPORTING_EVIDENCE",
            package_path, package_sha,
        ))
    inputs.extend(extra_inputs)
    return LocalConfiguration(
        inputs=tuple(inputs),
        output_path=local / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
        exclusion_events_dir=event_root,
    ), record.record_id


def test_generation_is_byte_deterministic_across_output_roots(tmp_path):
    first = generate(synthetic_config(tmp_path / "first"))
    second = generate(synthetic_config(tmp_path / "second"))

    assert first.ledger_sha256 == second.ledger_sha256
    assert first.audit_sha256 == second.audit_sha256
    assert first.markdown_sha256 == second.markdown_sha256


def test_generate_production_lifecycle_uses_empty_raw_claim_inventories(tmp_path):
    config, record_id = lifecycle_generate_fixture(tmp_path)

    result = generate(config)
    ledger = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert ledger["records"][0]["record_id"] == record_id
    assert ledger["records"][0]["disposition"] == "OUT_OF_SCOPE_WITH_PROOF"
    assert ledger["records"][0]["release_blocking"] is False
    assert audit["excluded_with_proof"] == [record_id]
    assert audit["exclusion_validation_failures"] == []
    assert audit["in_scope_nonterminal"] == []


@pytest.mark.parametrize("history_case", [
    "superseded", "revoked-older", "revoked-newer-fallback",
])
def test_generate_valid_history_closes_ledger_and_audit_consistently(tmp_path, history_case):
    config, record_id = lifecycle_generate_fixture(tmp_path)
    event_root = config.exclusion_events_dir
    current = json.loads((event_root / "sbbf.json").read_text(encoding="utf-8"))
    older = deepcopy(current)
    older["created_utc"] = "2026-09-02T11:00:00Z"
    older["event_id"] = exclusion_event_id(older)
    _write_json(event_root / "z-sbbf-older.json", older)
    selected = older if history_case == "revoked-newer-fallback" else current
    if history_case != "superseded":
        target = current if history_case == "revoked-newer-fallback" else older
        _write_json(event_root / "sbbf-revocation.json", {
            "event_type": "REVOCATION", "record_id": record_id, "mode": "sbbf",
            "revokes_event_id": target["event_id"],
            "created_utc": "2026-09-02T13:00:00Z",
        })

    result = generate(config)
    ledger = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert ledger["summary"]["record_count"] == 1
    record = ledger["records"][0]
    assert record["terminal_exclusion"]["sbbf"]["event"] == selected
    assert record["disposition"] == "OUT_OF_SCOPE_WITH_PROOF"
    assert record["release_blocking"] is False
    assert audit["excluded_with_proof"] == [record_id]
    assert audit["in_scope_nonterminal"] == []
    assert audit["exclusion_validation_failures"] == []
    assert audit["exclusion_history_failures"] == []


@pytest.mark.parametrize(("history_case", "expected_code"), [
    ("conflicting", "CONFLICTING_EXCLUSION_EVENTS"),
    ("invalid-current", "MISSING_REASON_PROOF:exact_profile"),
    ("invalid-older", "MISSING_REASON_PROOF:exact_profile"),
    ("unsigned-older", "EVENT_ID_MISMATCH"),
    ("unapproved-older", "APPROVED_BY_MISMATCH"),
    ("wrong-identity-older", "IDENTITY_SHA256_MISMATCH"),
    ("revoked-current", "EXCLUSION_ATTACHMENT_MISSING"),
])
def test_generate_invalid_or_revoked_history_stays_blocking(tmp_path, history_case, expected_code):
    config, record_id = lifecycle_generate_fixture(tmp_path)
    event_root = config.exclusion_events_dir
    current = json.loads((event_root / "sbbf.json").read_text(encoding="utf-8"))
    sibling = deepcopy(current)
    sibling["created_utc"] = "2026-09-02T11:00:00Z"
    if history_case == "conflicting":
        sibling["created_utc"] = current["created_utc"]
        sibling["scope_statement"] = "Conflicting same-time exclusion."
    elif history_case in {"invalid-current", "invalid-older"}:
        sibling["reason_proof"] = {}
        if history_case == "invalid-current":
            sibling["created_utc"] = "2026-09-02T13:00:00Z"
    elif history_case == "unapproved-older":
        sibling["approved_by"] = "Not Alan"
    elif history_case == "wrong-identity-older":
        sibling["identity_sha256"] = "0" * 64
    sibling["event_id"] = exclusion_event_id(sibling)
    if history_case == "unsigned-older":
        sibling["scope_statement"] = "Changed after signing."
    if history_case == "revoked-current":
        sibling = {
            "event_type": "REVOCATION", "record_id": record_id, "mode": "sbbf",
            "revokes_event_id": current["event_id"],
            "created_utc": "2026-09-02T13:00:00Z",
        }
    _write_json(event_root / "sbbf-sibling.json", sibling)

    result = generate(config)
    ledger = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert ledger["records"][0]["disposition"] == "DEFERRED_WITH_CAUSE"
    assert ledger["records"][0]["release_blocking"] is True
    assert ledger["records"][0]["terminal_exclusion"]["sbbf"] is None
    assert audit["excluded_with_proof"] == []
    assert audit["in_scope_nonterminal"] == [record_id]
    assert audit["exclusion_validation_failures"] == [record_id]
    assert any(expected_code in code for code in audit["exclusion_history_failures"])


@pytest.mark.parametrize("discovery_form", ["kind", "input-id", "schema", "schema-coverage"])
@pytest.mark.parametrize("with_claim", [False, True])
def test_generate_authority_discovery_forms_are_non_record_evidence(
    tmp_path, discovery_form, with_claim,
):
    config, record_id = lifecycle_generate_fixture(
        tmp_path,
        provider_routes=([{
            "record_id": "$RECORD_ID", "mode": "sbbf", "provider_id": "provider-a",
        }] if with_claim else ()),
        package_routes=([{
            "record_id": "$RECORD_ID", "mode": "bcb", "package_ids": ["PACKAGE_SHA256:" + "A" * 64],
        }] if with_claim else ()),
    )
    baseline = generate(config)
    expected_ledger = json.loads(baseline.ledger_path.read_text(encoding="utf-8"))
    expected_audit = json.loads(baseline.audit_path.read_text(encoding="utf-8"))
    inputs = []
    for input_ in config.inputs:
        if input_.input_id in {"provider_claim_inventory", "package_claim_inventory"}:
            if discovery_form == "kind":
                input_ = replace(input_, kind=input_.input_id.upper())
            elif discovery_form == "input-id":
                input_ = replace(input_, kind="PACKAGE")
            else:
                input_ = replace(
                    input_, input_id="schema-" + input_.input_id,
                    kind="COVERAGE" if discovery_form == "schema-coverage" else "PACKAGE",
                )
        inputs.append(input_)

    result = generate(replace(config, inputs=tuple(inputs)))
    ledger = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert ledger["summary"]["record_count"] == 1
    assert ledger["summary"]["observation_count"] == 1
    assert ledger["records"] == expected_ledger["records"]
    authority_ids = [input_.input_id for input_ in inputs if "claim_inventory" in input_.input_id]
    assert audit["registered_inventories"]["prior_evidence"] == sorted([
        "input:source_audit", *(f"input:{input_id}" for input_id in authority_ids),
    ])
    for name in ("in_scope_nonterminal", "excluded_modes_with_proof", "excluded_with_proof",
                 "exclusion_validation_failures", "exclusion_history_failures",
                 "excluded_but_packaged", "packaged_without_ledger", "ledger_without_source",
                 "missing_from_ledger"):
        assert audit[name] == expected_audit[name]
    assert audit["in_scope_nonterminal"] == ([record_id] if with_claim else [])


@pytest.mark.parametrize(
    ("include_provider", "include_package", "expected_codes"),
    [
        pytest.param(
            False, True, {"MISSING_PROVIDER_CLAIM_AUTHORITY"},
            id="missing-provider-authority",
        ),
        pytest.param(
            True, False, {"MISSING_PACKAGE_CLAIM_AUTHORITY"},
            id="missing-package-authority",
        ),
        pytest.param(
            False, False,
            {"MISSING_PROVIDER_CLAIM_AUTHORITY", "MISSING_PACKAGE_CLAIM_AUTHORITY"},
            id="missing-both-authorities",
        ),
    ],
)
def test_generate_attempted_attachment_requires_both_verified_claim_authorities(
    tmp_path, include_provider, include_package, expected_codes,
):
    config, record_id = lifecycle_generate_fixture(
        tmp_path,
        include_provider_authority=include_provider,
        include_package_authority=include_package,
    )

    result = generate(config)
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [record_id]
    assert audit["in_scope_nonterminal"] == [record_id]
    assert expected_codes <= {
        failure.split(":")[2]
        for failure in audit["exclusion_history_failures"]
        if failure.startswith("INVALID_EVENT:")
    }


@pytest.mark.parametrize(
    "claim",
    [
        pytest.param({"provider_id": "RAW_PROVIDER_ID"}, id="provider-id"),
        pytest.param({"target_vrs": ["44444444-4444-4444-4444-444444444444"]}, id="target-vr"),
        pytest.param({"target_paths": ["Public/Synthetic/Claim.GR2"]}, id="target-path"),
        pytest.param({"payload_hashes": ["7" * 64]}, id="payload-hash"),
        pytest.param({"provenance": "RAW_PROVIDER_PROVENANCE"}, id="provenance"),
    ],
)
def test_generate_raw_provider_claim_blocks_terminal_exclusion(tmp_path, claim):
    config, record_id = lifecycle_generate_fixture(
        tmp_path,
        provider_routes=({
            "record_id": "$RECORD_ID",
            "mode": "sbbf",
            **claim,
        },),
    )

    result = generate(config)
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [record_id]
    assert record_id in audit["in_scope_nonterminal"]


@pytest.mark.parametrize(
    "claim",
    [
        pytest.param(
            {"package_ids": ["PACKAGE_SHA256:" + "8" * 64]},
            id="package-ids",
        ),
        pytest.param(
            {"shipped_package_id": "PACKAGE_SHA256:" + "9" * 64},
            id="shipped-package-id",
        ),
    ],
)
def test_generate_raw_package_claim_blocks_terminal_exclusion(tmp_path, claim):
    config, record_id = lifecycle_generate_fixture(
        tmp_path,
        package_routes=({
            "record_id": "$RECORD_ID",
            "mode": "sbbf",
            **claim,
        },),
    )

    result = generate(config)
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [record_id]
    assert record_id in audit["in_scope_nonterminal"]


@pytest.mark.parametrize(
    ("authority", "mode", "expected_code"),
    [
        pytest.param(
            "provider", "sbbf", "INDEPENDENT_PROVIDER_CLAIM",
            id="stale-provider-record-id",
        ),
        pytest.param(
            "package", "bcb", "INDEPENDENT_PACKAGE_CLAIM",
            id="stale-package-record-id",
        ),
    ],
)
def test_generate_stale_direct_claim_id_blocks_real_record_mode_wide(
    tmp_path, authority, mode, expected_code,
):
    stale_record_id = "LEDGER_" + "A" * 64
    provider_routes = ({
        "record_id": stale_record_id,
        "mode": mode,
        "provider_id": "STALE_PROVIDER",
    },) if authority == "provider" else ()
    package_routes = ({
        "record_id": stale_record_id,
        "mode": mode,
        "package_ids": ["PACKAGE_SHA256:" + "B" * 64],
    },) if authority == "package" else ()
    config, record_id = lifecycle_generate_fixture(
        tmp_path,
        provider_routes=provider_routes,
        package_routes=package_routes,
    )
    assert record_id != stale_record_id

    result = generate(config)
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [record_id]
    assert audit["in_scope_nonterminal"] == [record_id]
    assert f"{expected_code}:{record_id}:{mode}" in audit[
        "exclusion_history_failures"
    ]


def test_raw_claim_canonical_source_key_resolves_through_reconciliation_map():
    module = importlib.import_module("workstreams.release_master_ledger.generate")
    resolve = getattr(module, "_resolve_independent_claims", None)
    assert callable(resolve)
    record_id = "LEDGER_" + "A" * 64
    claims = {
        ("OBSERVATION:package:package-row", "sbbf"): ("package_id:PACKAGE",),
        (record_id, "bcb"): ("provider_id:DIRECT",),
        "external": ("missing_provider_route_inventory:provider",),
    }
    reconciliation = ReconciliationResult(
        records=(),
        observation_to_record={"package:package-row": record_id},
        conflicts=(),
    )

    assert resolve(claims, reconciliation) == {
        (record_id, "sbbf"): ("package_id:PACKAGE",),
        "bcb": ("provider_id:DIRECT",),
        "external": ("missing_provider_route_inventory:provider",),
    }


@pytest.mark.parametrize(
    "route_inventory",
    [
        pytest.param({}, id="missing-routes"),
        pytest.param({"routes": []}, id="empty-routes"),
    ],
)
def test_generate_missing_provider_route_inventory_fails_closed(
    tmp_path, route_inventory,
):
    package_path = tmp_path / "local" / "evidence" / "provider-contract.json"
    package_sha = _write_json(package_path, {
        "candidate_pak_sha256": "A" * 64,
        "source_mod_uuid": "55555555-5555-5555-5555-555555555555",
        "source_mod_version": "1",
        "source_name": "SyntheticProvider",
        "route_count": 1,
        **route_inventory,
    })
    config, record_id = lifecycle_generate_fixture(
        tmp_path,
        extra_inputs=(EvidenceInput(
            "provider_contract", "PACKAGE", package_path, package_sha,
        ),),
    )

    result = generate(config)
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [record_id]
    assert record_id in audit["in_scope_nonterminal"]


def test_summary_is_recomputed_from_records(tmp_path):
    result = generate(synthetic_config(tmp_path, record_count=2))
    payload = json.loads(result.ledger_path.read_text(encoding="utf-8"))

    assert payload["summary"]["record_count"] == len(payload["records"]) == 2
    assert payload["summary"]["observation_count"] == 2
    assert "**Ledger records:** 2" in result.markdown_path.read_text(encoding="utf-8")


def test_json_outputs_use_canonical_pretty_encoding_and_one_trailing_newline(tmp_path):
    result = generate(synthetic_config(tmp_path))

    for path in (result.ledger_path, result.audit_path, result.manifest_path):
        content = path.read_bytes()
        assert content.endswith(b"\n")
        assert not content.endswith(b"\n\n")
        payload = json.loads(content.decode("utf-8"))
        assert content == (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def test_manifest_pins_each_verified_input_identity(tmp_path):
    config = synthetic_config(tmp_path)

    result = generate(config)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["inputs"] == [
        {
            "actual_sha256": config.inputs[0].expected_sha256,
            "bytes": config.inputs[0].path.stat().st_size,
            "expected_sha256": config.inputs[0].expected_sha256,
            "input_id": "synthetic_coverage",
            "kind": "COVERAGE",
            "path": str(config.inputs[0].path.resolve()),
        }
    ]


def test_hash_verification_does_not_infer_source_profile_completeness(tmp_path):
    result = generate(synthetic_config(tmp_path))

    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
    assert audit["required_source_profiles_complete"] is False
    assert audit["source_complete"] is False


def test_generation_namespaces_same_observation_id_from_distinct_inputs(tmp_path):
    inputs = []
    for input_id, root_uuid in (("first_source", "root-a"), ("second_source", "root-b")):
        evidence = tmp_path / "evidence" / f"{input_id}.json"
        digest = _write_json(evidence, {"records": [{
            "observation_id": "shared-item-id",
            "root_template_uuid": root_uuid,
            "disposition": "BLOCKED WITH CAUSE",
        }]})
        inputs.append(EvidenceInput(input_id, "COVERAGE", evidence, digest))
    config = LocalConfiguration(
        inputs=tuple(inputs),
        output_path=tmp_path / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )

    result = generate(config)

    payload = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    assert payload["summary"]["observation_count"] == 2
    assert payload["summary"]["record_count"] == 2


def test_evidence_reference_normalization_precomputes_paths_once(tmp_path):
    inputs = [
        VerifiedInput(str(index), "KIND", tmp_path / str(index), 1, "A" * 64, "A" * 64)
        for index in range(16)
    ]
    payload = {
        "records": [
            {"evidence_paths": [str(inputs[0].path)], "value": index}
            for index in range(100)
        ]
    }

    started = time.perf_counter()
    normalized = _stable_evidence_references(payload, inputs)
    elapsed = time.perf_counter() - started

    assert normalized["records"][0]["evidence_paths"] == ["input:0"]
    assert elapsed < 1.0


def test_supporting_evidence_inventory_is_nonempty_without_fake_ledger_record(tmp_path):
    primary = tmp_path / "evidence" / "primary.json"
    support = tmp_path / "evidence" / "support.json"
    primary_sha = _write_json(primary, {"records": [{
        "observation_id": "primary-row",
        "root_template_uuid": "root-primary",
        "disposition": "BLOCKED WITH CAUSE",
    }]})
    support_sha = _write_json(support, {"files": [{"sha256": "A" * 64}]})
    config = LocalConfiguration(
        inputs=(
            EvidenceInput("primary", "COVERAGE", primary, primary_sha),
            EvidenceInput("support", "SUPPORTING_EVIDENCE", support, support_sha),
        ),
        output_path=tmp_path / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )

    result = generate(config)
    ledger = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert ledger["summary"]["input_observation_counts"] == {"primary": 1, "support": 0}
    assert "SUPPORTING_EVIDENCE_REFERENCE" not in ledger["summary"]["observation_kind_counts"]
    assert ledger["summary"]["record_count"] == 1
    assert audit["registered_inventories"]["prior_evidence"] == ["input:support"]
    assert audit["unreferenced_prior_evidence"] == ["input:support"]


def test_package_inventory_uses_exact_normalized_package_id(tmp_path):
    package = tmp_path / "evidence" / "package.json"
    package_sha = _write_json(package, {
        "candidate_pak_sha256": "A" * 64,
        "source_mod_uuid": "module-1",
        "source_mod_version": "36028797018963968",
        "source_name": "RecluseProvider",
    })
    config = LocalConfiguration(
        inputs=(EvidenceInput("package", "PACKAGE", package, package_sha),),
        output_path=tmp_path / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )

    result = generate(config)
    ledger = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
    package_id = "PACKAGE_SHA256:" + "A" * 64

    assert ledger["records"][0]["shipped_package_id"] == package_id
    assert audit["registered_inventories"]["packaged_records"] == [package_id]
    assert audit["packaged_without_ledger"] == []


def test_registered_supporting_inventory_is_sorted_by_normalized_input_id(tmp_path):
    inputs = []
    for input_id, filename in (("z-input", "a.json"), ("a-input", "z.json")):
        evidence = tmp_path / filename
        digest = _write_json(evidence, {"input_id": input_id})
        inputs.append(EvidenceInput(input_id, "SUPPORTING_EVIDENCE", evidence, digest))
    config = LocalConfiguration(
        inputs=tuple(inputs),
        output_path=tmp_path / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )

    result = generate(config)
    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))

    assert audit["registered_inventories"]["prior_evidence"] == [
        "input:a-input",
        "input:z-input",
    ]
    assert audit["unreferenced_prior_evidence"] == [
        "input:a-input",
        "input:z-input",
    ]
