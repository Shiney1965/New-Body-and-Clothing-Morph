from dataclasses import replace
import json

from workstreams.release_master_ledger.adapters import adapt_permission_manifest
from workstreams.release_master_ledger.audit import build_completeness_audit
from workstreams.release_master_ledger.inventory import (
    BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    extract_independent_inventories,
)
from workstreams.release_master_ledger.configuration import VerifiedInput
from workstreams.release_master_ledger.reconcile import reconcile_observations
import hashlib


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


FREEZE_UUID = "bebe0904-d39d-49f9-81b5-3627e2e29e76"
FREEZE_VERSION = "36028799166447616"
FREEZE_SHA = "8A039D59AA301357D42A1E10879D4342C3D95703C91D92612579D0EB87E19341"
FREEZE_PROFILE = f"SOURCE_PROFILE:{FREEZE_UUID}:{FREEZE_VERSION}"
UNFROZEN_UUID = "1d24059d-ff23-4a79-8892-57c85d512416"
UNFROZEN_VERSION = "36028797018963968"
UNFROZEN_PROFILE = f"SOURCE_PROFILE:{UNFROZEN_UUID}:{UNFROZEN_VERSION}"


def census_candidate(*, release_complete=False, admissible=None, blockers=None, contract_overrides=None):
    contract = {
        "schema": "clothmorph.source-profile",
        "schema_version": 1,
        "profile_id": None,
        "module": {
            "pak_filename": "SMH_Gloomstalker_Gear.pak",
            "folder": "SMH_Gloomstalker_Gear",
            "name": "SMH_Gloomstalker_Gear",
            "uuid": FREEZE_UUID,
            "version64": FREEZE_VERSION,
            "pak_sha256": FREEZE_SHA,
        },
        "content_manifest_sha256": "B" * 64,
        "root_stats_visualbank_digest": "C" * 64,
        "required_dependencies": [],
        "forbidden_modules": None,
        "supported_body_tuples": None,
        "permission": {
            "state": None,
            "evidence_sha256": None,
            "credit_line": None,
            "distribution_limits": None,
        },
        "route_partition_digest": None,
    }
    if contract_overrides:
        contract.update(contract_overrides)
    return {
        "discovery_profile_id": f"DISCOVERY:{FREEZE_UUID}:{FREEZE_VERSION}:{FREEZE_SHA}",
        "release_profile_complete": release_complete,
        "admissible_contract": admissible,
        "blockers": list(blockers or ["BODY_TUPLE_UNRESOLVED", "PERMISSION_EVIDENCE_MISSING"]),
        "contract": contract,
    }


def permission_records(*rows):
    return {"records": list(rows)}


def namespace_permission(input_, payload):
    return [
        replace(observation, observation_id=f"{input_.input_id}:{observation.observation_id}")
        for observation in adapt_permission_manifest(payload, input_)
    ]


def test_permission_meshes_are_not_inventoried_without_freeze_binding(tmp_path):
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA.lower(),
        "scope_resolved": ["HUM_F_Gloom.GR2"],
    })
    input_ = verified_json(tmp_path, "permission", "PERMISSION", payload)

    inventories = extract_independent_inventories([input_])

    assert inventories.source_observations == frozenset()


def test_unmatched_permission_pak_hash_is_not_inventoried(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate()],
    )
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": "0" * 64,
        "scope_resolved": ["HUM_F_Gloom.GR2"],
    })
    permission = verified_json(tmp_path, "permission", "PERMISSION", payload)

    inventories = extract_independent_inventories([census, permission])

    assert inventories.source_observations == frozenset()
    assert FREEZE_PROFILE in inventories.required_source_profiles
    assert inventories.complete_source_profiles == frozenset()


def test_empty_permission_scope_is_not_inventoried_as_source(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate()],
    )
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA,
        "scope_resolved": [],
    })
    permission = verified_json(tmp_path, "permission", "PERMISSION", payload)

    inventories = extract_independent_inventories([census, permission])

    assert inventories.source_observations == frozenset()


def test_freeze_bound_permission_meshes_are_independently_inventoried(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate()],
    )
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA.lower(),
        "scope_resolved": ["HUM_F_Gloom.GR2", "HUM_M_Gloom.GR2"],
    })
    permission = verified_json(tmp_path, "permission", "PERMISSION", payload)

    inventories = extract_independent_inventories([census, permission])

    assert inventories.source_observations == frozenset({
        "permission:permission:0:0",
        "permission:permission:0:1",
    })
    assert inventories.required_source_profiles == frozenset({
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED, FREEZE_PROFILE,
    })
    assert inventories.complete_source_profiles == frozenset()
    assert inventories.freeze_bound_source_profiles == frozenset({FREEZE_PROFILE})
    assert inventories.freeze_missing_source_profiles == frozenset({
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
    })
    assert inventories.census_incomplete_source_profiles == frozenset({FREEZE_PROFILE})


def test_incomplete_census_candidate_cannot_self_authorize_even_with_full_contract(tmp_path):
    complete_contract = full_profile(FREEZE_PROFILE, FREEZE_UUID, FREEZE_VERSION)
    complete_contract["module"]["pak_sha256"] = FREEZE_SHA
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate(
            release_complete=False,
            admissible=complete_contract,
            contract_overrides=complete_contract,
        )],
    )

    inventories = extract_independent_inventories([census])

    assert FREEZE_PROFILE in inventories.required_source_profiles
    assert inventories.complete_source_profiles == frozenset()


def test_admissible_release_complete_census_contract_is_complete(tmp_path):
    complete_contract = full_profile(FREEZE_PROFILE, FREEZE_UUID, FREEZE_VERSION)
    complete_contract["module"]["pak_sha256"] = FREEZE_SHA
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate(
            release_complete=True,
            admissible=complete_contract,
            blockers=[],
            contract_overrides=complete_contract,
        )],
    )

    inventories = extract_independent_inventories([census])

    assert inventories.complete_source_profiles == frozenset({FREEZE_PROFILE})
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.missing_source_profiles
    assert FREEZE_PROFILE not in inventories.missing_source_profiles


def test_required_live_module_absent_from_freeze_is_recorded_exactly(tmp_path):
    live = verified_json(
        tmp_path, "source_profile_inventory", "SUPPORTING_EVIDENCE",
        {"modules": [{"uuid": UNFROZEN_UUID, "version64": UNFROZEN_VERSION}]},
    )
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate()],
    )

    inventories = extract_independent_inventories([live, census])

    assert inventories.required_source_profiles == frozenset({
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED, FREEZE_PROFILE, UNFROZEN_PROFILE,
    })
    assert inventories.freeze_bound_source_profiles == frozenset({FREEZE_PROFILE})
    assert inventories.freeze_missing_source_profiles == frozenset({
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED, UNFROZEN_PROFILE,
    })
    assert inventories.complete_source_profiles == frozenset()


def test_freeze_bound_permission_observation_closes_ledger_without_source(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate()],
    )
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA,
        "scope_resolved": ["HUM_F_Gloom.GR2"],
    })
    permission = verified_json(tmp_path, "permission", "PERMISSION", payload)
    inventories = extract_independent_inventories([census, permission])
    observations = namespace_permission(permission, payload)

    audit = build_completeness_audit(
        reconcile_observations(observations), inventories.to_audit_sets(),
    )

    assert [item.observation_id for item in observations] == ["permission:permission:0:0"]
    assert audit["ledger_without_source"] == []
    assert audit["missing_from_ledger"] == []
    assert audit["source_complete"] is False
    assert audit["release_complete"] is False
    assert audit["required_source_profiles_complete"] is False
    assert audit["freeze_missing_source_profiles"] == [BASE_GAME_SOURCE_PROFILE_UNRESOLVED]
    assert audit["freeze_bound_source_profiles"] == [FREEZE_PROFILE]


def test_permission_without_freeze_remains_ledger_without_source(tmp_path):
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA,
        "scope_resolved": ["HUM_F_Gloom.GR2"],
    })
    permission = verified_json(tmp_path, "permission", "PERMISSION", payload)
    inventories = extract_independent_inventories([permission])
    observations = namespace_permission(permission, payload)

    audit = build_completeness_audit(
        reconcile_observations(observations), inventories.to_audit_sets(),
    )

    assert audit["ledger_without_source"] == [
        reconcile_observations(observations).records[0].record_id,
    ]
    assert audit["source_complete"] is False

from workstreams.release_master_ledger.adapters import (
    adapt_coverage,
    adapt_named_target,
    adapt_package_evidence,
)
from workstreams.release_master_ledger.generate import attach_named_target_evidence


def namespace(input_, observations):
    return [
        replace(observation, observation_id=f"{input_.input_id}:{observation.observation_id}")
        for observation in observations
    ]


def test_empty_permission_scope_emits_no_placeholder_observation(tmp_path):
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA,
        "scope_resolved": [],
    })
    input_ = verified_json(tmp_path, "permission", "PERMISSION", payload)

    observations = adapt_permission_manifest(payload, input_)

    assert observations == []
    assert all(
        "UNKNOWN_PERMISSION_SCOPE" not in str(observation.payload)
        for observation in observations
    )


