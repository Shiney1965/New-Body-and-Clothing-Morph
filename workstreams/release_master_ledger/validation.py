"""Standard-library validation for public release-ledger records."""

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from .exclusions import (
    EXCLUSION_MODES,
    EXCLUSION_REASONS,
    RELEASE_MODES,
    ZERO_CLAIM_MODE_ROUTE,
    validate_exclusion_event,
)
from .identity import build_identity, canonical_json, sha256_text
from .models import CanonicalIdentityFields


DISPOSITIONS = (
    "ACCEPTED_PROTECTED",
    "SOURCE_NATIVE_PROTECTED",
    "PACKAGE_ONLY_PROTECTED",
    "READY_FOR_OFFLINE_CORRECTION",
    "OFFLINE_CANDIDATE_PASS",
    "PACKAGE_READY_GAMEPLAY_UNASSESSED",
    "CLASS_GAMEPLAY_ACCEPTED",
    "ITEM_GAMEPLAY_ACCEPTED",
    "SHIPPED_NATIVE_PASSTHROUGH",
    "SHIPPED_REFIT",
    "OUT_OF_SCOPE_WITH_PROOF",
    "BLOCKED_WITH_CAUSE",
    "DEFERRED_WITH_CAUSE",
)
MODE_ROUTES = RELEASE_MODES
MODE_FIELDS = (
    "behavior",
    "target_vrs",
    "target_paths",
    "payload_hashes",
    "provider_id",
    "provenance",
    "static_status",
    "gameplay_status",
    "save_reload_status",
)
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
BLOCKER_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*(?::[A-Z0-9_.-]+)*$")
EXCLUSION_EVENT_ID_RE = re.compile(r"^EXCLUSION_[0-9A-F]{64}$")
NON_EXCLUSION_TERMINAL_DISPOSITIONS = frozenset({
    "ACCEPTED_PROTECTED", "SOURCE_NATIVE_PROTECTED",
    "SHIPPED_NATIVE_PASSTHROUGH", "SHIPPED_REFIT",
})
TERMINAL_GATES = (
    "topology", "component", "material", "skin", "clearance", "silhouette",
    "deterministic_readback", "nontriviality",
)

_TEXT_VALUES = (
    ("record_id",),
    ("canonical_identity",),
    ("identity_sha256",),
    ("source_module", "pak"),
    ("source_module", "folder"),
    ("source_module", "name"),
    ("source_module", "uuid"),
    ("source_module", "version64"),
    ("source_module", "pak_sha256"),
    ("source_module", "profile_digest"),
    ("permission", "state"),
    ("permission", "evidence_path"),
    ("permission", "evidence_sha256"),
    ("permission", "credit"),
    ("permission", "distribution_limits"),
    ("creation_path", "kind"),
    ("creation_path", "root_uuid"),
    ("creation_path", "stats_entry"),
    ("creation_path", "chain_digest"),
    ("classification", "effective_slot"),
    ("classification", "body_content"),
    ("classification", "garment_family"),
    ("classification", "class_id"),
    ("classification", "class_contract_digest"),
    ("body_tuple", "race"),
    ("body_tuple", "sex"),
    ("body_tuple", "body_type"),
    ("body_tuple", "body_shape"),
    ("body_tuple", "equipment_race"),
    ("source_route", "component_contract_digest"),
    ("transformation", "eligibility"),
    ("transformation", "strategy"),
    ("transformation", "exception_id"),
    ("next_admissible_action",),
    ("acceptance_event_id",),
    ("shipped_package_id",),
)
_SEQUENCE_VALUES = (
    ("creation_path", "inheritance_chain"),
    ("source_route", "ordered_vrs"),
    ("source_route", "ordered_paths"),
    ("source_route", "ordered_file_hashes"),
    ("protected_relations", "registry_ids"),
    ("protected_relations", "protected_consumers"),
    ("protected_relations", "shared_assets"),
    ("protected_relations", "forbidden_targets"),
    ("transformation", "allowed_components"),
    ("transformation", "allowed_channels"),
    ("evidence_paths",),
    ("evidence_hashes",),
)
_GATES = (
    "topology",
    "component",
    "material",
    "skin",
    "clearance",
    "package",
    "fresh_extract",
    "route",
    "gameplay",
)
_HASH_VALUES = (
    ("identity_sha256",),
    ("source_module", "pak_sha256"),
    ("source_module", "profile_digest"),
    ("permission", "evidence_sha256"),
    ("creation_path", "chain_digest"),
    ("classification", "class_contract_digest"),
    ("source_route", "component_contract_digest"),
)
_HASH_SEQUENCES = (
    ("source_route", "ordered_file_hashes"),
    ("evidence_hashes",),
)


