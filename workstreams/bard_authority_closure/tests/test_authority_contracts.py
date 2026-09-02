from dataclasses import replace
import json
from pathlib import Path

import pytest
from workstreams.bard_authority_closure import authority_contracts as authority_module

from workstreams.bard_authority_closure.authority_contracts import (
    ALT_ITEM_UUID,
    NORMAL_ITEM_UUID,
    REQUIRED_AUDIT_SCOPES,
    SKIRT_ITEM_UUID,
    TERMINAL_UNRESOLVED_REASON,
    AuthorityAuditEvidence,
    AuthorityComponentReference,
    AuthorityRouteReference,
    AuthoritySourceSnapshot,
    ContractAdmissionError,
    build_current_authority_resolution,
    canonical_exclusion_event_input,
    load_current_authority_snapshot,
    resolve_authority_contract,
    write_current_authority_exclusion_input,
)


MAIN_OBJECT_IDS = (
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Gloves.0",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Knee.1",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Robe.2",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Sash.3",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Shawl.4",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Sleeve.5",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Stiletto.6",
    "HUM_F_ARM_Authority_Robe.HUM_F_NKD_Breast.7",
    "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Skirt.8",
)
SKIRT_OBJECT_IDS = (
    "HUM_F_ARM_Authority_Robe_Skirt_KEL.HUM_F_ARM_Authority_Skirt.0",
)
MAIN_SHA256 = "03E2EED348D29649E3E222E613592ACD497D49C8EE3B226E84B2072BAF1BC07B"
SKIRT_SHA256 = "20B32325E017682E1C2EC17CD858F7EDA15DF596F8EBDAD5EAAA4477BE4242AE"
MAIN_VISUAL_UUID = "aec60cfa-c6a1-4a77-8148-b2fa01e4d988"
SKIRT_VISUAL_UUID = "122d5812-e27d-4638-905d-5e520cc26202"
HUMAN_RACE_UUID = "71180b76-5752-4a97-b71f-911a69197f58"
TIEFLING_SMALL_RACE_UUID = "a5789cd3-ecd6-411b-a53a-368b659bc04a"
HALFLING_RACE_UUID = "8f00cf38-4588-433a-8175-8acdbbf33f33"
MISSING_GEOMETRY_IDS = (
    "a913de25-257e-4e42-a677-c663effbe25a",
    "f1f789d3-c09e-485b-8f84-173e41fe9f96",
    "9bebc3db-3e3a-4faf-85fe-f19f589c247d",
    "94e2bcb1-8c38-4687-9833-c761536f0b0a",
)


def _main(*, defect_region: tuple[str, ...] = ("synthetic-defect",)) -> AuthorityComponentReference:
    return AuthorityComponentReference(
        role="main",
        visual_resource_uuid=MAIN_VISUAL_UUID,
        source_family="BCBScantily",
        source_file="Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe.GR2",
        object_ids=MAIN_OBJECT_IDS,
        geometry_sha256=MAIN_SHA256,
        defect_region=defect_region,
    )


def _skirt(*, defect_region: tuple[str, ...] = ("synthetic-skirt-defect",)) -> AuthorityComponentReference:
    return AuthorityComponentReference(
        role="skirt",
        visual_resource_uuid=SKIRT_VISUAL_UUID,
        source_family="BCBScantily",
        source_file="Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe_Skirt_KEL.GR2",
        object_ids=SKIRT_OBJECT_IDS,
        geometry_sha256=SKIRT_SHA256,
        defect_region=defect_region,
    )