def test_empty_freeze_bound_permission_placeholder_is_not_ledger_without_source(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate()],
    )
    payload = permission_records({
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA,
        "scope_resolved": [],
    })
    permission = verified_json(tmp_path, "permission", "PERMISSION", payload)
    inventories = extract_independent_inventories([census, permission])
    observations = namespace_permission(permission, payload)

    audit = build_completeness_audit(
        reconcile_observations(observations), inventories.to_audit_sets(),
    )

    assert observations == []
    assert inventories.source_observations == frozenset()
    assert audit["ledger_without_source"] == []
    assert audit["source_complete"] is False
    assert audit["release_complete"] is False


def test_package_observation_is_independently_inventoried_as_source(tmp_path):
    package_sha = "A4BB716CB70C8046FE87ECB94A8D081563D953AD1E07BA1F521B01765768E345"
    payload = {
        "candidate_pak_sha256": package_sha,
        "source_mod_uuid": "096665c7-75aa-4747-9548-6ccafba985c8",
        "source_mod_version": "36028797018963968",
        "source_name": "SindaeImportedOutfitsRecluseWave2TEST",
    }
    package = verified_json(tmp_path, "recluse_provider_contract_v2", "PACKAGE", payload)
    inventories = extract_independent_inventories([package])
    observations = namespace(package, adapt_package_evidence(payload, package))

    audit = build_completeness_audit(
        reconcile_observations(observations), inventories.to_audit_sets(),
    )

    assert inventories.source_observations == frozenset({
        "recluse_provider_contract_v2:recluse_provider_contract_v2:0",
    })
    assert inventories.packaged_records == frozenset({f"PACKAGE_SHA256:{package_sha}"})
    assert audit["ledger_without_source"] == []
    assert audit["packaged_without_ledger"] == []
    assert audit["missing_from_ledger"] == []
    assert "096665c7-75aa-4747-9548-6ccafba985c8" not in "".join(
        inventories.freeze_bound_source_profiles
    )
    assert audit["source_complete"] is False
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.required_source_profiles


def test_named_target_json_joins_onto_matching_coverage_records(tmp_path):
    root = "274ee212-effb-44f0-b122-3d755a1d844e"
    coverage_payload = [{
        "observation_id": "soul-alt",
        "root_template_uuid": root,
        "stats_entry": "Soul_Vest_Alt",
        "garment_family": "Soul_Vest_Alt",
        "source_module_uuid": "73928ffc-07c0-46ac-8cf4-86a693b0cd92",
        "source_visual_resource_uuid": "cb557abd-d1d0-44fc-b9eb-3ced4dd48af9",
        "disposition": "DEFERRED WITH CAUSE",
    }]
    named_payload = {
        "item": "Soul_Vest_Alt",
        "item_uuid": root,
        "required_route": {"original_vr": "cb557abd-d1d0-44fc-b9eb-3ced4dd48af9"},
    }
    coverage = verified_json(tmp_path, "coverage", "COVERAGE", coverage_payload)
    named = verified_json(tmp_path, "soul_vest_alt_decision", "NAMED_TARGET", named_payload)
    inventories = extract_independent_inventories([coverage, named])
    observations = (
        namespace(coverage, adapt_coverage(coverage_payload, coverage))
        + namespace(named, adapt_named_target(named_payload, named))
    )
    reconciled = reconcile_observations(observations)
    records, observation_to_record = attach_named_target_evidence(
        reconciled.records, observations, reconciled.observation_to_record,
    )
    audit = build_completeness_audit(
        replace(reconciled, records=records, observation_to_record=observation_to_record),
        inventories.to_audit_sets(),
    )

    assert len(records) == 1
    assert str(named.path) in records[0].evidence_paths
    assert str(coverage.path) in records[0].evidence_paths
    assert audit["ledger_without_source"] == []
    assert audit["excluded_with_proof"] == []
    assert audit["source_complete"] is False
    assert records[0].disposition != "OUT_OF_SCOPE_WITH_PROOF"


def test_named_target_markdown_joins_onto_coverage_records_sharing_source_vr(tmp_path):
    vr = "c4e56439-38a8-4b9a-bec2-4c603f7473cc"
    coverage_payload = [{
        "observation_id": "bard-dress",
        "root_template_uuid": "42092137-4e81-4598-bb18-34939fbb8719",
        "stats_entry": "Bard_Dress",
        "garment_family": "Bard_Dress",
        "source_visual_resource_uuid": vr,
        "source_visual_resource_path": "Generated/Public/BCBScantily/Assets/HUM_F_CLT_Bard_Dress_Base_KEL.GR2",
        "disposition": "DEFERRED WITH CAUSE",
    }]
    coverage = verified_json(tmp_path, "coverage", "COVERAGE", coverage_payload)
    document = tmp_path / "bard.md"
    document.write_text(
        "# Bard Dress Vanilla and SBBF\n\n"
        f"Source VR: `{vr}`.\n"
        "Source path: `Generated/Public/BCBScantily/Assets/HUM_F_CLT_Bard_Dress_Base_KEL.GR2`.\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(document.read_bytes()).hexdigest().upper()
    named = VerifiedInput(
        "bard_findings", "NAMED_TARGET", document, document.stat().st_size, digest, digest,
    )
    from workstreams.release_master_ledger.adapters import read_observations
    inventories = extract_independent_inventories([coverage, named])
    observations = (
        namespace(coverage, adapt_coverage(coverage_payload, coverage))
        + namespace(named, read_observations(named))
    )
    reconciled = reconcile_observations(observations)
    records, observation_to_record = attach_named_target_evidence(
        reconciled.records, observations, reconciled.observation_to_record,
    )
    audit = build_completeness_audit(
        replace(reconciled, records=records, observation_to_record=observation_to_record),
        inventories.to_audit_sets(),
    )

    assert len(records) == 1
    assert str(named.path) in records[0].evidence_paths
    assert audit["ledger_without_source"] == []
    assert audit["excluded_with_proof"] == []


def test_unmatched_named_target_is_inventoried_as_source_without_invented_meshes(tmp_path):
    coverage_payload = [{
        "observation_id": "unrelated",
        "root_template_uuid": "11111111-1111-1111-1111-111111111111",
        "stats_entry": "Unrelated_Gown",
        "disposition": "DEFERRED WITH CAUSE",
    }]
    coverage = verified_json(tmp_path, "coverage", "COVERAGE", coverage_payload)
    document = tmp_path / "padded.md"
    document.write_text(
        "# Padded Armour / BG Watch Leather Topology Recovery Findings\n\n"
        "No second independent BG Watch Armor candidate was found.\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(document.read_bytes()).hexdigest().upper()
    named = VerifiedInput(
        "padded_findings", "NAMED_TARGET", document, document.stat().st_size, digest, digest,
    )
    from workstreams.release_master_ledger.adapters import read_observations
    inventories = extract_independent_inventories([coverage, named])
    observations = (
        namespace(coverage, adapt_coverage(coverage_payload, coverage))
        + namespace(named, read_observations(named))
    )
    reconciled = reconcile_observations(observations)
    records, observation_to_record = attach_named_target_evidence(
        reconciled.records, observations, reconciled.observation_to_record,
    )
    audit = build_completeness_audit(
        replace(reconciled, records=records, observation_to_record=observation_to_record),
        inventories.to_audit_sets(),
    )

    assert "padded_findings:padded_findings" in inventories.source_observations
    assert len(records) == 2
    named_records = [
        record for record in records if str(named.path) in record.evidence_paths
        and str(coverage.path) not in record.evidence_paths
    ]
    assert len(named_records) == 1
    assert audit["ledger_without_source"] == []
    assert audit["missing_from_ledger"] == []
    assert audit["excluded_with_proof"] == []


def test_named_target_with_item_name_does_not_join_different_stats_same_root(tmp_path):
    root = "274ee212-effb-44f0-b122-3d755a1d844e"
    coverage_payload = [{
        "observation_id": "soul",
        "root_template_uuid": root,
        "stats_entry": "Soul_Vest",
        "garment_family": "Soul_Vest",
        "disposition": "DEFERRED WITH CAUSE",
    }]
    named_payload = {
        "item": "Soul_Vest_Alt",
        "item_uuid": root,
    }
    coverage = verified_json(tmp_path, "coverage", "COVERAGE", coverage_payload)
    named = verified_json(tmp_path, "soul_vest_alt_decision", "NAMED_TARGET", named_payload)
    observations = (
        namespace(coverage, adapt_coverage(coverage_payload, coverage))
        + namespace(named, adapt_named_target(named_payload, named))
    )
    reconciled = reconcile_observations(observations)
    records, _observation_to_record = attach_named_target_evidence(
        reconciled.records, observations, reconciled.observation_to_record,
    )

    assert len(records) == 2
    coverage_record = next(
        record for record in records if str(coverage.path) in record.evidence_paths
    )
    assert str(named.path) not in coverage_record.evidence_paths



def permission_grant_record(*, scope=None):
    return {
        "mod_uuid": FREEZE_UUID,
        "pak_sha256": FREEZE_SHA.lower(),
        "scope_resolved": list(scope if scope is not None else ["HUM_F_Gloom.GR2"]),
        "decision": "process",
        "evidence": {
            "where": "NexusMods permissions tab (mod 16997)",
            "when": "2026-07-21",
            "quote": "Recorded from the source noted in where.",
        },
        "flag": {
            "mod_uuid": FREEZE_UUID,
            "permission": "granted",
            "credit_line": "Gloomstalker Gear by Samerrah (Nexus mod 16997)",
            "exclude": [],
            "bodies": ["*"],
            "items": "*",
        },
    }


def test_freeze_permission_join_makes_incomplete_census_admissible(tmp_path):
    """Independent permission evidence can admit a freeze-bound census contract.

    Census may remain release_profile_complete=false; ledger completeness is the
    section-7.1 contract filled from freeze digests + permission binding, not a
    self-authored candidate admissible_contract.
    """
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate(
            release_complete=False,
            blockers=["BODY_TUPLE_UNRESOLVED", "PERMISSION_EVIDENCE_MISSING", "ROUTE_PARTITION_UNRESOLVED"],
        ) | {"observed_creation_paths_digest": "F" * 64}],
    )
    permission = verified_json(
        tmp_path, "permission", "PERMISSION",
        permission_records(permission_grant_record()),
    )

    inventories = extract_independent_inventories([census, permission])

    assert inventories.complete_source_profiles == frozenset({FREEZE_PROFILE})
    assert FREEZE_PROFILE not in inventories.census_incomplete_source_profiles
    assert FREEZE_PROFILE in inventories.freeze_bound_source_profiles
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.missing_source_profiles