def _value_at(record: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, object]:
    current: object = record
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == [] or value == () or value == {}


def _is_unknown_code(value: object) -> bool:
    if not isinstance(value, str) or not BLOCKER_CODE_RE.fullmatch(value):
        return False
    return (
        value.startswith(("UNKNOWN_", "UNASSESSED_", "MISSING_", "BLOCKED_"))
        or value.endswith("_UNASSESSED")
        or value.endswith("_UNRESOLVED")
    )


def _is_valid_hash_or_unknown(value: object) -> bool:
    return isinstance(value, str) and (
        SHA256_RE.fullmatch(value) is not None or _is_unknown_code(value)
    )


def _validate_text_values(record: Mapping[str, Any], errors: list[str]) -> None:
    for path in _TEXT_VALUES:
        present, value = _value_at(record, path)
        dotted_path = ".".join(path)
        if not present:
            errors.append(f"MISSING:{dotted_path}")
        elif _is_blank(value):
            errors.append(f"BLANK:{dotted_path}")
        elif not isinstance(value, str):
            errors.append(f"INVALID_TYPE:{dotted_path}")


def _validate_sequence_values(record: Mapping[str, Any], errors: list[str]) -> None:
    for path in _SEQUENCE_VALUES:
        present, value = _value_at(record, path)
        dotted_path = ".".join(path)
        if not present:
            errors.append(f"MISSING:{dotted_path}")
        elif not isinstance(value, (list, tuple)):
            errors.append(f"INVALID_TYPE:{dotted_path}")
        elif not value:
            errors.append(f"BLANK:{dotted_path}")
        else:
            for index, member in enumerate(value):
                member_path = f"{dotted_path}[{index}]"
                if _is_blank(member):
                    errors.append(f"BLANK:{member_path}")
                elif not isinstance(member, str):
                    errors.append(f"INVALID_TYPE:{member_path}")


def _validate_hash_values(record: Mapping[str, Any], errors: list[str]) -> None:
    for path in _HASH_VALUES:
        present, value = _value_at(record, path)
        if present and not _is_blank(value) and not _is_valid_hash_or_unknown(value):
            errors.append(f"INVALID_SHA256:{'.'.join(path)}")
    for path in _HASH_SEQUENCES:
        present, values = _value_at(record, path)
        if present and isinstance(values, (list, tuple)):
            for index, value in enumerate(values):
                if not _is_blank(value) and not _is_valid_hash_or_unknown(value):
                    errors.append(f"INVALID_SHA256:{'.'.join(path)}[{index}]")


def _validate_mapping_fields(
    record: Mapping[str, Any],
    family: str,
    names: Sequence[str],
    errors: list[str],
) -> None:
    value = record.get(family)
    if not isinstance(value, Mapping):
        if family not in record:
            errors.append(f"MISSING:{family}")
        elif _is_blank(value):
            errors.append(f"BLANK:{family}")
        else:
            errors.append(f"INVALID:{family}")
        return
    for name in names:
        path = f"{family}.{name}"
        if name not in value:
            errors.append(f"MISSING:{path}")
        elif _is_blank(value[name]):
            errors.append(f"BLANK:{path}")
        elif not isinstance(value[name], str):
            errors.append(f"INVALID_TYPE:{path}")


def _validate_mode_routes(record: Mapping[str, Any], errors: list[str]) -> None:
    mode_routes = record.get("mode_routes")
    if not isinstance(mode_routes, Mapping):
        errors.append("MISSING:mode_routes" if "mode_routes" not in record else "INVALID:mode_routes")
        return
    for mode in MODE_ROUTES:
        path = f"mode_routes.{mode}"
        if mode not in mode_routes:
            errors.append(f"MISSING:{path}")
            continue
        route = mode_routes[mode]
        if not isinstance(route, Mapping):
            errors.append(f"INVALID:{path}")
            continue
        scopes = record.get("mode_scope")
        scope = scopes.get(mode) if isinstance(scopes, Mapping) else None
        excluded = (
            isinstance(scope, Mapping)
            and scope.get("advertised") is False
            and scope.get("terminal_state") == "OUT_OF_SCOPE_WITH_PROOF"
        )
        for field in MODE_FIELDS:
            field_path = f"{path}.{field}"
            if field not in route:
                errors.append(f"MISSING:{field_path}")
            elif field in {"target_vrs", "target_paths", "payload_hashes"}:
                if not isinstance(route[field], (list, tuple)):
                    errors.append(f"INVALID_TYPE:{field_path}")
                elif not route[field] and not excluded:
                    errors.append(f"BLANK:{field_path}")
                else:
                    for index, member in enumerate(route[field]):
                        member_path = f"{field_path}[{index}]"
                        if _is_blank(member):
                            errors.append(f"BLANK:{member_path}")
                        elif not isinstance(member, str):
                            errors.append(f"INVALID_TYPE:{member_path}")
                        elif field == "payload_hashes" and not _is_valid_hash_or_unknown(member):
                            errors.append(f"INVALID_SHA256:{member_path}")
            elif _is_blank(route[field]):
                errors.append(f"BLANK:{field_path}")
            elif not isinstance(route[field], str):
                errors.append(f"INVALID_TYPE:{field_path}")
        if excluded and dict(route) != ZERO_CLAIM_MODE_ROUTE:
            errors.append(f"MODE_ROUTE_EXCLUSION_MISMATCH:{mode}")