def _nonhuman_component(index: int) -> AuthorityComponentReference:
    visual_uuid = MISSING_GEOMETRY_IDS[index]
    prefix = "TIF_FS" if index in (0, 2) else "HFL_F"
    variant = "_Alt" if index in (2, 3) else ""
    object_ids = tuple(
        f"{prefix}_ARM_Authority_Robe.{prefix}_ARM_Authority_{part}.{object_index}"
        for object_index, part in enumerate((
            "Gloves", "Knee", "Robe", "Sash", "Shawl", "Sleeve", "Stiletto", "Breast", "Netherstone", "Skirt"
        ))
    )
    return AuthorityComponentReference(
        role="main",
        visual_resource_uuid=visual_uuid,
        source_family="SCO",
        source_file=f"Generated/Public/SCO/Assets/{prefix}_ARM_Authority_Robe{variant}.GR2",
        object_ids=object_ids,
        geometry_sha256=None,
        defect_region=(),
    )


def _route(
    item_uuid: str,
    variant: str,
    components: tuple[AuthorityComponentReference, ...],
    race_uuid: str = HUMAN_RACE_UUID,
) -> AuthorityRouteReference:
    return AuthorityRouteReference(
        item_uuid=item_uuid,
        variant=variant,
        race_uuid=race_uuid,
        components=components,
    )


def _evidence() -> tuple[AuthorityAuditEvidence, ...]:
    return tuple(
        AuthorityAuditEvidence(
            scope=scope,
            path=f"synthetic/{scope.lower()}.json",
            sha256=f"{index:064X}",
            claim=f"synthetic complete {scope.lower()} audit",
        )
        for index, scope in enumerate(sorted(REQUIRED_AUDIT_SCOPES), start=1)
    )


def _complete_snapshot() -> AuthoritySourceSnapshot:
    return AuthoritySourceSnapshot(
        source_module_uuid="75934b95-f697-4d5b-890c-fe198b799484",
        source_pak_sha256="6BF0EB3F9AD7920BD35DD5BF52218873DB4F1C22CBFBCD73089D3614F3D154BA",
        routes=(
            _route(NORMAL_ITEM_UUID, "normal", (_main(),)),
            _route(NORMAL_ITEM_UUID, "normal", (_nonhuman_component(0),), TIEFLING_SMALL_RACE_UUID),
            _route(NORMAL_ITEM_UUID, "normal", (_nonhuman_component(1),), HALFLING_RACE_UUID),
            _route(SKIRT_ITEM_UUID, "skirt", (_main(), _skirt())),
            _route(ALT_ITEM_UUID, "alt", (_main(), _skirt())),
            _route(ALT_ITEM_UUID, "alt", (_nonhuman_component(2),), TIEFLING_SMALL_RACE_UUID),
            _route(ALT_ITEM_UUID, "alt", (_nonhuman_component(3),), HALFLING_RACE_UUID),
        ),
        evidence=_evidence(),
        searched_aliases=(MAIN_VISUAL_UUID, SKIRT_VISUAL_UUID, *MISSING_GEOMETRY_IDS),
        required_aliases=(MAIN_VISUAL_UUID, SKIRT_VISUAL_UUID, *MISSING_GEOMETRY_IDS),
        unresolved_retained_evidence_files=(),
    )


def test_ten_object_netherstone_substitute_is_rejected_before_contract_admission():
    snapshot = _complete_snapshot()
    ten_object = replace(
        _main(),
        object_ids=MAIN_OBJECT_IDS + (
            "TIF_FS_ARM_Authority_Robe.TIF_FS_ARM_Authority_Netherstone.9",
        ),
    )
    routes = tuple(
        replace(route, components=(ten_object,))
        if route.item_uuid == NORMAL_ITEM_UUID
        else route
        for route in snapshot.routes
    )

    with pytest.raises(ContractAdmissionError, match="AUTHORITY_NETHERSTONE_SUBSTITUTE_FORBIDDEN"):
        resolve_authority_contract(replace(snapshot, routes=routes))