def test_empty_permission_scope_still_admits_freeze_profile_without_invented_meshes(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate(release_complete=False) | {"observed_creation_paths_digest": "F" * 64}],
    )
    permission = verified_json(
        tmp_path, "permission", "PERMISSION",
        permission_records(permission_grant_record(scope=[])),
    )

    inventories = extract_independent_inventories([census, permission])

    assert inventories.complete_source_profiles == frozenset({FREEZE_PROFILE})
    assert inventories.source_observations == frozenset()


def test_permission_pak_mismatch_does_not_admit_freeze_profile(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate(release_complete=False) | {"observed_creation_paths_digest": "F" * 64}],
    )
    record = permission_grant_record()
    record["pak_sha256"] = "0" * 64
    permission = verified_json(
        tmp_path, "permission", "PERMISSION", permission_records(record),
    )

    inventories = extract_independent_inventories([census, permission])

    assert inventories.complete_source_profiles == frozenset()
    assert FREEZE_PROFILE in inventories.census_incomplete_source_profiles


def test_census_without_permission_join_remains_incomplete(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [census_candidate(release_complete=False) | {"observed_creation_paths_digest": "F" * 64}],
    )

    inventories = extract_independent_inventories([census])

    assert inventories.complete_source_profiles == frozenset()
    assert FREEZE_PROFILE in inventories.census_incomplete_source_profiles


SCO_UUID = "73928ffc-07c0-46ac-8cf4-86a693b0cd92"
SCO_VERSION = "72057772279070722"
SCO_SHA = "182A77E669F1576A3B07D29F226161A43F76EA10D8D3EFEE442D36AEA9F7A891"
SCO_PROFILE = f"SOURCE_PROFILE:{SCO_UUID}:{SCO_VERSION}"
SCO_CREDIT_LINE = "Scantily Camp Outfit by Crosscrusade (Nexus mod 2617)"
SCO_EVIDENCE_WHERE = (
    "Alan 2026-09-03 paste of Nexus https://www.nexusmods.com/baldursgate3/mods/2617 "
    "permissions tab (agent browser fetch blocked by Adult content disabled)"
)
SCO_EVIDENCE_WHEN = "2026-09-03"
SCO_EVIDENCE_QUOTE = "Credits and distribution permission\n\nOther user's assets\nAll the assets in this file belong to the author, or are from free-to-use modder's resources\n\nUpload permission\nYou are not allowed to upload this file to other sites under any circumstances\n\nModification permission\nYou are allowed to modify my files and release bug fixes or improve on the features so long as you credit me as the original creator\n\nConversion permission\nYou are not allowed to convert this file to work on other games under any circumstances\n\nAsset use permission\nYou are allowed to use the assets in this file without permission as long as you credit me\n\nAsset use permission in mods/files that are being sold\nYou are not allowed to use assets from this file in any mods/files that are being sold, for money, on Steam Workshop or other platforms\n\nAsset use permission in mods/files that earn donation points\nYou are allowed to earn Donation Points for your mods if they use my assets"
SCO_PERMISSION_STATEMENT = (
    "Nexus permissions allow asset use without permission and modification/bug-fix "
    "releases so long as Crosscrusade is credited as the original creator; upload, "
    "conversion, and use in sold mods/files are not allowed; Donation Points are allowed."
)


def sco_census_candidate():
    return census_candidate(
        release_complete=False,
        blockers=[
            "BODY_TUPLE_UNRESOLVED",
            "PERMISSION_EVIDENCE_MISSING",
            "ROUTE_PARTITION_UNRESOLVED",
        ],
        contract_overrides={
            "module": {
                "pak_filename": "Scantily.pak",
                "folder": "SCO",
                "name": "Scantily Camp Outfit",
                "uuid": SCO_UUID,
                "version64": SCO_VERSION,
                "pak_sha256": SCO_SHA,
            },
        },
    ) | {"observed_creation_paths_digest": "F" * 64}


def sco_exact_permissions_tab_record():
    evidence = {
        "where": SCO_EVIDENCE_WHERE,
        "when": SCO_EVIDENCE_WHEN,
        "quote": SCO_EVIDENCE_QUOTE,
    }
    return {
        "mod_uuid": SCO_UUID,
        "mod_name": "Scantily Camp Outfit",
        "source_pak": "Scantily.pak",
        "pak_sha256": SCO_SHA.lower(),
        "flag_sha256": None,
        "scope_resolved": [],
        "unresolvable": [],
        "per_body_decisions": {"sbbf": "process", "bcb": "process"},
        "mesh_hashes": {},
        "scanned": "2026-09-03T00:00:00+00:00",
        "decision": "process",
        "reason": "",
        "source": "override",
        "evidence": evidence,
        "flag": {
            "mod_uuid": SCO_UUID,
            "spec_version": 1,
            "permission": "granted",
            "bodies": ["*"],
            "items": "*",
            "exclude": [],
            "mod_version": "as-shipped",
            "credit_line": SCO_CREDIT_LINE,
            "permission_statement": SCO_PERMISSION_STATEMENT,
            "url": "https://www.nexusmods.com/baldursgate3/mods/2617",
            "evidence": evidence,
        },
    }


def test_sco_exact_nexus_permissions_tab_quote_admits_freeze_profile(tmp_path):
    """SCO freeze profile completes only with Alan's exact Nexus permissions-tab quote.

    Citation-only paraphrases are aborted for this bind; evidence.quote must be the
    full permissions-tab block Alan pasted on 2026-09-03.
    """
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [sco_census_candidate()],
    )
    record = sco_exact_permissions_tab_record()
    permission = verified_json(
        tmp_path, "permission", "PERMISSION", permission_records(record),
    )

    inventories = extract_independent_inventories([census, permission])

    assert inventories.complete_source_profiles == frozenset({SCO_PROFILE})
    assert SCO_PROFILE not in inventories.census_incomplete_source_profiles
    assert SCO_PROFILE in inventories.freeze_bound_source_profiles
    assert record["flag"]["credit_line"] == SCO_CREDIT_LINE
    assert record["flag"]["permission"] == "granted"
    assert record["evidence"]["where"] == SCO_EVIDENCE_WHERE
    assert record["evidence"]["when"] == SCO_EVIDENCE_WHEN
    assert record["evidence"]["quote"] == SCO_EVIDENCE_QUOTE
    quote_lines = record["evidence"]["quote"].splitlines()
    assert quote_lines[0] == "Credits and distribution permission"
    assert quote_lines[-1] == (
        "You are allowed to earn Donation Points for your mods if they use my assets"
    )
    assert "We have permission to use SCO" not in record["evidence"]["quote"]
    assert "Recorded from the source noted" not in record["evidence"]["quote"]


# Retained base-game aggregate capture identities (clothmorph-runtime14 research 2026-09-02).
BASE_SHARED_UUID = "ed539163-bb70-431b-96a7-f5b2eda5376b"
BASE_SHARED_VERSION = "36029297386049870"
BASE_SHARED_PAK_SHA = "9D63D634DAC98F1E864EAD6B8FF6452B566372997D61C1BF3A9B156A61536AA7"
BASE_SHARED_CONTENT_MANIFEST_SHA = "08394D7AA4C77AEEDF5FDEE8171867E0EDB9D44F07DA7B924D82D83DA301431E"
BASE_EQUIPMENT_RACES_SHA = "FC66EDC47FB8ABC10F42D564D49C7BE535C2357B5E2070D94E34912495CBD291"
BASE_TOP_LEVEL_MANIFEST_SHA = "048FB0EBD34D5DD6A116235ACA93A9A79896C7E8D3606F4217431B70610643B7"
BASE_EXE_SHA = "E899C67CB90B9C6B0F052E3F758BA8615BC2012E52561C2AF2E6A1E06EF61A2F"
BASE_CREDIT_LINE = (
    "Baldur's Gate 3 base game (Larian Studios) — retained installed-Data "
    "package hash snapshot base_game_profile_20260902"
)