def _validate_mode_scope(record: Mapping[str, Any], errors: list[str]) -> None:
    value = record.get("mode_scope")
    if not isinstance(value, Mapping):
        errors.append("MISSING:mode_scope" if "mode_scope" not in record else "INVALID:mode_scope")
        return
    for mode in RELEASE_MODES:
        if mode not in value:
            errors.append(f"MISSING:mode_scope.{mode}")
            continue
        scope = value[mode]
        if not isinstance(scope, Mapping):
            errors.append(f"INVALID:mode_scope.{mode}")
            continue
        for unexpected in sorted(set(scope) - {"advertised", "terminal_state"}):
            errors.append(f"UNEXPECTED:mode_scope.{mode}.{unexpected}")
        if "advertised" not in scope or not isinstance(scope.get("advertised"), bool):
            errors.append(f"INVALID_TYPE:mode_scope.{mode}.advertised")
        if scope.get("terminal_state") not in {"NONTERMINAL", "OUT_OF_SCOPE_WITH_PROOF"}:
            errors.append(f"INVALID_VALUE:mode_scope.{mode}.terminal_state")
    for unexpected in sorted(set(value) - set(RELEASE_MODES)):
        errors.append(f"UNEXPECTED:mode_scope.{unexpected}")


def _identity_fields_from_record(record: Mapping[str, Any]) -> CanonicalIdentityFields | None:
    source_module = record.get("source_module")
    creation_path = record.get("creation_path")
    classification = record.get("classification")
    body_tuple = record.get("body_tuple")
    source_route = record.get("source_route")
    required_mappings = (source_module, creation_path, classification, body_tuple, source_route)
    if not all(isinstance(value, Mapping) for value in required_mappings):
        return None
    ordered_vrs = source_route.get("ordered_vrs")
    body_values = tuple(body_tuple.get(name) for name in ("race", "sex", "body_type", "body_shape", "equipment_race"))
    if not isinstance(ordered_vrs, (list, tuple)) or not all(isinstance(value, str) for value in ordered_vrs):
        return None
    if not all(isinstance(value, str) for value in body_values):
        return None
    required_values = (
        source_module.get("uuid"),
        source_module.get("profile_digest"),
        creation_path.get("kind"),
        creation_path.get("root_uuid"),
        creation_path.get("stats_entry"),
        creation_path.get("chain_digest"),
        classification.get("effective_slot"),
        source_route.get("component_contract_digest"),
    )
    if not all(isinstance(value, str) for value in required_values):
        return None
    return CanonicalIdentityFields(
        source_module_uuid=source_module["uuid"],
        source_profile_digest=source_module["profile_digest"],
        creation_path_kind=creation_path["kind"],
        root_template_uuid=creation_path["root_uuid"],
        stats_entry=creation_path["stats_entry"],
        inheritance_digest=creation_path["chain_digest"],
        effective_slot=classification["effective_slot"],
        body_tuple=body_values,
        ordered_source_vrs=tuple(ordered_vrs),
        component_contract_digest=source_route["component_contract_digest"],
    )


def _contains_unknown_or_blocking(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_unknown_or_blocking(member) for member in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_unknown_or_blocking(member) for member in value)
    return _is_unknown_code(value)