@pytest.mark.parametrize(
    ("item_uuid", "replacement_components", "expected_error"),
    (
        (NORMAL_ITEM_UUID, (_main(), _skirt()), "AUTHORITY_NORMAL_ROUTE_MUST_NOT_HAVE_OPTIONAL_SKIRT"),
        (SKIRT_ITEM_UUID, (_main(),), "AUTHORITY_SKIRT_ROUTE_REQUIRES_OPTIONAL_SKIRT"),
        (ALT_ITEM_UUID, (_main(),), "AUTHORITY_ALT_ROUTE_REQUIRES_OPTIONAL_SKIRT"),
    ),
)
def test_item_specific_normal_skirt_and_alt_contracts_cannot_be_collapsed(
    item_uuid: str,
    replacement_components: tuple[AuthorityComponentReference, ...],
    expected_error: str,
):
    snapshot = _complete_snapshot()
    routes = tuple(
        replace(route, components=replacement_components)
        if route.item_uuid == item_uuid and route.race_uuid == HUMAN_RACE_UUID
        else route
        for route in snapshot.routes
    )

    with pytest.raises(ContractAdmissionError, match=expected_error):
        resolve_authority_contract(replace(snapshot, routes=routes))


def test_exact_human_contract_is_not_enough_to_admit_geometry_while_four_routes_are_forbidden():
    resolution = resolve_authority_contract(_complete_snapshot())

    assert resolution.status == TERMINAL_UNRESOLVED_REASON
    assert resolution.geometry_admitted is False
    assert resolution.replacement_routes == 0
    assert resolution.protected_mutations == 0
    assert resolution.unresolved_geometry_ids == MISSING_GEOMETRY_IDS
    assert resolution.forbidden_substitute_ids == MISSING_GEOMETRY_IDS
    assert resolution.exclusion_event_input is not None


def test_missing_required_race_route_cannot_be_geometry_admitted():
    snapshot = _complete_snapshot()
    routes = tuple(
        route for route in snapshot.routes
        if not (
            route.item_uuid == NORMAL_ITEM_UUID
            and route.race_uuid == HALFLING_RACE_UUID
        )
    )

    with pytest.raises(ContractAdmissionError, match="AUTHORITY_ROUTE_MATRIX_MISMATCH"):
        resolve_authority_contract(replace(snapshot, routes=routes))


def test_unresolved_geometry_ids_cannot_be_swapped_between_race_or_variant_routes():
    snapshot = _complete_snapshot()
    normal_tiefling = next(
        route for route in snapshot.routes
        if route.item_uuid == NORMAL_ITEM_UUID and route.race_uuid == TIEFLING_SMALL_RACE_UUID
    )
    alt_tiefling = next(
        route for route in snapshot.routes
        if route.item_uuid == ALT_ITEM_UUID and route.race_uuid == TIEFLING_SMALL_RACE_UUID
    )
    routes = tuple(
        replace(route, components=alt_tiefling.components)
        if route is normal_tiefling
        else replace(route, components=normal_tiefling.components)
        if route is alt_tiefling
        else route
        for route in snapshot.routes
    )

    with pytest.raises(ContractAdmissionError, match="AUTHORITY_UNRESOLVED_ROUTE_BINDING_MISMATCH"):
        resolve_authority_contract(replace(snapshot, routes=routes))


def test_missing_exact_geometry_after_exhaustive_audit_prepares_terminal_exclusion_input():
    snapshot = _complete_snapshot()
    resolution = resolve_authority_contract(snapshot)

    assert resolution.status == TERMINAL_UNRESOLVED_REASON
    assert resolution.geometry_admitted is False
    assert resolution.unresolved_geometry_ids == MISSING_GEOMETRY_IDS
    assert resolution.replacement_routes == 0
    assert resolution.protected_mutations == 0
    assert resolution.exclusion_event_input is not None
    assert resolution.exclusion_event_input["reason"] == TERMINAL_UNRESOLVED_REASON
    assert resolution.exclusion_event_input["protected_impact"]["result"] == "NO_PROTECTED_MUTATION"
    assert resolution.exclusion_event_input["forbidden_substitutes"] == list(MISSING_GEOMETRY_IDS)