def base_game_retained_capture_candidate(*, release_complete=True):
    """Census-shaped aggregate candidate anchored on retained Shared capture digests."""
    contract = {
        "schema": "clothmorph.source-profile",
        "schema_version": 1,
        "profile_id": BASE_GAME_SOURCE_PROFILE_UNRESOLVED,
        "module": {
            "pak_filename": "Shared.pak",
            "folder": "Shared",
            "name": "Shared",
            "uuid": BASE_SHARED_UUID,
            "version64": BASE_SHARED_VERSION,
            "pak_sha256": BASE_SHARED_PAK_SHA,
        },
        "content_manifest_sha256": BASE_SHARED_CONTENT_MANIFEST_SHA,
        "root_stats_visualbank_digest": BASE_EQUIPMENT_RACES_SHA,
        "required_dependencies": [],
        "forbidden_modules": [],
        "supported_body_tuples": [],
        "permission": {
            "state": "release_cleared",
            "evidence_sha256": BASE_TOP_LEVEL_MANIFEST_SHA,
            "credit_line": BASE_CREDIT_LINE,
            "distribution_limits": [],
        },
        "route_partition_digest": BASE_TOP_LEVEL_MANIFEST_SHA,
    }
    return {
        "discovery_profile_id": (
            f"DISCOVERY:BASE_GAME:{BASE_EXE_SHA}:{BASE_SHARED_PAK_SHA}"
        ),
        "release_profile_complete": release_complete,
        "admissible_contract": None,
        "blockers": [] if release_complete else ["BASE_GAME_CAPTURE_INCOMPLETE"],
        "contract": contract,
        "observed_creation_paths_digest": BASE_TOP_LEVEL_MANIFEST_SHA,
        "role": "base_game_aggregate",
        "retained_capture_evidence": {
            "top_level_package_hash_manifest_sha256": BASE_TOP_LEVEL_MANIFEST_SHA,
            "shared_content_manifest_sha256": BASE_SHARED_CONTENT_MANIFEST_SHA,
            "shared_equipment_races_sha256": BASE_EQUIPMENT_RACES_SHA,
        },
    }


def test_base_game_retained_capture_completes_aggregate_profile(tmp_path):
    """BASE_GAME closes from retained capture digests without inventing a mod package freeze.

    profile_id stays BASE_GAME_SOURCE_PROFILE_UNRESOLVED; Shared uuid/version must not
    inflate required as SOURCE_PROFILE:Shared:.... Freeze-bound completeness reuses the
    census release_profile_complete path.
    """
    census = verified_json(
        tmp_path, "base_game_aggregate_census", "SUPPORTING_EVIDENCE",
        [base_game_retained_capture_candidate(release_complete=True)],
    )

    inventories = extract_independent_inventories([census])

    shared_profile = f"SOURCE_PROFILE:{BASE_SHARED_UUID}:{BASE_SHARED_VERSION}"
    assert inventories.required_source_profiles == frozenset({BASE_GAME_SOURCE_PROFILE_UNRESOLVED})
    assert shared_profile not in inventories.required_source_profiles
    assert inventories.complete_source_profiles == frozenset({BASE_GAME_SOURCE_PROFILE_UNRESOLVED})
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.freeze_bound_source_profiles
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED not in inventories.freeze_missing_source_profiles
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED not in inventories.census_incomplete_source_profiles
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED not in inventories.missing_source_profiles


def test_base_game_retained_capture_incomplete_without_release_complete(tmp_path):
    census = verified_json(
        tmp_path, "base_game_aggregate_census", "SUPPORTING_EVIDENCE",
        [base_game_retained_capture_candidate(release_complete=False)],
    )

    inventories = extract_independent_inventories([census])

    assert inventories.complete_source_profiles == frozenset()
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.freeze_bound_source_profiles
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.census_incomplete_source_profiles
    assert BASE_GAME_SOURCE_PROFILE_UNRESOLVED in inventories.missing_source_profiles


# --- BCB core trio freeze-promote (Spike #2 bound) ---
# Package identities: census local core_source_freeze_20260902_retry1/packages
# (sha256+bytes verified). BCBPak and BCBUniqueTav are body-path XOR / mutually
# exclusive installs (not additive dual-body). All garments in each pak are
# in-scope (no forced 200-item cap). Imports/SindaeTexturePak remain freeze-missing.

BCB_PAK_UUID = "1d24059d-ff23-4a79-8892-57c85d512416"
BCB_PAK_VERSION = "36028797018963968"
BCB_PAK_SHA = "ABB53996163B64C7621CDB3C809E71B3248F60BE8FFC6240C632A005C0F55D1E"
BCB_PAK_PROFILE = f"SOURCE_PROFILE:{BCB_PAK_UUID}:{BCB_PAK_VERSION}"

BCB_UT_UUID = "28c82588-4ad0-4907-afac-6567817c6b13"
BCB_UT_VERSION = "36028797018963968"
BCB_UT_SHA = "0E08D6D8949CA779DC7C53C09356C914069E71B6EC645C77C0959D1972CA9AC5"
BCB_UT_PROFILE = f"SOURCE_PROFILE:{BCB_UT_UUID}:{BCB_UT_VERSION}"

BCB_SC_UUID = "75934b95-f697-4d5b-890c-fe198b799484"
BCB_SC_VERSION = "36028797018963968"
BCB_SC_SHA = "6BF0EB3F9AD7920BD35DD5BF52218873DB4F1C22CBFBCD73089D3614F3D154BA"
BCB_SC_PROFILE = f"SOURCE_PROFILE:{BCB_SC_UUID}:{BCB_SC_VERSION}"

BCB_EVIDENCE_WHERE = (
    "ChatGPT Work Files/Nexus Permission Evidence Review 2026-07-11.md "
    "(Alan authenticated Nexus session 2026-07-11; Beautiful Curvy Body and Sexy Outfits, "
    "https://www.nexusmods.com/baldursgate3/mods/2351; private conversation "
    "Permission Request - for using BCB in a selectable bodytype and clothing/armor morphing mod)"
)
BCB_EVIDENCE_WHEN = "2026-07-11"
BCB_SINDAE_QUOTE = "I would like my mod to be a requirement rather than bundling it with your mod."
BCB_PUBLIC_SUMMARY = (
    "The public page permits modification and asset use with credit, permits Donation Points, "
    "prohibits use in sold mods, and prohibits uploading the original file to other sites."
)


def bcb_census_candidate(folder, name, uuid, version64, pak_sha, pak_filename, content_sha, root_sha, route_sha):
    return {
        "discovery_profile_id": f"DISCOVERY:{uuid}:{version64}:{pak_sha}",
        "release_profile_complete": False,
        "admissible_contract": None,
        "blockers": ["PERMISSION_EVIDENCE_MISSING", "BODY_TUPLE_UNRESOLVED"],
        "observed_creation_paths_digest": route_sha,
        "contract": {
            "schema": "clothmorph.source-profile",
            "schema_version": 1,
            "profile_id": None,
            "module": {
                "pak_filename": pak_filename,
                "folder": folder,
                "name": name,
                "uuid": uuid,
                "version64": version64,
                "pak_sha256": pak_sha,
            },
            "content_manifest_sha256": content_sha,
            "root_stats_visualbank_digest": root_sha,
            "required_dependencies": [],
            "forbidden_modules": None,
            "supported_body_tuples": None,
            "permission": {
                "state": None,
                "evidence_sha256": None,
                "credit_line": None,
                "distribution_limits": None,
            },
            "route_partition_digest": None,
        },
    }


def bcb_permission_record(uuid, name, pak_filename, pak_sha, credit_line, *, xor_note=False):
    quote = (
        BCB_PUBLIC_SUMMARY
        + " Sindae replied on 2026-06-21 and approved the proposal. "
        + "The controlling distribution condition was: "
        + repr(BCB_SINDAE_QUOTE)
        + "."
    )
    if xor_note:
        quote += (
            " BCBUniqueTav is the alternate Unique Tav body path under the BCB/Sindae family: "
            "mutually exclusive (XOR) with BCBPak install, not additive dual-body; all garments "
            "in the UniqueTav pak remain in-scope (not a forced 200-item subset)."
        )
    evidence = {
        "where": BCB_EVIDENCE_WHERE,
        "when": BCB_EVIDENCE_WHEN,
        "quote": quote,
    }
    return {
        "mod_uuid": uuid,
        "mod_name": name,
        "source_pak": pak_filename,
        "pak_sha256": pak_sha.lower(),
        "scope_resolved": [],
        "decision": "process",
        "evidence": evidence,
        "flag": {
            "mod_uuid": uuid,
            "permission": "granted",
            "credit_line": credit_line,
            "exclude": [],
            "bodies": ["*"],
            "items": "*",
            "evidence": evidence,
        },
    }