def _validate_blocker_codes(
    record: Mapping[str, Any], errors: list[str], terminal_exclusion_valid: bool
) -> None:
    blocker_codes = record.get("blocker_codes")
    if not isinstance(blocker_codes, (list, tuple)):
        errors.append("INVALID_TYPE:blocker_codes")
        return
    for index, code in enumerate(blocker_codes):
        path = f"blocker_codes[{index}]"
        if _is_blank(code):
            errors.append(f"BLANK:{path}")
        elif not isinstance(code, str) or not BLOCKER_CODE_RE.fullmatch(code):
            errors.append(f"INVALID_BLOCKER_CODE:{path}")
    if not blocker_codes and not terminal_exclusion_valid and (
        bool(record.get("release_blocking")) or _contains_unknown_or_blocking(record)
    ):
        errors.append("BLOCKER_CODES_REQUIRED")


def _closed_mapping(
    value: object, *, allowed: frozenset[str], required: frozenset[str], path: str,
) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{path}:INVALID_TYPE"]
    errors = [f"{path}:MISSING:{key}" for key in sorted(required - set(value))]
    errors.extend(f"{path}:UNEXPECTED:{key}" for key in sorted(set(value) - allowed))
    return errors


StructuralContract = Callable[[object, str], list[str]]


def _mapping_contract(
    value: object, path: str, fields: Mapping[str, StructuralContract], *,
    optional: frozenset[str] = frozenset(),
) -> list[str]:
    """Apply one closed-object contract and recursively validate every field."""
    required = frozenset(fields) - optional
    errors = _closed_mapping(
        value, allowed=frozenset(fields), required=required, path=path,
    )
    if isinstance(value, Mapping):
        for name, contract in fields.items():
            if name in value:
                errors.extend(contract(value[name], f"{path}.{name}"))
    return errors


def _text_contract(value: object, path: str) -> list[str]:
    return [] if isinstance(value, str) and value else [f"{path}:INVALID_TYPE"]


def _hash_contract(value: object, path: str) -> list[str]:
    return [] if isinstance(value, str) and SHA256_RE.fullmatch(value) else [f"{path}:INVALID_TYPE"]


def _integer_contract(value: object, path: str) -> list[str]:
    return [] if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else [f"{path}:INVALID_TYPE"]


def _constant_contract(expected: object) -> StructuralContract:
    def validate(value: object, path: str) -> list[str]:
        if isinstance(expected, bool):
            valid = isinstance(value, bool) and value is expected
        elif isinstance(expected, int):
            valid = isinstance(value, int) and not isinstance(value, bool) and value == expected
        else:
            valid = value == expected
        return [] if valid else [f"{path}:INVALID_VALUE"]

    return validate


def _enum_contract(allowed: frozenset[object]) -> StructuralContract:
    def validate(value: object, path: str) -> list[str]:
        try:
            valid = value in allowed
        except TypeError:
            valid = False
        return [] if valid else [f"{path}:INVALID_VALUE"]

    return validate


def _pattern_contract(pattern: re.Pattern[str]) -> StructuralContract:
    def validate(value: object, path: str) -> list[str]:
        return [] if isinstance(value, str) and pattern.fullmatch(value) else [f"{path}:INVALID_TYPE"]

    return validate


def _sequence_contract(
    item_contract: StructuralContract, *, minimum: int = 0,
) -> StructuralContract:
    def validate(value: object, path: str) -> list[str]:
        if not isinstance(value, list):
            return [f"{path}:INVALID_TYPE"]
        errors = [f"{path}:INVALID_LENGTH"] if len(value) < minimum else []
        for index, item in enumerate(value):
            errors.extend(item_contract(item, f"{path}[{index}]"))
        return errors

    return validate


def _date_time_contract(value: object, path: str) -> list[str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        return [f"{path}:INVALID_TYPE"]
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return [f"{path}:INVALID_TYPE"]
    return [] if parsed.tzinfo is not None else [f"{path}:INVALID_TYPE"]


def _mapping_only_contract(value: object, path: str) -> list[str]:
    return [] if isinstance(value, Mapping) else [f"{path}:INVALID_TYPE"]


def _profile_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "id": _text_contract,
        "version": _text_contract,
        "sha256": _hash_contract,
    })


def _path_hash_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "path": _text_contract,
        "sha256": _hash_contract,
    })


def _link_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "result": _text_contract,
        "evidence_path": _text_contract,
        "evidence_sha256": _hash_contract,
    })


def _component_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "component_id": _text_contract,
        "status": _enum_contract(frozenset({"FAIL", "BLOCKED"})),
        "fixed_gates": _fixed_gates_contract,
        "evidence_path": _text_contract,
        "evidence_sha256": _hash_contract,
    })