def test_missing_audit_scope_or_alias_remains_blocking_not_terminally_excluded():
    snapshot = _complete_snapshot()
    incomplete_evidence = tuple(
        record for record in snapshot.evidence if record.scope != "PROVIDER_RECORDS"
    )

    resolution = resolve_authority_contract(
        replace(snapshot, evidence=incomplete_evidence)
    )
    assert resolution.status == "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
    assert resolution.exclusion_event_input is None

    resolution = resolve_authority_contract(
        replace(
            snapshot,
            searched_aliases=tuple(
                alias for alias in snapshot.searched_aliases if alias != MISSING_GEOMETRY_IDS[0]
            ),
        )
    )
    assert resolution.status == "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
    assert resolution.exclusion_event_input is None


def test_unreviewed_retained_evidence_file_blocks_exhaustive_disposition():
    snapshot = _complete_snapshot()
    resolution = resolve_authority_contract(
        replace(
            snapshot,
            unresolved_retained_evidence_files=("retained/not-reviewed.json",),
        )
    )

    assert resolution.status == "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
    assert resolution.exclusion_event_input is None


def test_exclusion_event_input_is_canonical_and_binds_every_evidence_hash():
    snapshot = _complete_snapshot()
    resolution = resolve_authority_contract(snapshot)

    first = canonical_exclusion_event_input(resolution)
    second = canonical_exclusion_event_input(resolution)
    payload = json.loads(first)

    assert first == second
    assert first.endswith(b"\n")
    assert [entry["sha256"] for entry in payload["evidence"]] == [
        record.sha256 for record in sorted(snapshot.evidence, key=lambda value: (value.scope, value.path))
    ]
    assert payload["release_ledger_binding"] == "PENDING_TASK_5_VALIDATION_AND_RECORD_BINDING"
    assert payload["ready_for_attachment"] is False


def test_real_sources_do_not_exclude_available_geometry_using_old_partial_inventory():
    resolution = build_current_authority_resolution()

    assert resolution.status == "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
    assert resolution.geometry_admitted is False
    assert resolution.unresolved_geometry_ids == MISSING_GEOMETRY_IDS
    assert resolution.forbidden_substitute_ids == MISSING_GEOMETRY_IDS
    assert resolution.replacement_routes == 0
    assert resolution.protected_mutations == 0
    assert resolution.exclusion_event_input is None


def test_real_hash_locked_route_matrix_keeps_normal_skirt_and_alt_distinct():
    snapshot = load_current_authority_snapshot()
    routes_by_item = {
        item_uuid: tuple(route for route in snapshot.routes if route.item_uuid == item_uuid)
        for item_uuid in (NORMAL_ITEM_UUID, SKIRT_ITEM_UUID, ALT_ITEM_UUID)
    }

    assert tuple(len(routes_by_item[item_uuid]) for item_uuid in (
        NORMAL_ITEM_UUID,
        SKIRT_ITEM_UUID,
        ALT_ITEM_UUID,
    )) == (3, 1, 3)
    human_routes = {
        item_uuid: next(
            route for route in routes if route.race_uuid == HUMAN_RACE_UUID
        )
        for item_uuid, routes in routes_by_item.items()
    }
    assert tuple(component.visual_resource_uuid for component in human_routes[NORMAL_ITEM_UUID].components) == (
        MAIN_VISUAL_UUID,
    )
    assert tuple(component.visual_resource_uuid for component in human_routes[SKIRT_ITEM_UUID].components) == (
        MAIN_VISUAL_UUID,
        SKIRT_VISUAL_UUID,
    )
    assert tuple(component.visual_resource_uuid for component in human_routes[ALT_ITEM_UUID].components) == (
        MAIN_VISUAL_UUID,
        SKIRT_VISUAL_UUID,
    )
    missing_components = tuple(
        route.components[0]
        for item_uuid in (NORMAL_ITEM_UUID, ALT_ITEM_UUID)
        for route in routes_by_item[item_uuid]
        if route.race_uuid != HUMAN_RACE_UUID
    )
    assert tuple(component.visual_resource_uuid for component in missing_components) == MISSING_GEOMETRY_IDS
    assert all(component.geometry_sha256 is not None for component in missing_components)
    assert all(len(component.object_ids) == 10 for component in missing_components)
    assert all(any("Netherstone" in object_id for object_id in component.object_ids) for component in missing_components)
    assert set(snapshot.searched_aliases) == set(snapshot.required_aliases)
    assert snapshot.unresolved_retained_evidence_files