def test_bcb_core_trio_freeze_permission_joins_complete_profiles(tmp_path):
    """Each BCB core package freeze-binds and completes via permission join.

    Contracts use real freeze UUID/version64/pak sha from census core freeze.
    """
    candidates = [
        bcb_census_candidate(
            "BCBPak", "BCBPak", BCB_PAK_UUID, BCB_PAK_VERSION, BCB_PAK_SHA, "BCBPak.pak",
            "5A8C9D3678E63085C3F34AE7C675F4A9A7D1CD96648C6BDF21F5D6CE307DA3BE",
            "4FBCA506D40D0E8C088E46125E34A578C84E53954D95FCC27953921708246C43",
            "D0566274B31E113206E05673A5AB43C653B4EAF88F9EC216747078F1D49C9BC4",
        ),
        bcb_census_candidate(
            "BCBUniqueTav", "BCBUniqueTav", BCB_UT_UUID, BCB_UT_VERSION, BCB_UT_SHA, "BCBUniqueTav.pak",
            "49F28E50AD5B35DF446CCC8B5093088555238F27EB181F4DAD56430ADAC3398A",
            "A5099076E40B79FD8D8E4EC4FDF39137CC5546BF61BEA9D4FF7C435AAABA14C6",
            "38C1A1FDE633F919EB47BB5988996D1B4413E15647B0E9E97058A579051C1FE7",
        ),
        bcb_census_candidate(
            "BCBScantily", "BCBScantily", BCB_SC_UUID, BCB_SC_VERSION, BCB_SC_SHA, "BCBScantily.pak",
            "49BB0EBD3BE6D43A72E41172BA6F05F17C4490FDB4C821F13D60F2EA16D537FC",
            "2FEF23CCB87AB7FA87A61F7688A3C9DA61705417AB465B067C7D0DAFAC1576A2",
            "809810D89B492C6FC4B7E7DC287390D8C3EBBB9932DA8917E3DBAB6F5A33FFB8",
        ),
    ]
    records = [
        bcb_permission_record(
            BCB_PAK_UUID, "BCBPak", "BCBPak.pak", BCB_PAK_SHA,
            "Beautiful Curvy Body (BCBPak) by Sindae (Nexus mod 2351)",
        ),
        bcb_permission_record(
            BCB_UT_UUID, "BCBUniqueTav", "BCBUniqueTav.pak", BCB_UT_SHA,
            "BCB Unique Tav by Sindae (Nexus mod 2351 family; body-path XOR vs BCBPak)",
            xor_note=True,
        ),
        bcb_permission_record(
            BCB_SC_UUID, "BCBScantily", "BCBScantily.pak", BCB_SC_SHA,
            "BCB Scantily Clad Camp Outfits by Sindae (Nexus mod 2351)",
        ),
    ]
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE", candidates,
    )
    permission = verified_json(
        tmp_path, "permission", "PERMISSION", permission_records(*records),
    )

    inventories = extract_independent_inventories([census, permission])

    expected = frozenset({BCB_PAK_PROFILE, BCB_UT_PROFILE, BCB_SC_PROFILE})
    assert inventories.freeze_bound_source_profiles == expected
    assert inventories.complete_source_profiles == expected
    assert inventories.census_incomplete_source_profiles == frozenset()
    assert inventories.source_observations == frozenset()  # empty scope_resolved; no invented meshes


def test_bcbpak_unique_tav_body_path_xor_is_documented_in_permission_evidence(tmp_path):
    """UniqueTav permission evidence records mutual exclusivity vs BCBPak.

    Both may be freeze-bound/complete as alternate body-path profiles; install is XOR.
    """
    record = bcb_permission_record(
        BCB_UT_UUID, "BCBUniqueTav", "BCBUniqueTav.pak", BCB_UT_SHA,
        "BCB Unique Tav by Sindae (Nexus mod 2351 family; body-path XOR vs BCBPak)",
        xor_note=True,
    )
    quote = record["evidence"]["quote"]
    assert "mutually exclusive (XOR) with BCBPak" in quote
    assert "not additive dual-body" in quote
    assert "not a forced 200-item subset" in quote
    assert BCB_SINDAE_QUOTE in quote
    assert "body-path XOR vs BCBPak" in record["flag"]["credit_line"]

    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [
            bcb_census_candidate(
                "BCBPak", "BCBPak", BCB_PAK_UUID, BCB_PAK_VERSION, BCB_PAK_SHA, "BCBPak.pak",
                "5A8C9D3678E63085C3F34AE7C675F4A9A7D1CD96648C6BDF21F5D6CE307DA3BE",
                "4FBCA506D40D0E8C088E46125E34A578C84E53954D95FCC27953921708246C43",
                "D0566274B31E113206E05673A5AB43C653B4EAF88F9EC216747078F1D49C9BC4",
            ),
            bcb_census_candidate(
                "BCBUniqueTav", "BCBUniqueTav", BCB_UT_UUID, BCB_UT_VERSION, BCB_UT_SHA, "BCBUniqueTav.pak",
                "49F28E50AD5B35DF446CCC8B5093088555238F27EB181F4DAD56430ADAC3398A",
                "A5099076E40B79FD8D8E4EC4FDF39137CC5546BF61BEA9D4FF7C435AAABA14C6",
                "38C1A1FDE633F919EB47BB5988996D1B4413E15647B0E9E97058A579051C1FE7",
            ),
        ],
    )
    permission = verified_json(
        tmp_path, "permission", "PERMISSION",
        permission_records(
            bcb_permission_record(
                BCB_PAK_UUID, "BCBPak", "BCBPak.pak", BCB_PAK_SHA,
                "Beautiful Curvy Body (BCBPak) by Sindae (Nexus mod 2351)",
            ),
            record,
        ),
    )
    inventories = extract_independent_inventories([census, permission])
    # Both complete as alternate profiles; XOR is install-time mutual exclusivity, not ledger exclusion.
    assert inventories.complete_source_profiles == frozenset({BCB_PAK_PROFILE, BCB_UT_PROFILE})
    assert inventories.freeze_bound_source_profiles == frozenset({BCB_PAK_PROFILE, BCB_UT_PROFILE})


def test_bcb_permission_pak_mismatch_does_not_complete(tmp_path):
    census = verified_json(
        tmp_path, "source_profile_census_candidates", "SUPPORTING_EVIDENCE",
        [
            bcb_census_candidate(
                "BCBPak", "BCBPak", BCB_PAK_UUID, BCB_PAK_VERSION, BCB_PAK_SHA, "BCBPak.pak",
                "5A8C9D3678E63085C3F34AE7C675F4A9A7D1CD96648C6BDF21F5D6CE307DA3BE",
                "4FBCA506D40D0E8C088E46125E34A578C84E53954D95FCC27953921708246C43",
                "D0566274B31E113206E05673A5AB43C653B4EAF88F9EC216747078F1D49C9BC4",
            ),
        ],
    )
    bad = bcb_permission_record(
        BCB_PAK_UUID, "BCBPak", "BCBPak.pak", BCB_PAK_SHA,
        "Beautiful Curvy Body (BCBPak) by Sindae (Nexus mod 2351)",
    )
    bad["pak_sha256"] = "0" * 64
    permission = verified_json(
        tmp_path, "permission", "PERMISSION", permission_records(bad),
    )
    inventories = extract_independent_inventories([census, permission])
    assert inventories.complete_source_profiles == frozenset()
    assert BCB_PAK_PROFILE in inventories.freeze_bound_source_profiles
    assert BCB_PAK_PROFILE in inventories.census_incomplete_source_profiles


# --- Imports + SindaeTexturePak paired freeze-promote ---
# Package identities: census local core_source_freeze_20260902_retry1/packages
# SindaeImportedOutfits.pak / NightreignStylePak folder (096665c7..., sha F91C4F78...)
# SindaeTexturePak.pak (873d1b73..., sha 33BE5016...) — dependency-only / paired
# operational dep for Sindae garment sources, not a garment-source twin.
# Keep OUT: ClothMorph Runtime/BCB/SCO/External providers; Tiefling/Recluse/Underwear TEST.

IMPORTS_UUID = "096665c7-75aa-4747-9548-6ccafba985c8"
IMPORTS_VERSION = "36028797018963968"
IMPORTS_SHA = "F91C4F78BE6B543835EC90BCDC1F1C4D269F272237033263FC1FD8E414455BCA"
IMPORTS_PROFILE = f"SOURCE_PROFILE:{IMPORTS_UUID}:{IMPORTS_VERSION}"

TEXTURE_UUID = "873d1b73-6adf-4f0c-9e8f-51a78fc3d9c5"
TEXTURE_VERSION = "36028797018963968"
TEXTURE_SHA = "33BE501670368E7259EDFA0C74827A146B75403B6E34DB42CC3871FEFC877992"
TEXTURE_PROFILE = f"SOURCE_PROFILE:{TEXTURE_UUID}:{TEXTURE_VERSION}"