def _architecture_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "method_id": _text_contract,
        "method_family": _text_contract,
        "implementation_path": _text_contract,
        "implementation_sha256": _hash_contract,
        "candidate_count": _integer_contract,
        "status": _constant_contract("FAILED_FIXED_GATES"),
        "component_contract_digest": _hash_contract,
        "components": _sequence_contract(_component_contract, minimum=1),
    })


def _fixed_gates_contract(value: object, path: str) -> list[str]:
    if isinstance(value, Mapping) and not value:
        return []
    return _mapping_contract(
        value, path, {gate: _link_contract for gate in TERMINAL_GATES},
    )


def _boundary_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "boundary_type": _enum_contract(frozenset({
            "FORBIDDEN_TARGET", "SHARED_ASSET", "COMPONENT", "MATERIAL",
            "BODY", "OBJECT",
        })),
        "record_field": _text_contract,
        "record_path": _text_contract,
        "record_value": _text_contract,
        "evidence_path": _text_contract,
        "evidence_sha256": _hash_contract,
    })


def _hard_contract_impossibility_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "result": _constant_contract("HARD_CONTRACT_IMPOSSIBILITY"),
        "protected_object_id": _text_contract,
        "protected_object_path": _text_contract,
        "protected_object_sha256": _hash_contract,
        "boundary_contract": _boundary_contract,
    })


def _evidence_contract(value: object, path: str) -> list[str]:
    return _mapping_contract(value, path, {
        "path": _text_contract,
        "sha256": _hash_contract,
        "claim": _text_contract,
    })


def _protected_impact_contract(value: object, path: str) -> list[str]:
    text_array = _sequence_contract(_text_contract)
    return _mapping_contract(value, path, {
        "registry_ids": text_array,
        "shared_consumers": text_array,
        "shared_assets": text_array,
        "forbidden_targets": text_array,
        "result": _constant_contract("NO_PROTECTED_MUTATION"),
    })


def _terminal_reason_proof_contract(event: Mapping[str, Any]) -> list[str]:
    proof = event.get("reason_proof")
    reason = event.get("reason")
    if reason == "SOURCE_ABSENT_EXACT_PROFILE":
        return _mapping_contract(proof, "reason_proof", {
            "exact_profile": _profile_contract,
            "complete_source_inventory": _link_contract,
            "zero_route_result": _link_contract,
            "anti_omission": _link_contract,
        })
    if reason == "NO_RELEASE_PERMISSION":
        return _mapping_contract(proof, "reason_proof", {
            "permission_text": _path_hash_contract,
            "permission_result": _constant_contract("PROHIBITED"),
            "requested_operations": _sequence_contract(
                _enum_contract(frozenset({"DERIVATIVE", "REDISTRIBUTION"})),
                minimum=1,
            ),
            "date": _text_contract,
            "credit": _text_contract,
            "derivative_scope": _enum_contract(frozenset({
                "NO_DERIVATIVES", "DERIVATIVE_DENIED", "ALLOWED",
            })),
            "redistribution_scope": _enum_contract(frozenset({
                "NO_REDISTRIBUTION", "REDISTRIBUTION_DENIED", "ALLOWED",
            })),
            "exact_source_version": _text_contract,
        })
    if reason == "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE":
        return _mapping_contract(proof, "reason_proof", {
            "exact_slot": _text_contract,
            "exact_body_tuple": _sequence_contract(_text_contract, minimum=1),
            "source_contract": _text_contract,
            "release_scope_mismatch": _text_contract,
        })
    if reason == "PROTECTED_NATIVE_ONLY":
        return _mapping_contract(proof, "reason_proof", {
            "protected_registry_id": _text_contract,
            "protected_consumer": _text_contract,
            "protected_route": _text_contract,
            "protected_path": _text_contract,
            "protected_sha256": _hash_contract,
            "forbidden_target": _text_contract,
            "new_target": _text_contract,
        })
    if reason == "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT":
        searched_contracts = {
            name: _link_contract for name in (
                "root_templates", "named_stats", "inheritance", "visual_banks",
                "ordered_components", "provider_maps", "uuid_path_hash_aliases",
            )
        }
        return _mapping_contract(proof, "reason_proof", {
            "exact_profile": _profile_contract,
            "searched_contracts": lambda value, path: _mapping_contract(
                value, path, searched_contracts,
            ),
            "search_result": _link_contract,
            "anti_omission": _link_contract,
            "anti_omission_pass": _constant_contract(True),
        })
    if reason == "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE":
        return _mapping_contract(proof, "reason_proof", {
            "selected_profile_id": _text_contract,
            "alternate_profile_id": _text_contract,
            "forbidden_module_relationship": _constant_contract("MUTUALLY_EXCLUSIVE"),
            "alternate_artifact": _path_hash_contract,
        })
    if reason == "NO_SAFE_GEOMETRY_AVAILABLE":
        hard_contract = isinstance(proof, Mapping) and isinstance(
            proof.get("hard_contract_impossibility"), Mapping
        )
        return _mapping_contract(proof, "reason_proof", {
            "expected_components": _sequence_contract(_text_contract, minimum=1),
            "component_contract_digest": _hash_contract,
            "hard_contract_impossibility": _hard_contract_impossibility_contract,
            "architecture_results": _sequence_contract(_architecture_contract),
            "fixed_gates": _fixed_gates_contract,
            "final_available_safe_tooling_failure": _link_contract,
        }, optional=(
            frozenset({
                "expected_components", "component_contract_digest",
                "final_available_safe_tooling_failure",
            })
            if hard_contract else frozenset({"hard_contract_impossibility"})
        ))
    return ["reason_proof:UNKNOWN_REASON"]