def test_real_incomplete_audit_cannot_write_terminal_exclusion(tmp_path: Path):
    with pytest.raises(ContractAdmissionError, match="AUTHORITY_TERMINAL_EXCLUSION_NOT_ADMITTED"):
        write_current_authority_exclusion_input(tmp_path / "run-1")
    assert not (tmp_path / "run-1").exists()


def test_fresh_source_audit_pins_complete_package_and_rechecks_every_formerly_missing_id():
    snapshot = load_current_authority_snapshot()
    assert hasattr(snapshot, "fresh_source_audit"), "fresh frozen source must be audited"
    audit = snapshot.fresh_source_audit
    assert audit["pak_sha256"] == "182A77E669F1576A3B07D29F226161A43F76EA10D8D3EFEE442D36AEA9F7A891"
    assert audit["file_count"] == 955
    assert audit["listing_path_size_mismatches"] == []
    assert audit["access_gaps"] == []
    assert len(audit["input_manifest"]) == 955
    assert [record["visual_resource_uuid"] for record in audit["geometry_records"]] == list(MISSING_GEOMETRY_IDS)
    assert [record["size_bytes"] for record in audit["geometry_records"]] == [2201876, 2209088, 2244136, 2268400]
    assert all(record["available"] for record in audit["geometry_records"])
    assert all(len(record["object_ids"]) == 10 for record in audit["geometry_records"])
    assert all(any("Netherstone" in name for name in record["object_ids"]) for record in audit["geometry_records"])
    assert set(MISSING_GEOMETRY_IDS) <= {query["alias"] for query in audit["queries"]}


def test_precursor_packet_never_invents_canonical_profile_record_or_event_identity():
    resolution = resolve_authority_contract(_complete_snapshot())
    payload = json.loads(canonical_exclusion_event_input(resolution))
    assert "source_profile_id" not in payload
    assert "identity_sha256" not in payload
    assert "record_id" not in payload
    assert "event_id" not in payload
    assert "approved_by" not in payload
    assert payload["ready_for_attachment"] is False


def test_fresh_contract_is_bound_to_packed_lsf_not_only_bundled_editable_lsx():
    audit = load_current_authority_snapshot().fresh_source_audit
    assert "packed_resource_readback" in audit
    assert [record["input_sha256"] for record in audit["packed_resource_readback"]] == [
        "C9AF449B84D27E4136D9ADCCBA5A02CDD324721328A7C974C32E8E88102EDBD5",
        "8C51AD9F17AF671EA2DF888DBC729DA3E7D4625EE44D08FC907BD9381DD81C2F",
    ]
    assert all(record["tool_sha256"] == "65C47A5050E55F686B55484A901A01D0F1A1D5BA0E776F65FEC71D3E1B2A16B7"
               for record in audit["packed_resource_readback"])
    assert all(record["roottemplate_reference_found"] for record in audit["geometry_records"])


def test_wrong_family_cannot_impersonate_exact_bcb_component():
    snapshot = _complete_snapshot()
    routes = (replace(snapshot.routes[0], components=(replace(_main(), source_family="SCO"),)), *snapshot.routes[1:])
    with pytest.raises(ContractAdmissionError, match="AUTHORITY_COMPONENT_SOURCE_FAMILY_MISMATCH"):
        resolve_authority_contract(replace(snapshot, routes=routes))