IMPORTS_EVIDENCE_WHERE = (
    "ChatGPT Work Files/Nexus Permission Evidence Review 2026-07-11.md "
    "(Alan authenticated Nexus session 2026-07-11; Sindae family mods including "
    "Imported Outfits Nexus 18009 / Texture Pak Nexus 9716; private conversation "
    "Permission Request - for using BCB in a selectable bodytype and clothing/armor morphing mod)"
)
IMPORTS_EVIDENCE_WHEN = "2026-07-11"
IMPORTS_SINDAE_QUOTE = "I would like my mod to be a requirement rather than bundling it with your mod."
IMPORTS_PUBLIC_SUMMARY = (
    "The public page permits modification and asset use with credit, permits Donation Points, "
    "prohibits use in sold mods, and prohibits uploading the original file to other sites. "
    "Sindae replied on 2026-06-21 and approved the proposal. The controlling distribution "
    f"condition was: {IMPORTS_SINDAE_QUOTE!r}."
)


def imports_census_candidate():
    return {
        "admissible_contract": None,
        "blockers": ["PERMISSION_EVIDENCE_MISSING"],
        "contract": {
            "content_manifest_sha256": "4468E0269566AFB83B6A42B3122DD7C74BF4C33553016F72FC3AFC0A4179F5EA",
            "forbidden_modules": None,
            "module": {
                "folder": "NightreignStylePak",
                "name": "SindaeImportedOutfits",
                "pak_filename": "SindaeImportedOutfits.pak",
                "pak_sha256": IMPORTS_SHA,
                "uuid": IMPORTS_UUID,
                "version64": IMPORTS_VERSION,
            },
            "permission": {
                "credit_line": None,
                "distribution_limits": None,
                "evidence_sha256": None,
                "state": None,
            },
            "profile_id": None,
            "required_dependencies": [TEXTURE_PROFILE],
            "root_stats_visualbank_digest": "2B2E980C2CB4B6EB28DF25BD516A916CC1256C373493406C177FBD2AEF736D5B",
            "route_partition_digest": None,
            "schema": "clothmorph.source-profile",
            "schema_version": 1,
            "supported_body_tuples": None,
        },
        "creation_coverage": {
            "census_without_source": [],
            "complete": True,
            "duplicate_census_rows": [],
            "duplicate_source_rows": [],
            "missing_from_census": [],
        },
        "creation_paths_complete": False,
        "definition_parse_complete": False,
        "discovery_profile_id": f"DISCOVERY:{IMPORTS_UUID}:{IMPORTS_VERSION}:{IMPORTS_SHA}",
        "observed_creation_paths_digest": "EF7AE042F1200237134014364C1FCCDAB4F3431040341B5C7E4029AED4A46F2F",
        "release_profile_complete": False,
        "role": "source",
        "supplied_contract": None,
        "supplied_contract_structurally_complete": False,
    }


def texture_census_candidate():
    return {
        "admissible_contract": None,
        "blockers": ["PERMISSION_EVIDENCE_MISSING"],
        "contract": {
            "content_manifest_sha256": "ACEEBF6478BFB1B6D7E76087855749BFA0F36862617F8B5497CB42E4670C2678",
            "forbidden_modules": None,
            "module": {
                "folder": "SindaeTexturePak",
                "name": "SindaeTexturePak",
                "pak_filename": "SindaeTexturePak.pak",
                "pak_sha256": TEXTURE_SHA,
                "uuid": TEXTURE_UUID,
                "version64": TEXTURE_VERSION,
            },
            "permission": {
                "credit_line": None,
                "distribution_limits": None,
                "evidence_sha256": None,
                "state": None,
            },
            "profile_id": None,
            "required_dependencies": [],
            "root_stats_visualbank_digest": "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
            "route_partition_digest": None,
            "schema": "clothmorph.source-profile",
            "schema_version": 1,
            "supported_body_tuples": None,
        },
        "creation_coverage": {
            "census_without_source": [],
            "complete": True,
            "duplicate_census_rows": [],
            "duplicate_source_rows": [],
            "missing_from_census": [],
        },
        "creation_paths_complete": False,
        "definition_parse_complete": False,
        "discovery_profile_id": f"DISCOVERY:{TEXTURE_UUID}:{TEXTURE_VERSION}:{TEXTURE_SHA}",
        "observed_creation_paths_digest": "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
        "release_profile_complete": False,
        "role": "dependency",
        "supplied_contract": None,
        "supplied_contract_structurally_complete": False,
    }


def imports_permission_record():
    quote = (
        IMPORTS_PUBLIC_SUMMARY
        + " Sindae Imported Outfits / NightreignStylePak is a garment-source freeze profile "
        + "paired with SindaeTexturePak as an operational dependency (not a body-path XOR)."
    )
    return {
        "mod_uuid": IMPORTS_UUID,
        "mod_name": "SindaeImportedOutfits",
        "source_pak": "SindaeImportedOutfits.pak",
        "pak_sha256": IMPORTS_SHA.lower(),
        "flag_sha256": None,
        "flag": {
            "mod_uuid": IMPORTS_UUID,
            "spec_version": 1,
            "permission": "granted",
            "bodies": ["*"],
            "items": "*",
            "exclude": [],
            "mod_version": "as-shipped",
            "credit_line": (
                "Sindae Imported Outfits (NightreignStylePak) by Sindae "
                "(Nexus mod 18009; paired with Texture Pak 9716)"
            ),
            "permission_statement": (
                "Sindae family public terms authorize modification and asset use with credit; "
                "Donation Points allowed; sold-mod use and re-upload of the original file prohibited. "
                "Sindae 2026-06-21 project-specific reply approved selectable-body/clothing morph use "
                "with the controlling condition quoted in evidence. ClothMorph must keep Sindae "
                "packages as required dependencies and must not bundle Sindae-origin assets."
            ),
            "url": "https://www.nexusmods.com/baldursgate3/mods/18009",
            "evidence": {
                "where": IMPORTS_EVIDENCE_WHERE,
                "when": IMPORTS_EVIDENCE_WHEN,
                "quote": quote,
            },
        },
        "evidence": {
            "where": IMPORTS_EVIDENCE_WHERE,
            "when": IMPORTS_EVIDENCE_WHEN,
            "quote": quote,
        },
        "source": "override",
        "scope_resolved": [],
        "unresolvable": [],
        "per_body_decisions": {"sbbf": "process", "bcb": "process"},
        "mesh_hashes": {},
        "scanned": "2026-09-03T00:00:00+00:00",
        "decision": "process",
        "reason": "Imports freeze-promote; garment-source twin to dependency-only SindaeTexturePak",
    }


def texture_permission_record():
    quote = (
        IMPORTS_PUBLIC_SUMMARY
        + " SindaeTexturePak is dependency-only / a paired operational dependency for "
        + "Sindae garment sources (including Imported Outfits / NightreignStylePak): it is "
        + "not a garment-source twin and does not invent meshes or authored outfit rows."
    )
    return {
        "mod_uuid": TEXTURE_UUID,
        "mod_name": "SindaeTexturePak",
        "source_pak": "SindaeTexturePak.pak",
        "pak_sha256": TEXTURE_SHA.lower(),
        "flag_sha256": None,
        "flag": {
            "mod_uuid": TEXTURE_UUID,
            "spec_version": 1,
            "permission": "granted",
            "bodies": ["*"],
            "items": "*",
            "exclude": [],
            "mod_version": "as-shipped",
            "credit_line": (
                "Sindae Texture Pak by Sindae (Nexus mod 9716; dependency-only / "
                "paired operational dep, not garment-source twin)"
            ),
            "permission_statement": (
                "Sindae family public terms authorize modification and asset use with credit; "
                "Donation Points allowed; sold-mod use and re-upload of the original file prohibited. "
                "Sindae 2026-06-21 project-specific reply approved selectable-body/clothing morph use "
                "with the controlling condition quoted in evidence. ClothMorph must keep Sindae "
                "packages as required dependencies and must not bundle Sindae-origin assets. "
                "SindaeTexturePak remains dependency-only (textures for Sindae mods), not a "
                "garment-source twin of Imported Outfits."
            ),
            "url": "https://www.nexusmods.com/baldursgate3/mods/9716",
            "evidence": {
                "where": IMPORTS_EVIDENCE_WHERE,
                "when": IMPORTS_EVIDENCE_WHEN,
                "quote": quote,
            },
        },
        "evidence": {
            "where": IMPORTS_EVIDENCE_WHERE,
            "when": IMPORTS_EVIDENCE_WHEN,
            "quote": quote,
        },
        "source": "override",
        "scope_resolved": [],
        "unresolvable": [],
        "per_body_decisions": {"sbbf": "process", "bcb": "process"},
        "mesh_hashes": {},
        "scanned": "2026-09-03T00:00:00+00:00",
        "decision": "process",
        "reason": (
            "SindaeTexturePak freeze-promote; dependency-only / paired operational dep "
            "for Imports and other Sindae garment sources; not garment-source twin"
        ),
    }