def _terminal_schema_contract_errors(event: Mapping[str, Any]) -> list[str]:
    errors = _mapping_contract(event, "event", {
        "schema": _constant_contract("clothmorph.terminal-exclusion"),
        "schema_version": _constant_contract(1),
        "event_id": _pattern_contract(EXCLUSION_EVENT_ID_RE),
        "record_id": _pattern_contract(re.compile(r"^LEDGER_[0-9A-F]{64}$")),
        "identity_sha256": _hash_contract,
        "source_profile_id": _text_contract,
        "mode": _enum_contract(frozenset(EXCLUSION_MODES)),
        "reason": _enum_contract(frozenset(EXCLUSION_REASONS)),
        "reason_proof": _mapping_only_contract,
        "scope_statement": _text_contract,
        "attempted_architectures": _sequence_contract(_architecture_contract),
        "fixed_acceptance_gates": _fixed_gates_contract,
        "evidence": _sequence_contract(_evidence_contract, minimum=1),
        "protected_impact": _protected_impact_contract,
        "next_project_if_reopened": _text_contract,
        "approved_by": _text_contract,
        "approved_reason": _text_contract,
        "created_utc": _date_time_contract,
        "event_type": _constant_contract("EXCLUSION"),
    }, optional=frozenset({"event_type"}))
    if event.get("reason") != "NO_SAFE_GEOMETRY_AVAILABLE" and (
        event.get("attempted_architectures") != [] or event.get("fixed_acceptance_gates") != {}
    ):
        errors.append("event:NON_GEOMETRY_ARCHITECTURES_OR_GATES")
    errors.extend(_terminal_reason_proof_contract(event))
    return errors


