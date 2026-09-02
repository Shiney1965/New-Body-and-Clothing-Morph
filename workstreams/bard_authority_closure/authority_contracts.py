"""Fail-closed Robe of Authority source-contract admission.

This module resolves the exact retained BCBScantily Authority routes.  It does
not build geometry, GR2 files, routes, or packages.  Geometry may begin in a
separate module only when every required component has exact source geometry
and a declared defect region.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import os
import xml.etree.ElementTree as ET
from typing import Mapping

from .contracts import load_authority_contract


NORMAL_ITEM_UUID = "56d78c52-e349-4386-81c0-d8ee8bc8f10e"
SKIRT_ITEM_UUID = "3f869845-badc-4035-ad51-e4ed25f43068"
ALT_ITEM_UUID = "b8c94f92-e857-4725-a59a-5db58bb9a8e6"
TERMINAL_UNRESOLVED_REASON = "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT"
SOURCE_MODULE_UUID = "75934b95-f697-4d5b-890c-fe198b799484"
SOURCE_PAK_SHA256 = "6BF0EB3F9AD7920BD35DD5BF52218873DB4F1C22CBFBCD73089D3614F3D154BA"
MAIN_VISUAL_UUID = "aec60cfa-c6a1-4a77-8148-b2fa01e4d988"
SKIRT_VISUAL_UUID = "122d5812-e27d-4638-905d-5e520cc26202"
UNRESOLVED_GEOMETRY_IDS = (
    "a913de25-257e-4e42-a677-c663effbe25a",
    "f1f789d3-c09e-485b-8f84-173e41fe9f96",
    "9bebc3db-3e3a-4faf-85fe-f19f589c247d",
    "94e2bcb1-8c38-4687-9833-c761536f0b0a",
)
REQUIRED_AUDIT_SCOPES = frozenset({
    "SOURCE_PROFILE",
    "DEPENDENCY",
    "ROOT_TEMPLATES",
    "STATS",
    "INHERITANCE",
    "VISUAL_BANK",
    "GEOMETRY_INVENTORY",
    "PROVIDER_RECORDS",
    "PACKAGE_LISTINGS",
    "ALIAS_SEARCH",
    "SOURCE_MANIFEST",
})
WORKSTREAM_ROOT = Path(__file__).resolve().parent
AUTHORITY_CONFIG_PATH = WORKSTREAM_ROOT / "local" / "authority_config.json"
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")

_ITEM_VARIANTS = {
    NORMAL_ITEM_UUID: "normal",
    SKIRT_ITEM_UUID: "skirt",
    ALT_ITEM_UUID: "alt",
}
_EXPECTED_ROUTE_KEYS = {
    (NORMAL_ITEM_UUID, "71180b76-5752-4a97-b71f-911a69197f58"),
    (NORMAL_ITEM_UUID, "a5789cd3-ecd6-411b-a53a-368b659bc04a"),
    (NORMAL_ITEM_UUID, "8f00cf38-4588-433a-8175-8acdbbf33f33"),
    (SKIRT_ITEM_UUID, "71180b76-5752-4a97-b71f-911a69197f58"),
    (ALT_ITEM_UUID, "71180b76-5752-4a97-b71f-911a69197f58"),
    (ALT_ITEM_UUID, "a5789cd3-ecd6-411b-a53a-368b659bc04a"),
    (ALT_ITEM_UUID, "8f00cf38-4588-433a-8175-8acdbbf33f33"),
}
_EXPECTED_UNRESOLVED_BY_ROUTE = {
    (NORMAL_ITEM_UUID, "a5789cd3-ecd6-411b-a53a-368b659bc04a"): UNRESOLVED_GEOMETRY_IDS[0],
    (NORMAL_ITEM_UUID, "8f00cf38-4588-433a-8175-8acdbbf33f33"): UNRESOLVED_GEOMETRY_IDS[1],
    (ALT_ITEM_UUID, "a5789cd3-ecd6-411b-a53a-368b659bc04a"): UNRESOLVED_GEOMETRY_IDS[2],
    (ALT_ITEM_UUID, "8f00cf38-4588-433a-8175-8acdbbf33f33"): UNRESOLVED_GEOMETRY_IDS[3],
}
# These were absent from the historical partial extraction, not the full PAK.
_REQUIRED_SCO_SOURCE_FILES = {
    "a913de25-257e-4e42-a677-c663effbe25a": "Generated/Public/SCO/Assets/TIF_FS_ARM_Authority_Robe.GR2",
    "f1f789d3-c09e-485b-8f84-173e41fe9f96": "Generated/Public/SCO/Assets/HFL_F_ARM_Authority_Robe.GR2",
    "9bebc3db-3e3a-4faf-85fe-f19f589c247d": "Generated/Public/SCO/Assets/TIF_FS_ARM_Authority_Robe_Alt.GR2",
    "94e2bcb1-8c38-4687-9833-c761536f0b0a": "Generated/Public/SCO/Assets/HFL_F_ARM_Authority_Robe_Alt.GR2",
}
_REQUIRED_REAL_ALIASES = (
    NORMAL_ITEM_UUID,
    SKIRT_ITEM_UUID,
    ALT_ITEM_UUID,
    MAIN_VISUAL_UUID,
    SKIRT_VISUAL_UUID,
    *UNRESOLVED_GEOMETRY_IDS,
    "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe.GR2",
    "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe_Skirt_KEL.GR2",
    *_REQUIRED_SCO_SOURCE_FILES.values(),
    "03E2EED348D29649E3E222E613592ACD497D49C8EE3B226E84B2072BAF1BC07B",
    "20B32325E017682E1C2EC17CD858F7EDA15DF596F8EBDAD5EAAA4477BE4242AE",
    SOURCE_PAK_SHA256,
    "A67C89499E558CA6BD3DB1EB804EA9960F9533CBF07AB9E04EC2B5D724E1BCB4",
    "A48298438EF6901683FC5D95184FD9E1FBE1E6B4E062A35C6AB49A8474247F7A",
    "A2376B89597CD547577D05CA33A58D14059A10D83500FD79B120A734F411328A",
    "83F7D246DE0DC1E761EE413FD15F5C77EA6B18D34A0EF79022351BD75281FF3A",
    "Netherstone",
)
_REQUIRED_INPUT_IDS = {
    "authority_item_contracts",
    "authority_visual_resources",
    "authority_geometry_inventory",
    "authority_input_hashes",
    "authority_class_ledger",
    "bcbscantily_source_pak",
    "bcbscantily_meta",
    "bcbscantily_roottemplates",
    "bcbscantily_visualbank",
    "bcbscantily_stats_armor",
    "bcbscantily_stats_object",
    "bcbscantily_treasure",
    "bcbscantily_main_gr2",
    "bcbscantily_skirt_gr2",
    "sco_roottemplates",
    "sco_visualbank",
    "scantily_separator_pak",
    "sco_addon_zip",
    "sco_addon_pak",
    "sbbf_sco_patch_zip",
    "bcbscantily_package_list",
    "scantily_separator_package_list",
    "sco_addon_package_list",
    "sbbf_sco_patch_list",
    "retained_alias_search",
}


class ContractAdmissionError(ValueError):
    """Raised when a candidate contradicts the exact Authority contract."""


@dataclass(frozen=True)
class AuthorityAuditEvidence:
    scope: str
    path: str
    sha256: str
    claim: str


@dataclass(frozen=True)
class AuthorityComponentReference:
    role: str
    visual_resource_uuid: str
    source_family: str
    source_file: str
    object_ids: tuple[str, ...]
    geometry_sha256: str | None
    defect_region: tuple[str, ...]


@dataclass(frozen=True)
class AuthorityRouteReference:
    item_uuid: str
    variant: str
    race_uuid: str
    components: tuple[AuthorityComponentReference, ...]


@dataclass(frozen=True)
class AuthoritySourceSnapshot:
    source_module_uuid: str
    source_pak_sha256: str
    routes: tuple[AuthorityRouteReference, ...]
    evidence: tuple[AuthorityAuditEvidence, ...]
    searched_aliases: tuple[str, ...]
    required_aliases: tuple[str, ...]
    unresolved_retained_evidence_files: tuple[str, ...]
    fresh_source_audit: dict[str, object] | None = None


@dataclass(frozen=True)
class AuthorityResolution:
    status: str
    geometry_admitted: bool
    unresolved_geometry_ids: tuple[str, ...]
    forbidden_substitute_ids: tuple[str, ...]
    replacement_routes: int
    protected_mutations: int
    exclusion_event_input: dict[str, object] | None


@dataclass(frozen=True)
class _VerifiedAuthorityInput:
    input_id: str
    kind: str
    path: Path
    sha256: str


def _component_is_known_forbidden_substitute(component: AuthorityComponentReference) -> bool:
    return (
        component.visual_resource_uuid in UNRESOLVED_GEOMETRY_IDS
        and component.source_family == "SCO"
        and any("Netherstone" in object_id for object_id in component.object_ids)
    )


def _component_is_known_missing_exact_target(component: AuthorityComponentReference) -> bool:
    expected_source = _REQUIRED_SCO_SOURCE_FILES.get(component.visual_resource_uuid)
    return (
        expected_source is not None
        and component.source_file == expected_source
        and component.geometry_sha256 is None
        and len(component.object_ids) == load_authority_contract().main_component.object_count
        and not any("Netherstone" in object_id for object_id in component.object_ids)
    )


def _validate_exact_component(component: AuthorityComponentReference) -> None:
    contract = load_authority_contract()
    if any("Netherstone" in object_id for object_id in component.object_ids):
        raise ContractAdmissionError("AUTHORITY_NETHERSTONE_SUBSTITUTE_FORBIDDEN")
    if component.source_family != "BCBScantily":
        raise ContractAdmissionError("AUTHORITY_COMPONENT_SOURCE_FAMILY_MISMATCH")
    if component.role == "main":
        if (
            component.visual_resource_uuid != contract.main_component.visual_resource_uuid
            or component.source_file != contract.main_component.source_file
            or component.object_ids != contract.main_component.object_ids
            or component.geometry_sha256 != contract.main_component.sha256
        ):
            raise ContractAdmissionError("AUTHORITY_MAIN_EXACT_CONTRACT_MISMATCH")
    elif component.role == "skirt":
        if (
            component.visual_resource_uuid != contract.skirt_component.visual_resource_uuid
            or component.source_file != contract.skirt_component.source_file
            or component.object_ids != contract.skirt_component.object_ids
            or component.geometry_sha256 != contract.skirt_component.sha256
        ):
            raise ContractAdmissionError("AUTHORITY_SKIRT_EXACT_CONTRACT_MISMATCH")
    else:
        raise ContractAdmissionError("AUTHORITY_COMPONENT_ROLE_INVALID")


def _validate_route_shape(route: AuthorityRouteReference) -> None:
    roles = tuple(component.role for component in route.components)
    if route.item_uuid == NORMAL_ITEM_UUID:
        if roles != ("main",):
            raise ContractAdmissionError("AUTHORITY_NORMAL_ROUTE_MUST_NOT_HAVE_OPTIONAL_SKIRT")
    elif route.item_uuid == SKIRT_ITEM_UUID:
        if roles != ("main", "skirt"):
            raise ContractAdmissionError("AUTHORITY_SKIRT_ROUTE_REQUIRES_OPTIONAL_SKIRT")
    elif route.item_uuid == ALT_ITEM_UUID:
        if roles != ("main", "skirt"):
            raise ContractAdmissionError("AUTHORITY_ALT_ROUTE_REQUIRES_OPTIONAL_SKIRT")
    else:
        raise ContractAdmissionError(f"AUTHORITY_ITEM_NOT_CONTRACTED:{route.item_uuid}")


def _audit_complete(snapshot: AuthoritySourceSnapshot) -> bool:
    scopes = {record.scope for record in snapshot.evidence}
    return (
        REQUIRED_AUDIT_SCOPES <= scopes
        and all(record.path and record.claim and SHA256_RE.fullmatch(record.sha256)
                for record in snapshot.evidence)
        and set(snapshot.required_aliases) <= set(snapshot.searched_aliases)
        and not snapshot.unresolved_retained_evidence_files
    )


def _build_exclusion_input(
    snapshot: AuthoritySourceSnapshot,
    unresolved_ids: tuple[str, ...],
    forbidden_ids: tuple[str, ...],
) -> dict[str, object]:
    evidence = [
        {
            "path": record.path,
            "sha256": record.sha256,
            "claim": record.claim,
            "scope": record.scope,
        }
        for record in sorted(snapshot.evidence, key=lambda value: (value.scope, value.path))
    ]
    return {
        "schema": "clothmorph.authority-exclusion-precursor",
        "schema_version": 1,
        "source_module_uuid": snapshot.source_module_uuid,
        "source_pak_sha256": snapshot.source_pak_sha256,
        "mode": "source",
        "reason": TERMINAL_UNRESOLVED_REASON,
        "scope_statement": (
            "Exclude the unresolved non-Human Authority normal/Alt source routes; "
            "preserve the exact BCBScantily Human nine-object main and optional skirt unchanged."
        ),
        "attempted_architectures": [
            "retained exact-source profile, dependency, route, VisualBank, Stats, geometry, and provider audit"
        ],
        "fixed_acceptance_gates": {
            "main_object_count": 9,
            "optional_skirt_object_count": 1,
            "netherstone_allowed": False,
            "exact_geometry_required": True,
            "defect_region_required_before_geometry": True,
        },
        "unresolved_geometry_ids": list(unresolved_ids),
        "forbidden_substitutes": list(forbidden_ids),
        "evidence": evidence,
        "protected_impact": {
            "registry_ids": [],
            "shared_consumers": [NORMAL_ITEM_UUID, SKIRT_ITEM_UUID, ALT_ITEM_UUID],
            "forbidden_targets": [MAIN_VISUAL_UUID, SKIRT_VISUAL_UUID],
            "result": "NO_PROTECTED_MUTATION",
        },
        "next_project_if_reopened": (
            "Supply the exact hash-pinned missing profile geometry and defect-localization evidence; "
            "do not substitute separator components or the SCO Netherstone contract."
        ),
        "release_ledger_binding": "PENDING_TASK_5_VALIDATION_AND_RECORD_BINDING",
        "ready_for_attachment": False,
    }


def resolve_authority_contract(snapshot: AuthoritySourceSnapshot) -> AuthorityResolution:
    """Resolve an exact snapshot or produce a fail-closed terminal audit input."""
    if snapshot.source_module_uuid != SOURCE_MODULE_UUID:
        raise ContractAdmissionError("AUTHORITY_SOURCE_MODULE_UUID_MISMATCH")
    if snapshot.source_pak_sha256 != SOURCE_PAK_SHA256:
        raise ContractAdmissionError("AUTHORITY_SOURCE_PAK_HASH_MISMATCH")

    route_keys = tuple((route.item_uuid, route.race_uuid) for route in snapshot.routes)
    if len(route_keys) != len(set(route_keys)) or set(route_keys) != _EXPECTED_ROUTE_KEYS:
        raise ContractAdmissionError("AUTHORITY_ROUTE_MATRIX_MISMATCH")

    variants_seen: dict[str, str] = {}
    unresolved: list[str] = []
    forbidden: list[str] = []
    for route in snapshot.routes:
        expected_variant = _ITEM_VARIANTS.get(route.item_uuid)
        if expected_variant is None:
            raise ContractAdmissionError(f"AUTHORITY_ITEM_NOT_CONTRACTED:{route.item_uuid}")
        if route.variant != expected_variant:
            raise ContractAdmissionError("AUTHORITY_ITEM_VARIANT_MISMATCH")
        variants_seen[route.item_uuid] = route.variant

        expected_unresolved = _EXPECTED_UNRESOLVED_BY_ROUTE.get(
            (route.item_uuid, route.race_uuid)
        )
        unresolved_ids_on_route = tuple(
            component.visual_resource_uuid
            for component in route.components
            if component.visual_resource_uuid in UNRESOLVED_GEOMETRY_IDS
        )
        if (
            expected_unresolved is not None
            and unresolved_ids_on_route != (expected_unresolved,)
        ) or (
            expected_unresolved is None
            and unresolved_ids_on_route
        ):
            raise ContractAdmissionError("AUTHORITY_UNRESOLVED_ROUTE_BINDING_MISMATCH")

        known_forbidden = tuple(
            component
            for component in route.components
            if _component_is_known_forbidden_substitute(component)
        )
        if known_forbidden:
            if len(known_forbidden) != len(route.components):
                raise ContractAdmissionError("AUTHORITY_PARTIAL_SUBSTITUTE_ROUTE_FORBIDDEN")
            for component in known_forbidden:
                forbidden.append(component.visual_resource_uuid)
                unresolved.append(component.visual_resource_uuid)
            continue

        known_missing = tuple(
            component
            for component in route.components
            if _component_is_known_missing_exact_target(component)
        )
        if known_missing:
            if len(known_missing) != len(route.components):
                raise ContractAdmissionError("AUTHORITY_PARTIAL_MISSING_EXACT_ROUTE_FORBIDDEN")
            for component in known_missing:
                unresolved.append(component.visual_resource_uuid)
            continue

        _validate_route_shape(route)
        for component in route.components:
            _validate_exact_component(component)
            if component.geometry_sha256 is None:
                unresolved.append(component.visual_resource_uuid)

    if set(variants_seen) != set(_ITEM_VARIANTS):
        raise ContractAdmissionError("AUTHORITY_ITEM_SET_INCOMPLETE")

    unresolved_ids = tuple(
        geometry_id
        for geometry_id in UNRESOLVED_GEOMETRY_IDS
        if geometry_id in set(unresolved)
    ) + tuple(
        geometry_id
        for geometry_id in unresolved
        if geometry_id not in UNRESOLVED_GEOMETRY_IDS
    )
    forbidden_ids = tuple(
        geometry_id for geometry_id in UNRESOLVED_GEOMETRY_IDS if geometry_id in set(forbidden)
    )
    audit_complete = _audit_complete(snapshot)
    if unresolved_ids:
        if not audit_complete:
            return AuthorityResolution(
                status="BLOCKED_SOURCE_AUDIT_INCOMPLETE",
                geometry_admitted=False,
                unresolved_geometry_ids=unresolved_ids,
                forbidden_substitute_ids=forbidden_ids,
                replacement_routes=0,
                protected_mutations=0,
                exclusion_event_input=None,
            )
        return AuthorityResolution(
            status=TERMINAL_UNRESOLVED_REASON,
            geometry_admitted=False,
            unresolved_geometry_ids=unresolved_ids,
            forbidden_substitute_ids=forbidden_ids,
            replacement_routes=0,
            protected_mutations=0,
            exclusion_event_input=_build_exclusion_input(
                snapshot, unresolved_ids, forbidden_ids
            ),
        )

    missing_defect_regions = tuple(
        component.visual_resource_uuid
        for route in snapshot.routes
        for component in route.components
        if not component.defect_region
    )
    if missing_defect_regions:
        if not audit_complete:
            status = "BLOCKED_SOURCE_AUDIT_INCOMPLETE"
            event_input = None
        else:
            status = TERMINAL_UNRESOLVED_REASON
            event_input = _build_exclusion_input(snapshot, missing_defect_regions, ())
        return AuthorityResolution(
            status=status,
            geometry_admitted=False,
            unresolved_geometry_ids=missing_defect_regions,
            forbidden_substitute_ids=(),
            replacement_routes=0,
            protected_mutations=0,
            exclusion_event_input=event_input,
        )

    return AuthorityResolution(
        status="EXACT_CONTRACT_ADMITTED_FOR_CONDITIONAL_GEOMETRY",
        geometry_admitted=True,
        unresolved_geometry_ids=(),
        forbidden_substitute_ids=(),
        replacement_routes=0,
        protected_mutations=0,
        exclusion_event_input=None,
    )


def canonical_exclusion_event_input(resolution: AuthorityResolution) -> bytes:
    """Return deterministic Task-5 input bytes for a terminal source audit."""
    if resolution.exclusion_event_input is None:
        raise ContractAdmissionError("AUTHORITY_EXCLUSION_INPUT_NOT_AVAILABLE")
    return (
        json.dumps(
            resolution.exclusion_event_input,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_verified_authority_inputs() -> dict[str, _VerifiedAuthorityInput]:
    try:
        payload = json.loads(AUTHORITY_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_MISSING") from error
    except json.JSONDecodeError as error:
        raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_INVALID_JSON") from error
    if not isinstance(payload, dict) or payload.get("schema") != "clothmorph.authority-local-evidence":
        raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_INVALID_SCHEMA")
    raw_inputs = payload.get("inputs")
    if not isinstance(raw_inputs, list):
        raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_INPUTS_INVALID")
    verified: dict[str, _VerifiedAuthorityInput] = {}
    for value in raw_inputs:
        if not isinstance(value, dict):
            raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_INPUT_INVALID")
        input_id = value.get("input_id")
        kind = value.get("kind")
        configured_path = value.get("path")
        expected = value.get("expected_sha256")
        if not all(isinstance(item, str) and item for item in (input_id, kind, configured_path, expected)):
            raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_INPUT_INVALID")
        if SHA256_RE.fullmatch(expected) is None:
            raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_HASH_INVALID")
        path_value = Path(configured_path)
        path = (
            path_value.resolve(strict=False)
            if path_value.is_absolute()
            else (AUTHORITY_CONFIG_PATH.parent / path_value).resolve(strict=False)
        )
        if input_id in verified:
            raise ContractAdmissionError("AUTHORITY_LOCAL_CONFIG_DUPLICATE_INPUT")
        try:
            actual = _hash_file(path)
        except OSError as error:
            raise ContractAdmissionError(f"AUTHORITY_EVIDENCE_UNREADABLE:{input_id}") from error
        if actual != expected:
            raise ContractAdmissionError(f"AUTHORITY_EVIDENCE_HASH_MISMATCH:{input_id}")
        verified[input_id] = _VerifiedAuthorityInput(input_id, kind, path, actual)
    if set(verified) != _REQUIRED_INPUT_IDS:
        raise ContractAdmissionError("AUTHORITY_EVIDENCE_INPUT_SET_MISMATCH")
    return verified


def _load_json(path: Path, error_code: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractAdmissionError(error_code) from error
    if not isinstance(value, dict):
        raise ContractAdmissionError(error_code)
    return value


def _component_from_json(value: object) -> AuthorityComponentReference:
    if not isinstance(value, dict):
        raise ContractAdmissionError("AUTHORITY_ITEM_COMPONENT_INVALID")
    visual_uuid = value.get("visual_resource_uuid")
    source_family = value.get("source_family")
    source_file = value.get("source_file")
    objects = value.get("objects")
    if not (
        isinstance(visual_uuid, str)
        and isinstance(source_family, str)
        and isinstance(source_file, str)
        and isinstance(objects, list)
    ):
        raise ContractAdmissionError("AUTHORITY_ITEM_COMPONENT_INVALID")
    object_ids: list[str] = []
    for object_value in objects:
        if not isinstance(object_value, dict) or not isinstance(object_value.get("object_id"), str):
            raise ContractAdmissionError("AUTHORITY_ITEM_OBJECT_INVALID")
        object_ids.append(object_value["object_id"])
    geometry = value.get("geometry")
    geometry_sha256: str | None = None
    if geometry is not None:
        if not isinstance(geometry, dict) or not isinstance(geometry.get("sha256"), str):
            raise ContractAdmissionError("AUTHORITY_ITEM_GEOMETRY_INVALID")
        geometry_sha256 = geometry["sha256"]
    return AuthorityComponentReference(
        role="skirt" if visual_uuid == SKIRT_VISUAL_UUID else "main",
        visual_resource_uuid=visual_uuid,
        source_family=source_family,
        source_file=source_file,
        object_ids=tuple(object_ids),
        geometry_sha256=geometry_sha256,
        defect_region=(),
    )


def _routes_from_item_contracts(path: Path) -> tuple[AuthorityRouteReference, ...]:
    payload = _load_json(path, "AUTHORITY_ITEM_CONTRACTS_INVALID")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ContractAdmissionError("AUTHORITY_ITEM_CONTRACTS_INVALID")
    selected = [
        item for item in raw_items
        if isinstance(item, dict) and item.get("item_uuid") in _ITEM_VARIANTS
    ]
    if {item.get("item_uuid") for item in selected} != set(_ITEM_VARIANTS):
        raise ContractAdmissionError("AUTHORITY_ITEM_SET_INCOMPLETE")
    routes: list[AuthorityRouteReference] = []
    for item in selected:
        item_uuid = item["item_uuid"]
        raw_routes = item.get("route_contracts")
        if not isinstance(raw_routes, list):
            raise ContractAdmissionError("AUTHORITY_ITEM_ROUTES_INVALID")
        for raw_route in raw_routes:
            if not isinstance(raw_route, dict):
                raise ContractAdmissionError("AUTHORITY_ITEM_ROUTE_INVALID")
            race_uuid = raw_route.get("race_uuid")
            components = raw_route.get("ordered_components")
            if not isinstance(race_uuid, str) or not isinstance(components, list):
                raise ContractAdmissionError("AUTHORITY_ITEM_ROUTE_INVALID")
            routes.append(AuthorityRouteReference(
                item_uuid=item_uuid,
                variant=_ITEM_VARIANTS[item_uuid],
                race_uuid=race_uuid,
                components=tuple(_component_from_json(value) for value in components),
            ))
    return tuple(routes)


def _validate_real_evidence(verified: Mapping[str, _VerifiedAuthorityInput]) -> tuple[str, ...]:
    contract = load_authority_contract()
    for input_id, expected in (
        ("bcbscantily_source_pak", SOURCE_PAK_SHA256),
        ("bcbscantily_main_gr2", contract.main_component.sha256),
        ("bcbscantily_skirt_gr2", contract.skirt_component.sha256),
    ):
        if verified[input_id].sha256 != expected:
            raise ContractAdmissionError(f"AUTHORITY_FROZEN_BCB_IDENTITY_MISMATCH:{input_id}")
    alias_payload = _load_json(
        verified["retained_alias_search"].path,
        "AUTHORITY_ALIAS_SEARCH_INVALID",
    )
    if (
        alias_payload.get("schema") != "clothmorph.authority-retained-alias-search"
        or alias_payload.get("schema_version") != 1
        or alias_payload.get("unreviewed_relevant_files") != []
    ):
        raise ContractAdmissionError("AUTHORITY_ALIAS_SEARCH_INVALID")
    raw_queries = alias_payload.get("queries")
    if not isinstance(raw_queries, list):
        raise ContractAdmissionError("AUTHORITY_ALIAS_SEARCH_INVALID")
    aliases: list[str] = []
    for query in raw_queries:
        if not isinstance(query, dict) or not isinstance(query.get("alias"), str):
            raise ContractAdmissionError("AUTHORITY_ALIAS_SEARCH_INVALID")
        if not isinstance(query.get("matched_paths"), list):
            raise ContractAdmissionError("AUTHORITY_ALIAS_SEARCH_INVALID")
        aliases.append(query["alias"])
    if len(aliases) != len(set(aliases)) or set(aliases) != set(_REQUIRED_REAL_ALIASES):
        raise ContractAdmissionError("AUTHORITY_ALIAS_SET_MISMATCH")

    bcb_listing = verified["bcbscantily_package_list"].path.read_text(encoding="utf-8")
    separator_listing = verified["scantily_separator_package_list"].path.read_text(encoding="utf-8")
    addon_listing = verified["sco_addon_package_list"].path.read_text(encoding="utf-8")
    sbbf_listing = verified["sbbf_sco_patch_list"].path.read_text(encoding="utf-8")
    main_path = "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe.GR2"
    skirt_path = "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe_Skirt_KEL.GR2"
    if main_path not in bcb_listing or skirt_path not in bcb_listing:
        raise ContractAdmissionError("AUTHORITY_BCB_PACKAGE_CONTRACT_MISSING")
    for source_file in _REQUIRED_SCO_SOURCE_FILES.values():
        if any(source_file.lower() in listing.lower() for listing in (
            bcb_listing, separator_listing, addon_listing, sbbf_listing
        )):
            raise ContractAdmissionError("AUTHORITY_MISSING_SOURCE_ALIAS_CONTRADICTED")
    if (
        "Generated/Public/Scantily_Separator/Assets/HFL_F_ARM_Authority_Robe_A.GR2"
        not in separator_listing
        or "Generated/Public/SCO/Assets/HUM_F_ARM_Authority_Robe_Alt.gr2"
        not in sbbf_listing
    ):
        raise ContractAdmissionError("AUTHORITY_ALTERNATE_DEPENDENCY_INVENTORY_INCOMPLETE")

    bcb_root = verified["bcbscantily_roottemplates"].path.read_text(encoding="utf-8")
    bcb_visual = verified["bcbscantily_visualbank"].path.read_text(encoding="utf-8")
    sco_root = verified["sco_roottemplates"].path.read_text(encoding="utf-8")
    sco_visual = verified["sco_visualbank"].path.read_text(encoding="utf-8")
    stats = verified["bcbscantily_stats_armor"].path.read_text(encoding="utf-8")
    for item_uuid in _ITEM_VARIANTS:
        if item_uuid not in bcb_root:
            raise ContractAdmissionError("AUTHORITY_ROOT_TEMPLATE_ITEM_MISSING")
    if (
        'using "ARM_Camp_Body"' not in stats
        or SKIRT_ITEM_UUID not in stats
        or MAIN_VISUAL_UUID not in bcb_visual
        or SKIRT_VISUAL_UUID not in bcb_visual
    ):
        raise ContractAdmissionError("AUTHORITY_BCB_METADATA_CONTRACT_MISMATCH")
    for geometry_id, source_file in _REQUIRED_SCO_SOURCE_FILES.items():
        if geometry_id not in sco_root or geometry_id not in sco_visual or source_file not in sco_visual:
            raise ContractAdmissionError("AUTHORITY_SCO_REFERENCE_CONTRACT_MISSING")
    if "Netherstone" not in sco_visual:
        raise ContractAdmissionError("AUTHORITY_SCO_SUBSTITUTE_EVIDENCE_MISSING")

    geometry_text = verified["authority_geometry_inventory"].path.read_text(encoding="utf-8")
    if (
        load_authority_contract().main_component.sha256 not in geometry_text
        or load_authority_contract().skirt_component.sha256 not in geometry_text
    ):
        raise ContractAdmissionError("AUTHORITY_GEOMETRY_INVENTORY_CONTRACT_MISSING")
    for source_file in _REQUIRED_SCO_SOURCE_FILES.values():
        if source_file in geometry_text:
            raise ContractAdmissionError("AUTHORITY_GEOMETRY_INVENTORY_CONTRADICTION")

    meta = verified["bcbscantily_meta"].path.read_text(encoding="utf-8")
    if (
        'value="75934b95-f697-4d5b-890c-fe198b799484"' not in meta
        or 'value="36028797018963968"' not in meta
    ):
        raise ContractAdmissionError("AUTHORITY_SOURCE_PROFILE_METADATA_MISMATCH")
    return tuple(aliases)


_FROZEN_SCANTILY_PINS = {
    "Scantily.pak": "182A77E669F1576A3B07D29F226161A43F76EA10D8D3EFEE442D36AEA9F7A891",
    "SOURCE_PAK_COPY_MANIFEST.json": "84484226DD8751D8092CAB4A2ACD323BC4C94B97D55A088FFD26D6F6C9A2779B",
    "FRESH_EXTRACTION_SUMMARY.json": "FCB8931D8D7030DBC7CD49BB011ED089FAE41DE71B378994D3242EEABADC83CC",
    "listings/Scantily.listing.txt": "9E778183837C255E481683B0229487BEE7A7450FED5323D0434780E3D5C29400",
}
_FRESH_READBACK_PINS = (
    ("Public/SCO/Content/Assets/Characters/[PAK]_Armor/_merged.lsf",
     "C9AF449B84D27E4136D9ADCCBA5A02CDD324721328A7C974C32E8E88102EDBD5",
     "visualbank.lsx", "DAF00D2A04FF05C1E0E1B7BD59E9FC559148F46529A66F387E15198F36B7D2EF"),
    ("Public/SCO/RootTemplates/_merged.lsf",
     "8C51AD9F17AF671EA2DF888DBC729DA3E7D4625EE44D08FC907BD9381DD81C2F",
     "roottemplates.lsx", "2EC3D885AF511340EEF9F07BDD4B9499A7C9B907C18A5C6962C0D0ACF8262D34"),
)


def verify_frozen_manifest(manifest: list[dict[str, object]]) -> str:
    """Pin every extracted path, size and byte hash, including same-size drift."""
    actual = hashlib.sha256((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest().upper()
    if actual != "419C1CF20FF024C4DEFABD8D5618B0842372B1503CB40D1B424D438538AFEE7B":
        raise ContractAdmissionError("AUTHORITY_FROZEN_MANIFEST_HASH_MISMATCH")
    return actual


def audit_frozen_scantily(root: Path) -> dict[str, object]:
    """Read the complete frozen package inventory; never infer binary semantics.

    Contract metadata is read from hash-pinned Divine conversions of the packed
    LSF resources, not inferred from included editable LSX. GR2 semantics are
    intentionally not inferred from metadata or byte availability.
    """
    root = Path(root)
    pins = []
    for relative, expected in _FROZEN_SCANTILY_PINS.items():
        path = root / relative
        try:
            actual = _hash_file(path)
        except OSError as error:
            raise ContractAdmissionError(f"AUTHORITY_FROZEN_INPUT_UNREADABLE:{relative}") from error
        if actual != expected:
            raise ContractAdmissionError(f"AUTHORITY_FROZEN_INPUT_HASH_MISMATCH:{relative}")
        pins.append({"path": str(path), "sha256": actual})
    listing = {}
    for line in (root / "listings/Scantily.listing.txt").read_text(encoding="utf-8").splitlines():
        relative, size, _ = line.split("\t")
        if relative in listing or relative.startswith("/") or ".." in Path(relative).parts:
            raise ContractAdmissionError("AUTHORITY_FROZEN_LISTING_INVALID")
        listing[relative] = int(size)
    extracted = root / "extracted/Scantily"
    gaps: list[str] = []
    manifest = []
    text_sources = {}
    for directory, subdirectories, names in os.walk(extracted, onerror=lambda error: gaps.append(str(error))):
        for name in subdirectories + names:
            path = Path(directory) / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ContractAdmissionError("AUTHORITY_FROZEN_REPARSE_FORBIDDEN")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(extracted).as_posix()
            try:
                manifest.append({"path": relative, "size_bytes": path.stat().st_size, "sha256": _hash_file(path)})
                if path.suffix.lower() in {".lsx", ".txt", ".json", ".xml", ".lua"}:
                    text_sources[relative] = path.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError) as error:
                gaps.append(f"{relative}:{type(error).__name__}:{error}")
    manifest.sort(key=lambda record: record["path"])
    actual_sizes = {record["path"]: record["size_bytes"] for record in manifest}
    mismatches = sorted(relative for relative in listing.keys() | actual_sizes.keys()
                        if listing.get(relative) != actual_sizes.get(relative))
    if gaps or mismatches or len(manifest) != 955:
        raise ContractAdmissionError("AUTHORITY_FROZEN_EXTRACTION_INCOMPLETE:" + json.dumps({
            "access_gaps": gaps, "mismatches": mismatches, "file_count": len(manifest)}, sort_keys=True))
    manifest_hash = verify_frozen_manifest(manifest)
    readback_root = WORKSTREAM_ROOT / "local/task-4-fresh-readback-20260902"
    readbacks = []
    for source, source_hash, target, target_hash in _FRESH_READBACK_PINS:
        if _hash_file(extracted / source) != source_hash or _hash_file(readback_root / target) != target_hash:
            raise ContractAdmissionError("AUTHORITY_FRESH_READBACK_HASH_MISMATCH")
        readbacks.append({
            "input_path": str(extracted / source), "input_sha256": source_hash,
            "output_path": str(readback_root / target), "output_sha256": target_hash,
            "tool_path": "C:/bg3-sidecar-work/Tools/Divine.exe",
            "tool_sha256": "65C47A5050E55F686B55484A901A01D0F1A1D5BA0E776F65FEC71D3E1B2A16B7",
            "action": "convert-resource", "game": "bg3",
        })
        text_sources[f"READBACK/{target}"] = (readback_root / target).read_text(encoding="utf-8-sig").splitlines()
    resources = ET.fromstring("\n".join(text_sources["READBACK/visualbank.lsx"]))
    root_templates = ET.fromstring("\n".join(text_sources["READBACK/roottemplates.lsx"]))
    root_values = {attribute.get("value") for attribute in root_templates.iter("attribute")}
    geometry = []
    by_path = {record["path"]: record for record in manifest}
    for visual_uuid, expected_path in _REQUIRED_SCO_SOURCE_FILES.items():
        matches = [node for node in resources.iter("node") if any(
            attribute.get("id") == "ID" and attribute.get("value") == visual_uuid
            for attribute in node.findall("attribute"))]
        if len(matches) != 1:
            raise ContractAdmissionError(f"AUTHORITY_FRESH_VISUAL_ID_NOT_UNIQUE:{visual_uuid}")
        node = matches[0]
        source = node.find("attribute[@id='SourceFile']")
        if source is None or source.get("value") != expected_path:
            raise ContractAdmissionError(f"AUTHORITY_FRESH_VISUAL_PATH_MISMATCH:{visual_uuid}")
        objects = [value.get("value") for value in node.findall("children/node[@id='Objects']/attribute[@id='ObjectID']")]
        metadata = by_path.get(expected_path)
        geometry.append({
            "visual_resource_uuid": visual_uuid, "source_file": expected_path,
            "available": metadata is not None,
            "sha256": metadata["sha256"] if metadata else None,
            "size_bytes": metadata["size_bytes"] if metadata else None,
            "object_ids": objects, "object_evidence": str(readback_root / "visualbank.lsx"),
            "roottemplate_reference_found": visual_uuid in root_values,
            "binary_geometry_readback": "UNASSESSED",
            "admissible_as_nine_object_replacement": False,
        })
    queries = []
    aliases = (*_REQUIRED_REAL_ALIASES, _FROZEN_SCANTILY_PINS["Scantily.pak"],
               *(record["sha256"] for record in geometry if record["sha256"]))
    for alias in dict.fromkeys(aliases):
        folded = alias.casefold()
        hits = [{"path": relative, "line": index, "text": line}
                for relative, lines in sorted(text_sources.items())
                for index, line in enumerate(lines, start=1) if folded in line.casefold()]
        queries.append({"alias": alias, "text_hits": hits,
                        "path_hits": [path for path in sorted(by_path) if folded in path.casefold()],
                        "hash_hits": [record["path"] for record in manifest if record["sha256"].casefold() == folded]})
    return {
        "pak_sha256": _FROZEN_SCANTILY_PINS["Scantily.pak"],
        "pak_size_bytes": (root / "Scantily.pak").stat().st_size,
        "source_root": str(root), "pins": pins,
        "file_count": len(manifest), "listing_path_size_mismatches": mismatches,
        "access_gaps": gaps, "input_manifest": manifest, "input_manifest_sha256": manifest_hash,
        "geometry_records": geometry,
        "queries": queries, "text_scan_paths": sorted(text_sources), "packed_resource_readback": readbacks,
        "search_scope": "All extracted paths and SHA256 values; UTF-8 LSX/TXT/JSON/XML/Lua content. Compressed/binary contents are inventoried, not searched as decoded resources.",
        "unresolved_retained_evidence_files": [str(extracted / record["source_file"]) for record in geometry],
    }


def load_current_authority_snapshot() -> AuthoritySourceSnapshot:
    """Load and independently validate the exact retained Authority evidence set."""
    verified = _load_verified_authority_inputs()
    aliases = _validate_real_evidence(verified)
    routes = _routes_from_item_contracts(verified["authority_item_contracts"].path)
    config = _load_json(AUTHORITY_CONFIG_PATH, "AUTHORITY_LOCAL_CONFIG_INVALID_JSON")
    fresh_root = config.get("fresh_scantily_root")
    if not isinstance(fresh_root, str) or not Path(fresh_root).is_absolute():
        raise ContractAdmissionError("AUTHORITY_FRESH_SOURCE_CONFIG_MISSING")
    fresh = audit_frozen_scantily(Path(fresh_root))
    fresh_geometry = {record["visual_resource_uuid"]: record for record in fresh["geometry_records"]}
    routes = tuple(replace(route, components=tuple(
        replace(component, geometry_sha256=fresh_geometry[component.visual_resource_uuid]["sha256"],
                object_ids=tuple(fresh_geometry[component.visual_resource_uuid]["object_ids"]))
        if component.visual_resource_uuid in fresh_geometry else component
        for component in route.components)) for route in routes)
    evidence = tuple(
        AuthorityAuditEvidence(
            scope=value.kind,
            path=str(value.path),
            sha256=value.sha256,
            claim=f"hash-verified retained Authority {value.kind.lower()} evidence",
        )
        for value in verified.values()
    )
    # The old report's empty unreviewed-files list is an assertion, not proof.
    # Preserve every matched file not semantically consumed by this reader.
    old_search = _load_json(verified["retained_alias_search"].path, "AUTHORITY_ALIAS_SEARCH_INVALID")
    verified_paths = {str(value.path).casefold() for value in verified.values()}
    unreviewed = {
        path for query in old_search["queries"] for path in query["matched_paths"]
        if path.casefold() not in verified_paths
    }
    unreviewed.update(fresh["unresolved_retained_evidence_files"])
    unreviewed.update(str(verified[input_id].path) for input_id in (
        "authority_geometry_inventory", "scantily_separator_pak", "sco_addon_pak", "sbbf_sco_patch_zip"))
    return AuthoritySourceSnapshot(
        source_module_uuid=SOURCE_MODULE_UUID,
        source_pak_sha256=SOURCE_PAK_SHA256,
        routes=routes,
        evidence=evidence,
        searched_aliases=aliases,
        required_aliases=_REQUIRED_REAL_ALIASES,
        unresolved_retained_evidence_files=tuple(sorted(unreviewed)),
        fresh_source_audit=fresh,
    )


def build_current_authority_resolution() -> AuthorityResolution:
    """Resolve the exact hash-pinned retained Authority evidence set."""
    return resolve_authority_contract(load_current_authority_snapshot())


def write_current_authority_exclusion_input(output_directory: Path) -> Path:
    """Write a precursor only after exhaustive audit; current blocked state refuses."""
    resolution = build_current_authority_resolution()
    if resolution.status != TERMINAL_UNRESOLVED_REASON:
        raise ContractAdmissionError("AUTHORITY_TERMINAL_EXCLUSION_NOT_ADMITTED")
    output_directory = Path(output_directory)
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_directory.mkdir()
    except FileExistsError as error:
        raise FileExistsError("AUTHORITY_OUTPUT_DIRECTORY_EXISTS") from error
    output_path = output_directory / "authority-exclusion-input.json"
    output_path.write_bytes(canonical_exclusion_event_input(resolution))
    return output_path


def write_current_authority_evidence(output_directory: Path) -> Path:
    """Write a deterministic, noncanonical evidence packet, including blockers."""
    snapshot = load_current_authority_snapshot()
    resolution = resolve_authority_contract(snapshot)
    payload = {
        "schema": "clothmorph.authority-source-audit-evidence", "schema_version": 1,
        "status": resolution.status, "ready_for_attachment": False,
        "release_blocking": True, "geometry_admitted": resolution.geometry_admitted,
        "replacement_routes": 0, "protected_mutations": 0,
        "source_module_uuid": snapshot.source_module_uuid,
        "source_pak_sha256": snapshot.source_pak_sha256,
        "fresh_source_audit": snapshot.fresh_source_audit,
        "unresolved_geometry_ids": list(resolution.unresolved_geometry_ids),
        "forbidden_substitute_ids": list(resolution.forbidden_substitute_ids),
        "unresolved_retained_evidence_files": list(snapshot.unresolved_retained_evidence_files),
        "blockers": [
            "Formerly missing SCO bytes are present, but packed VisualBank contracts have ten objects including Netherstone; no nine-object replacement admitted.",
            "Fresh GR2 binary readback and exact defect localization have not been completed. Byte hashes and metadata are not geometry acceptance.",
            "Legacy geometry inventory and unmatched retained alias hits require reconciliation; other retained dependency packages have listing-only coverage here.",
            "Independent anti-omission verification and canonical release-ledger identity binding are not supplied by this Task-4 packet.",
        ],
        "evidence": [record.__dict__ for record in snapshot.evidence],
        "routes": [
            {"item_uuid": route.item_uuid, "variant": route.variant, "race_uuid": route.race_uuid,
             "components": [component.__dict__ for component in route.components]}
            for route in snapshot.routes
        ],
        "exclusion_event_input": resolution.exclusion_event_input,
    }
    output_directory = Path(output_directory)
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_directory.mkdir()
    except FileExistsError as error:
        raise FileExistsError("AUTHORITY_OUTPUT_DIRECTORY_EXISTS") from error
    output_path = output_directory / "authority-source-audit-evidence.json"
    with output_path.open("xb") as stream:
        stream.write((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    return output_path