def test_imports_and_texture_freeze_permission_joins_complete_profiles(tmp_path):
    """Imports + SindaeTexturePak freeze-bind and complete via permission join."""
    census = verified_json(
        tmp_path,
        "source_profile_census_candidates",
        "SUPPORTING_EVIDENCE",
        [imports_census_candidate(), texture_census_candidate()],
    )
    permission = verified_json(
        tmp_path,
        "external_permission_manifest_v1",
        "PERMISSION",
        {"records": [imports_permission_record(), texture_permission_record()]},
    )
    inventories = extract_independent_inventories([census, permission])
    expected = frozenset({IMPORTS_PROFILE, TEXTURE_PROFILE})
    assert inventories.freeze_bound_source_profiles == expected
    assert inventories.complete_source_profiles == expected
    assert inventories.freeze_missing_source_profiles == frozenset({BASE_GAME_SOURCE_PROFILE_UNRESOLVED})
    assert IMPORTS_PROFILE not in inventories.census_incomplete_source_profiles
    assert TEXTURE_PROFILE not in inventories.census_incomplete_source_profiles


def test_sindaetexturepak_dependency_only_semantics_documented(tmp_path):
    """SindaeTexturePak role stays dependency-only; permission evidence says so."""
    cand = texture_census_candidate()
    assert cand["role"] == "dependency"
    record = texture_permission_record()
    quote = record["flag"]["evidence"]["quote"]
    assert "dependency-only" in quote
    assert "not a garment-source twin" in quote
    assert "dependency-only" in record["flag"]["credit_line"]
    assert IMPORTS_SINDAE_QUOTE in quote

    census = verified_json(
        tmp_path,
        "source_profile_census_candidates",
        "SUPPORTING_EVIDENCE",
        [imports_census_candidate(), cand],
    )
    permission = verified_json(
        tmp_path,
        "external_permission_manifest_v1",
        "PERMISSION",
        {"records": [imports_permission_record(), record]},
    )
    inventories = extract_independent_inventories([census, permission])
    assert TEXTURE_PROFILE in inventories.complete_source_profiles
    assert IMPORTS_PROFILE in inventories.complete_source_profiles
    # Imports declares TexturePak as required operational dependency in freeze contract.
    assert TEXTURE_PROFILE in imports_census_candidate()["contract"]["required_dependencies"]


def test_imports_texture_permission_pak_mismatch_does_not_complete(tmp_path):
    census = verified_json(
        tmp_path,
        "source_profile_census_candidates",
        "SUPPORTING_EVIDENCE",
        [imports_census_candidate(), texture_census_candidate()],
    )
    bad = imports_permission_record()
    bad["pak_sha256"] = "0" * 64
    permission = verified_json(
        tmp_path,
        "external_permission_manifest_v1",
        "PERMISSION",
        {"records": [bad, texture_permission_record()]},
    )
    inventories = extract_independent_inventories([census, permission])
    assert IMPORTS_PROFILE in inventories.freeze_bound_source_profiles
    assert IMPORTS_PROFILE in inventories.census_incomplete_source_profiles
    assert TEXTURE_PROFILE in inventories.complete_source_profiles

# --- ClothMorph provider freeze-promote (Spike #2 bound) ---
# Package identities from ChatGPT Work Files/BCB_Save_Uninstall_Safety_Audit_20260830/
# evidence/physical_pak_and_profile_inventory.json + retained evidence PAKs:
# Runtime 20aca985... sha 6610090C... (retained TieflingBT1 TEST output; live-matched)
# ClothMorphBCB 78f1571f... sha 9E315B49... (ClothMorph_Build _SHIP_v1.3)
# ClothMorphSCO 0d73fe2f... sha EBFFBA8D... (ABCD DrowDruid proof; live-matched)
# ClothMorphExternal fdb658be... sha 72535634... (OptionA W08 proof; live-matched)
# Roles: Runtime=runtime; BCB/SCO/External=provider (refit-map / presence-gated providers;
# not garment-source twins; do not invent meshes). OUT: Tiefling/Recluse/Underwear TEST.

CM_RUNTIME_UUID = "20aca985-e3e9-41d7-bf8f-10f2a3c413e4"
CM_RUNTIME_VERSION = "36451009484029952"
CM_RUNTIME_SHA = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6"
CM_RUNTIME_PROFILE = f"SOURCE_PROFILE:{CM_RUNTIME_UUID}:{CM_RUNTIME_VERSION}"

CM_BCB_UUID = "78f1571f-ffb5-5646-8a5b-63aac7ce2ecd"
CM_BCB_VERSION = "36028797018963968"
CM_BCB_SHA = "9E315B49F54F29B278313E974198674ACC951E55A7BC0C81BB05B800B1E91062"
CM_BCB_PROFILE = f"SOURCE_PROFILE:{CM_BCB_UUID}:{CM_BCB_VERSION}"

CM_SCO_UUID = "0d73fe2f-49ae-528e-9a9b-160e7f124afc"
CM_SCO_VERSION = "36451009484029952"
CM_SCO_SHA = "EBFFBA8DEDAF1AB75D1D472E0D1D02AA50491B2ACE70DF445A8096A505F9D262"
CM_SCO_PROFILE = f"SOURCE_PROFILE:{CM_SCO_UUID}:{CM_SCO_VERSION}"

CM_EXT_UUID = "fdb658be-223c-55c8-a12f-3542a9c6e2fb"
CM_EXT_VERSION = "36169534507384832"
CM_EXT_SHA = "725356348C8B83C20D211C6D064FFAE3B04F1E799C10D92683621A85047B7B5E"
CM_EXT_PROFILE = f"SOURCE_PROFILE:{CM_EXT_UUID}:{CM_EXT_VERSION}"

# Digests filled from provider freeze census after capture (real sha256 hex).
CM_DIGEST_CONTENT = {
    CM_RUNTIME_UUID: "72212848FA9CA0DA209E0DAE24BDF535F997FF08C95C947F7E72A9D0C21A05B7",
    CM_BCB_UUID: "3D24A3413D41AC14CE744E127A41790FABFE126536E7C195CF46042A0460A8AA",
    CM_SCO_UUID: "7CC9932214CF1CB828902D7BF5CAD6BAFE9ECD5B757D78780484CCE688F0EE3B",
    CM_EXT_UUID: "A10405C499E7E33CD20B4ABC42AE089C9AF2DE608BE2C87E4749EA73DDCCC562",
}
CM_DIGEST_ROOT = {
    CM_RUNTIME_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
    CM_BCB_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
    CM_SCO_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
    CM_EXT_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
}
CM_DIGEST_ROUTE = {
    CM_RUNTIME_UUID: "ADD58EC857CA8983443C89917F41DEA74E18C9EF6C55AE9C6576056EEB5B4974",
    CM_BCB_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
    CM_SCO_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
    CM_EXT_UUID: "37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570",
}

CM_EVIDENCE_WHERE = (
    "ChatGPT Work Files/BCB_Save_Uninstall_Safety_Audit_20260830/evidence/"
    "physical_pak_and_profile_inventory.json "
    "(retained first-party ClothMorph provider package identities; public author SerpentineShel)"
)
CM_EVIDENCE_WHEN = "2026-08-30"


def cm_provider_census_candidate(folder, name, uuid, version64, pak_sha, pak_filename, role):
    return {
        "admissible_contract": None,
        "blockers": ["PERMISSION_EVIDENCE_MISSING"],
        "contract": {
            "content_manifest_sha256": CM_DIGEST_CONTENT[uuid],
            "forbidden_modules": None,
            "module": {
                "folder": folder,
                "name": name,
                "pak_filename": pak_filename,
                "pak_sha256": pak_sha,
                "uuid": uuid,
                "version64": version64,
            },
            "permission": {
                "credit_line": None,
                "distribution_limits": None,
                "evidence_sha256": None,
                "state": None,
            },
            "profile_id": None,
            "required_dependencies": [],
            "root_stats_visualbank_digest": CM_DIGEST_ROOT[uuid],
            "route_partition_digest": None,
            "schema": "clothmorph.source-profile",
            "schema_version": 1,
            "supported_body_tuples": None,
        },
        "creation_coverage": {
            "census_without_source": [],
            "complete": True,
            "duplicate_census_rows": [],
            "duplicate_source_rows": [],
            "missing_from_census": [],
        },
        "creation_paths_complete": False,
        "definition_parse_complete": False,
        "discovery_profile_id": f"DISCOVERY:{uuid}:{version64}:{pak_sha}",
        "observed_creation_paths_digest": CM_DIGEST_ROUTE[uuid],
        "release_profile_complete": False,
        "role": role,
        "supplied_contract": None,
        "supplied_contract_structurally_complete": False,
    }


def cm_runtime_candidate():
    return cm_provider_census_candidate(
        "ClothMorphRuntime",
        "Body and Clothing Morph",
        CM_RUNTIME_UUID,
        CM_RUNTIME_VERSION,
        CM_RUNTIME_SHA,
        "ClothMorphRuntime.pak",
        "runtime",
    )


def cm_bcb_candidate():
    return cm_provider_census_candidate(
        "ClothMorphBCB",
        "Clothing Morph - BCB Add-on",
        CM_BCB_UUID,
        CM_BCB_VERSION,
        CM_BCB_SHA,
        "ClothMorphBCB.pak",
        "provider",
    )