def _validate_terminal_exclusion(
    record: Mapping[str, Any], errors: list[str], *,
    verified_evidence: Mapping[str, str] | None,
    discovered_event_files: Mapping[str, str] | None,
    independent_provider_claims: Mapping[object, object] | None,
    independent_package_claims: Mapping[object, object] | None,
    provider_authority_present: bool | None,
    provider_authority_complete: bool | None,
    package_authority_present: bool | None,
    package_authority_complete: bool | None,
) -> bool:
    """Validate every per-mode attachment and return record-wide exclusion closure."""
    if "terminal_exclusion" not in record:
        errors.append("MISSING:terminal_exclusion")
        return False
    value = record.get("terminal_exclusion")
    if not isinstance(value, Mapping):
        errors.append("INVALID:terminal_exclusion")
        return False
    map_shape_errors = _closed_mapping(
        value,
        allowed=frozenset(RELEASE_MODES),
        required=frozenset(RELEASE_MODES),
        path="terminal_exclusion",
    )
    errors.extend(
        f"TERMINAL_EXCLUSION_SCHEMA:{error}" for error in map_shape_errors
    )
    attached_modes = [mode for mode in RELEASE_MODES if value.get(mode) is not None]
    if attached_modes and (
        verified_evidence is None or discovered_event_files is None
    ):
        errors.append("MISSING_TERMINAL_EXCLUSION_VALIDATION_CONTEXT")
        return False

    valid_modes: set[str] = set()
    scopes = record.get("mode_scope")
    for mode in RELEASE_MODES:
        summary = value.get(mode)
        scope = scopes.get(mode) if isinstance(scopes, Mapping) else None
        if summary is None:
            if (
                isinstance(scope, Mapping)
                and scope.get("terminal_state") == "OUT_OF_SCOPE_WITH_PROOF"
            ):
                errors.append(f"MISSING_VALID_TERMINAL_EXCLUSION:{mode}")
            continue
        mode_valid = True
        summary_shape_errors = _closed_mapping(
            summary,
            allowed=frozenset({"event", "event_file"}),
            required=frozenset({"event", "event_file"}),
            path=f"terminal_exclusion.{mode}",
        )
        errors.extend(
            f"TERMINAL_EXCLUSION_SCHEMA:{error}"
            for error in summary_shape_errors
        )
        if summary_shape_errors:
            mode_valid = False
        event = summary.get("event") if isinstance(summary, Mapping) else None
        file_provenance = (
            summary.get("event_file") if isinstance(summary, Mapping) else None
        )
        if not isinstance(event, Mapping):
            errors.append(f"TERMINAL_EXCLUSION_EVENT_INVALID:{mode}:INVALID:event")
            mode_valid = False
        else:
            for error in _terminal_schema_contract_errors(event):
                errors.append(f"TERMINAL_EXCLUSION_SCHEMA:{error}")
                mode_valid = False
            assert verified_evidence is not None
            for error in validate_exclusion_event(
                event,
                ledger_record=record,
                evidence_hashes=verified_evidence,
                lifecycle="attached",
                independent_provider_claims=independent_provider_claims,
                independent_package_claims=independent_package_claims,
                provider_authority_present=provider_authority_present,
                provider_authority_complete=provider_authority_complete,
                package_authority_present=package_authority_present,
                package_authority_complete=package_authority_complete,
            ):
                errors.append(f"TERMINAL_EXCLUSION_EVENT_INVALID:{error}")
                mode_valid = False
            if event.get("mode") != mode:
                errors.append(f"TERMINAL_EXCLUSION_MODE_MISMATCH:{mode}")
                mode_valid = False
        if not isinstance(file_provenance, Mapping):
            errors.append(f"TERMINAL_EXCLUSION_EVENT_FILE_INVALID:{mode}")
            mode_valid = False
            continue
        file_shape_errors = _closed_mapping(
            file_provenance,
            allowed=frozenset({
                "relative_path", "sha256", "canonical_event_sha256",
            }),
            required=frozenset({
                "relative_path", "sha256", "canonical_event_sha256",
            }),
            path=f"terminal_exclusion.{mode}.event_file",
        )
        errors.extend(
            f"TERMINAL_EXCLUSION_SCHEMA:{error}" for error in file_shape_errors
        )
        if file_shape_errors:
            mode_valid = False
        relative_path = file_provenance.get("relative_path")
        digest = file_provenance.get("sha256")
        canonical_digest = file_provenance.get("canonical_event_sha256")
        if (
            not isinstance(relative_path, str) or not relative_path
            or relative_path.startswith(("/", "\\")) or ".." in relative_path.replace("\\", "/").split("/")
            or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
            or not isinstance(canonical_digest, str) or SHA256_RE.fullmatch(canonical_digest) is None
            or not isinstance(event, Mapping)
            or canonical_digest != sha256_text(canonical_json(event))
            or discovered_event_files is None
            or discovered_event_files.get(relative_path) != digest
        ):
            errors.append(f"TERMINAL_EXCLUSION_EVENT_FILE_INVALID:{mode}")
            mode_valid = False
        if not (
            isinstance(scope, Mapping)
            and scope.get("advertised") is False
            and scope.get("terminal_state") == "OUT_OF_SCOPE_WITH_PROOF"
        ):
            errors.append(f"TERMINAL_EXCLUSION_STATE_MISMATCH:{mode}")
            mode_valid = False
        if mode_valid:
            valid_modes.add(mode)

    record_closed = len(valid_modes) == len(RELEASE_MODES) and not map_shape_errors
    state_claims_record_closure = (
        record.get("disposition") == "OUT_OF_SCOPE_WITH_PROOF"
        or (
            record.get("release_blocking") is False
            and record.get("disposition") not in NON_EXCLUSION_TERMINAL_DISPOSITIONS
        )
    )
    if record_closed and (
        record.get("disposition") != "OUT_OF_SCOPE_WITH_PROOF"
        or record.get("release_blocking") is not False
    ):
        errors.append("TERMINAL_EXCLUSION_STATE_MISMATCH")
        return False
    if not record_closed and state_claims_record_closure:
        errors.append("MISSING_VALID_TERMINAL_EXCLUSION")
    return record_closed