def test_blocked_evidence_packet_is_deterministic_nonattachable_and_nonoverwriting(tmp_path: Path):
    assert hasattr(authority_module, "write_current_authority_evidence")
    first = authority_module.write_current_authority_evidence(tmp_path / "first")
    second = authority_module.write_current_authority_evidence(tmp_path / "second")
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_bytes())
    assert payload["status"] == "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
    assert payload["ready_for_attachment"] is False
    assert payload["geometry_admitted"] is False
    assert payload["release_blocking"] is True
    assert payload["unresolved_retained_evidence_files"]
    assert payload["fresh_source_audit"]["file_count"] == 955
    assert payload["exclusion_event_input"] is None
    assert not {"source_profile_id", "identity_sha256", "record_id", "event_id", "approved_by"} & payload.keys()
    with pytest.raises(FileExistsError, match="AUTHORITY_OUTPUT_DIRECTORY_EXISTS"):
        authority_module.write_current_authority_evidence(tmp_path / "first")


def test_unavailable_frozen_source_cannot_fall_back_to_partial_absence(tmp_path: Path):
    with pytest.raises(ContractAdmissionError, match="AUTHORITY_FROZEN_INPUT_UNREADABLE:Scantily.pak"):
        authority_module.audit_frozen_scantily(tmp_path)


def test_same_size_extracted_asset_drift_invalidates_frozen_manifest():
    audit = load_current_authority_snapshot().fresh_source_audit
    assert hasattr(authority_module, "verify_frozen_manifest")
    manifest = audit["input_manifest"]
    assert authority_module.verify_frozen_manifest(manifest) == "419C1CF20FF024C4DEFABD8D5618B0842372B1503CB40D1B424D438538AFEE7B"
    changed = [dict(record) for record in manifest]
    changed[0]["sha256"] = "0" * 64
    with pytest.raises(ContractAdmissionError, match="AUTHORITY_FROZEN_MANIFEST_HASH_MISMATCH"):
        authority_module.verify_frozen_manifest(changed)


def test_invalid_evidence_hash_cannot_assert_exhaustive_audit():
    snapshot = _complete_snapshot()
    invalid_evidence = (replace(snapshot.evidence[0], sha256="not-a-hash"), *snapshot.evidence[1:])
    result = resolve_authority_contract(replace(snapshot, evidence=invalid_evidence))
    assert result.status == "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
    assert result.exclusion_event_input is None


@pytest.mark.parametrize("input_id", ("bcbscantily_source_pak", "bcbscantily_main_gr2", "bcbscantily_skirt_gr2"))
def test_local_config_cannot_relabel_other_bytes_as_frozen_bcb_identity(input_id, tmp_path, monkeypatch):
    original_path = authority_module.AUTHORITY_CONFIG_PATH
    config = json.loads(original_path.read_text(encoding="utf-8"))
    for entry in config["inputs"]:
        if not Path(entry["path"]).is_absolute():
            entry["path"] = str(original_path.parent / entry["path"])
    substitute = next(entry for entry in config["inputs"] if entry["input_id"] == "bcbscantily_meta")
    target = next(entry for entry in config["inputs"] if entry["input_id"] == input_id)
    target["path"], target["expected_sha256"] = substitute["path"], substitute["expected_sha256"]
    config_path = tmp_path / "authority_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(authority_module, "AUTHORITY_CONFIG_PATH", config_path)
    with pytest.raises(ContractAdmissionError, match="AUTHORITY_FROZEN_BCB_IDENTITY_MISMATCH"):
        load_current_authority_snapshot()


def test_authority_geometry_module_is_absent_while_exact_contract_is_unresolved():
    workstream = Path(__file__).resolve().parents[1]

    assert not (workstream / "authority_landmark_cage.py").exists()
    assert not (workstream / "tests" / "test_authority_landmark_cage.py").exists()