def cm_sco_provider_candidate():
    return cm_provider_census_candidate(
        "ClothMorphSCO",
        "Clothing Morph - SCO Add-on",
        CM_SCO_UUID,
        CM_SCO_VERSION,
        CM_SCO_SHA,
        "ClothMorphSCO.pak",
        "provider",
    )


def cm_external_candidate():
    return cm_provider_census_candidate(
        "ClothMorphExternal",
        "Clothing Morph - External Garments",
        CM_EXT_UUID,
        CM_EXT_VERSION,
        CM_EXT_SHA,
        "ClothMorphExternal.pak",
        "provider",
    )


def cm_provider_permission_record(uuid, name, pak_filename, pak_sha, credit_line, role_note):
    quote = (
        f"First-party ClothMorph package {pak_filename} (uuid {uuid}, sha256 {pak_sha}) "
        f"authored by SerpentineShel. {role_note} Freeze-promote closes the required "
        "source-profile identity from retained evidence PAK bytes matching the Aug 30 "
        "physical inventory; no live Mods mutation; no mesh invention; not a garment-source twin."
    )
    return {
        "mod_uuid": uuid,
        "mod_name": name,
        "source_pak": pak_filename,
        "pak_sha256": pak_sha.lower(),
        "flag_sha256": None,
        "flag": {
            "mod_uuid": uuid,
            "spec_version": 1,
            "permission": "granted",
            "bodies": ["*"],
            "items": "*",
            "exclude": [],
            "mod_version": "as-shipped",
            "credit_line": credit_line,
            "permission_statement": (
                "First-party ClothMorph provider/runtime package by SerpentineShel. "
                "Authorized for ClothMorph release freeze-binding as its declared role. "
                "Not a third-party garment source; do not invent meshes."
            ),
            "url": "https://www.nexusmods.com/baldursgate3/mods/users/SerpentineShel",
            "evidence": {"where": CM_EVIDENCE_WHERE, "when": CM_EVIDENCE_WHEN, "quote": quote},
        },
        "evidence": {"where": CM_EVIDENCE_WHERE, "when": CM_EVIDENCE_WHEN, "quote": quote},
        "source": "override",
        "scope_resolved": [],
        "unresolvable": [],
        "per_body_decisions": {"sbbf": "process", "bcb": "process"},
        "mesh_hashes": {},
        "scanned": "2026-09-03T00:00:00+00:00",
        "decision": "process",
        "reason": f"ClothMorph freeze-promote; first-party SerpentineShel; {role_note}",
    }


def test_clothmorph_providers_freeze_permission_joins_complete_profiles(tmp_path):
    """Four ClothMorph provider/runtime packages freeze-bind and complete via permission join."""
    candidates = [
        cm_runtime_candidate(),
        cm_bcb_candidate(),
        cm_sco_provider_candidate(),
        cm_external_candidate(),
    ]
    assert candidates[0]["role"] == "runtime"
    assert all(c["role"] == "provider" for c in candidates[1:])
    records = [
        cm_provider_permission_record(
            CM_RUNTIME_UUID,
            "Body and Clothing Morph",
            "ClothMorphRuntime.pak",
            CM_RUNTIME_SHA,
            "Body and Clothing Morph (ClothMorphRuntime) by SerpentineShel (first-party ClothMorph runtime)",
            "Role: runtime. Persistent body-choice and EquipmentRace Runtime; not a garment-source twin.",
        ),
        cm_provider_permission_record(
            CM_BCB_UUID,
            "Clothing Morph - BCB Add-on",
            "ClothMorphBCB.pak",
            CM_BCB_SHA,
            "Clothing Morph - BCB Add-on (ClothMorphBCB) by SerpentineShel (first-party ClothMorph BCB provider)",
            "Role: provider. Session-only BCB refit-map provider; not a garment-source twin; does not invent meshes.",
        ),
        cm_provider_permission_record(
            CM_SCO_UUID,
            "Clothing Morph - SCO Add-on",
            "ClothMorphSCO.pak",
            CM_SCO_SHA,
            "Clothing Morph - SCO Add-on (ClothMorphSCO) by SerpentineShel (first-party ClothMorph SCO provider)",
            "Role: provider. SCO refit-map provider; not a garment-source twin; does not invent meshes.",
        ),
        cm_provider_permission_record(
            CM_EXT_UUID,
            "Clothing Morph - External Garments",
            "ClothMorphExternal.pak",
            CM_EXT_SHA,
            "Clothing Morph - External Garments (ClothMorphExternal) by SerpentineShel (first-party ClothMorph external provider)",
            "Role: provider. Presence-gated external-garment refit provider; not a garment-source twin; does not invent meshes.",
        ),
    ]
    census = verified_json(
        tmp_path,
        "source_profile_census_candidates",
        "SUPPORTING_EVIDENCE",
        candidates,
    )
    permission = verified_json(
        tmp_path,
        "external_permission_manifest_v1",
        "PERMISSION",
        {"records": records},
    )
    inventories = extract_independent_inventories([census, permission])
    expected = frozenset({CM_RUNTIME_PROFILE, CM_BCB_PROFILE, CM_SCO_PROFILE, CM_EXT_PROFILE})
    assert inventories.freeze_bound_source_profiles == expected
    assert inventories.complete_source_profiles == expected
    assert inventories.freeze_missing_source_profiles == frozenset({BASE_GAME_SOURCE_PROFILE_UNRESOLVED})
    assert not (expected & inventories.census_incomplete_source_profiles)


def test_clothmorph_provider_roles_documented(tmp_path):
    """Runtime vs provider roles stay honest; permission evidence names SerpentineShel."""
    assert cm_runtime_candidate()["role"] == "runtime"
    assert cm_bcb_candidate()["role"] == "provider"
    assert cm_sco_provider_candidate()["role"] == "provider"
    assert cm_external_candidate()["role"] == "provider"
    rec = cm_provider_permission_record(
        CM_BCB_UUID,
        "Clothing Morph - BCB Add-on",
        "ClothMorphBCB.pak",
        CM_BCB_SHA,
        "Clothing Morph - BCB Add-on (ClothMorphBCB) by SerpentineShel (first-party ClothMorph BCB provider)",
        "Role: provider. Session-only BCB refit-map provider; not a garment-source twin; does not invent meshes.",
    )
    assert "SerpentineShel" in rec["flag"]["credit_line"]
    assert "Alan Scheiner" not in rec["flag"]["credit_line"]
    assert "not a garment-source twin" in rec["flag"]["evidence"]["quote"]


def test_clothmorph_provider_permission_pak_mismatch_does_not_complete(tmp_path):
    census = verified_json(
        tmp_path,
        "source_profile_census_candidates",
        "SUPPORTING_EVIDENCE",
        [cm_runtime_candidate(), cm_bcb_candidate(), cm_sco_provider_candidate(), cm_external_candidate()],
    )
    bad = cm_provider_permission_record(
        CM_RUNTIME_UUID,
        "Body and Clothing Morph",
        "ClothMorphRuntime.pak",
        CM_RUNTIME_SHA,
        "Body and Clothing Morph (ClothMorphRuntime) by SerpentineShel (first-party ClothMorph runtime)",
        "Role: runtime. Persistent body-choice and EquipmentRace Runtime; not a garment-source twin.",
    )
    bad["pak_sha256"] = "0" * 64
    good = [
        cm_provider_permission_record(
            CM_BCB_UUID,
            "Clothing Morph - BCB Add-on",
            "ClothMorphBCB.pak",
            CM_BCB_SHA,
            "Clothing Morph - BCB Add-on (ClothMorphBCB) by SerpentineShel (first-party ClothMorph BCB provider)",
            "Role: provider. Session-only BCB refit-map provider; not a garment-source twin; does not invent meshes.",
        ),
        cm_provider_permission_record(
            CM_SCO_UUID,
            "Clothing Morph - SCO Add-on",
            "ClothMorphSCO.pak",
            CM_SCO_SHA,
            "Clothing Morph - SCO Add-on (ClothMorphSCO) by SerpentineShel (first-party ClothMorph SCO provider)",
            "Role: provider. SCO refit-map provider; not a garment-source twin; does not invent meshes.",
        ),
        cm_provider_permission_record(
            CM_EXT_UUID,
            "Clothing Morph - External Garments",
            "ClothMorphExternal.pak",
            CM_EXT_SHA,
            "Clothing Morph - External Garments (ClothMorphExternal) by SerpentineShel (first-party ClothMorph external provider)",
            "Role: provider. Presence-gated external-garment refit provider; not a garment-source twin; does not invent meshes.",
        ),
    ]
    permission = verified_json(
        tmp_path,
        "external_permission_manifest_v1",
        "PERMISSION",
        {"records": [bad, *good]},
    )
    inventories = extract_independent_inventories([census, permission])
    assert CM_RUNTIME_PROFILE in inventories.freeze_bound_source_profiles
    assert CM_RUNTIME_PROFILE in inventories.census_incomplete_source_profiles
    assert CM_BCB_PROFILE in inventories.complete_source_profiles
    assert CM_SCO_PROFILE in inventories.complete_source_profiles
    assert CM_EXT_PROFILE in inventories.complete_source_profiles