def validate_record(
    record: dict[str, object], *, verified_evidence: Mapping[str, str] | None = None,
    discovered_event_files: Mapping[str, str] | None = None,
    independent_provider_claims: Mapping[object, object] | None = None,
    independent_package_claims: Mapping[object, object] | None = None,
    provider_authority_present: bool | None = None,
    provider_authority_complete: bool | None = None,
    package_authority_present: bool | None = None,
    package_authority_complete: bool | None = None,
) -> list[str]:
    """Return stable errors for an emitted record; an empty list is valid."""
    if not isinstance(record, dict):
        return ["INVALID:record"]

    errors: list[str] = []
    _validate_text_values(record, errors)
    _validate_sequence_values(record, errors)
    _validate_mapping_fields(record, "gates", _GATES, errors)
    _validate_mode_scope(record, errors)
    _validate_mode_routes(record, errors)
    _validate_hash_values(record, errors)

    for family in ("permission", "protected_relations", "transformation"):
        if family not in record:
            errors.append(f"MISSING:{family}")
        elif _is_blank(record[family]):
            errors.append(f"BLANK:{family}")
        elif not isinstance(record[family], Mapping):
            errors.append(f"INVALID:{family}")

    if "release_blocking" not in record:
        errors.append("MISSING:release_blocking")
    elif not isinstance(record["release_blocking"], bool):
        errors.append("INVALID_TYPE:release_blocking")

    if "disposition" not in record:
        errors.append("MISSING:disposition")
    elif _is_blank(record["disposition"]):
        errors.append("BLANK:disposition")
    elif not isinstance(record["disposition"], str):
        errors.append("INVALID_TYPE:disposition")
    elif record["disposition"] == "UNCLASSIFIED":
        errors.append("FORBIDDEN_DISPOSITION:UNCLASSIFIED")
    elif record["disposition"] not in DISPOSITIONS:
        errors.append(f"INVALID_DISPOSITION:{record['disposition']}")

    terminal_exclusion_valid = _validate_terminal_exclusion(
        record,
        errors,
        verified_evidence=verified_evidence,
        discovered_event_files=discovered_event_files,
        independent_provider_claims=independent_provider_claims,
        independent_package_claims=independent_package_claims,
        provider_authority_present=provider_authority_present,
        provider_authority_complete=provider_authority_complete,
        package_authority_present=package_authority_present,
        package_authority_complete=package_authority_complete,
    )
    _validate_blocker_codes(record, errors, terminal_exclusion_valid)

    fields = _identity_fields_from_record(record)
    if fields is not None:
        canonical_identity, identity_sha256 = build_identity(fields)
        if (
            record.get("canonical_identity") != canonical_identity
            or record.get("identity_sha256") != identity_sha256
        ):
            errors.append("IDENTITY_MISMATCH")

    return errors


def validate_generated_ledger(
    document: object, *, verified_evidence: Mapping[str, str] | None = None,
    discovered_event_files: Mapping[str, str] | None = None,
    independent_provider_claims: Mapping[object, object] | None = None,
    independent_package_claims: Mapping[object, object] | None = None,
    provider_authority_present: bool | None = None,
    provider_authority_complete: bool | None = None,
    package_authority_present: bool | None = None,
    package_authority_complete: bool | None = None,
) -> list[str]:
    """Validate a complete generated ledger envelope and every record."""
    if not isinstance(document, Mapping):
        return ["INVALID:document"]
    errors: list[str] = []
    if document.get("schema_version") != 1 or isinstance(document.get("schema_version"), bool):
        errors.append("INVALID:schema_version")
    for key, expected in (("summary", Mapping), ("blockers", list), ("records", list)):
        if key not in document:
            errors.append(f"MISSING:{key}")
        elif not isinstance(document[key], expected):
            errors.append(f"INVALID:{key}")
    records = document.get("records")
    if isinstance(records, list):
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                errors.append(f"RECORD[{index}]:INVALID:record")
                continue
            errors.extend(
                f"RECORD[{index}]:{error}"
                for error in validate_record(
                    dict(record),
                    verified_evidence=verified_evidence,
                    discovered_event_files=discovered_event_files,
                    independent_provider_claims=independent_provider_claims,
                    independent_package_claims=independent_package_claims,
                    provider_authority_present=provider_authority_present,
                    provider_authority_complete=provider_authority_complete,
                    package_authority_present=package_authority_present,
                    package_authority_complete=package_authority_complete,
                )
            )
        summary = document.get("summary")
        if isinstance(summary, Mapping) and summary.get("record_count") != len(records):
            errors.append("SUMMARY_MISMATCH:record_count")
    return errors
