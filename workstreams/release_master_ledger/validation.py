"""Standard-library validation for public release-ledger records."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .exclusions import EXCLUSION_MODES, EXCLUSION_REASONS, validate_exclusion_event
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
MODE_ROUTES = ("vanilla", "sbbf", "bcb", "external")
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
TERMINAL_EVENT_FIELDS = frozenset({
    "schema", "schema_version", "event_id", "record_id", "identity_sha256",
    "source_profile_id", "mode", "reason", "reason_proof", "scope_statement",
    "attempted_architectures", "fixed_acceptance_gates", "evidence",
    "protected_impact", "next_project_if_reopened", "approved_by",
    "approved_reason", "created_utc", "event_type",
})
TERMINAL_EVENT_REQUIRED = TERMINAL_EVENT_FIELDS - {"event_type"}
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
        for field in MODE_FIELDS:
            field_path = f"{path}.{field}"
            if field not in route:
                errors.append(f"MISSING:{field_path}")
            elif _is_blank(route[field]):
                errors.append(f"BLANK:{field_path}")
            elif field in {"target_vrs", "target_paths", "payload_hashes"}:
                if not isinstance(route[field], (list, tuple)):
                    errors.append(f"INVALID_TYPE:{field_path}")
                else:
                    for index, member in enumerate(route[field]):
                        member_path = f"{field_path}[{index}]"
                        if _is_blank(member):
                            errors.append(f"BLANK:{member_path}")
                        elif not isinstance(member, str):
                            errors.append(f"INVALID_TYPE:{member_path}")
                        elif field == "payload_hashes" and not _is_valid_hash_or_unknown(member):
                            errors.append(f"INVALID_SHA256:{member_path}")
            elif not isinstance(route[field], str):
                errors.append(f"INVALID_TYPE:{field_path}")


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


def _link_contract(value: object, path: str) -> list[str]:
    errors = _closed_mapping(
        value, allowed=frozenset({"result", "evidence_path", "evidence_sha256"}),
        required=frozenset({"result", "evidence_path", "evidence_sha256"}), path=path,
    )
    if isinstance(value, Mapping) and (
        not isinstance(value.get("result"), str) or not value["result"]
        or not isinstance(value.get("evidence_path"), str) or not value["evidence_path"]
        or not isinstance(value.get("evidence_sha256"), str)
        or SHA256_RE.fullmatch(value["evidence_sha256"]) is None
    ):
        errors.append(f"{path}:INVALID_FIELDS")
    return errors


def _terminal_reason_proof_contract(event: Mapping[str, Any]) -> list[str]:
    proof = event.get("reason_proof")
    reason = event.get("reason")
    if reason == "SOURCE_ABSENT_EXACT_PROFILE":
        errors = _closed_mapping(proof, allowed=frozenset({"exact_profile", "complete_source_inventory", "zero_route_result", "anti_omission"}), required=frozenset({"exact_profile", "complete_source_inventory", "zero_route_result", "anti_omission"}), path="reason_proof")
        if isinstance(proof, Mapping):
            errors.extend(_closed_mapping(proof.get("exact_profile"), allowed=frozenset({"id", "version", "sha256"}), required=frozenset({"id", "version", "sha256"}), path="reason_proof.exact_profile"))
            for name in ("complete_source_inventory", "zero_route_result", "anti_omission"):
                errors.extend(_link_contract(proof.get(name), f"reason_proof.{name}"))
        return errors
    if reason == "NO_RELEASE_PERMISSION":
        return _closed_mapping(proof, allowed=frozenset({"permission_text", "permission_result", "requested_operations", "date", "credit", "derivative_scope", "redistribution_scope", "exact_source_version"}), required=frozenset({"permission_text", "permission_result", "requested_operations", "date", "credit", "derivative_scope", "redistribution_scope", "exact_source_version"}), path="reason_proof")
    if reason == "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE":
        return _closed_mapping(proof, allowed=frozenset({"exact_slot", "exact_body_tuple", "source_contract", "release_scope_mismatch"}), required=frozenset({"exact_slot", "exact_body_tuple", "source_contract", "release_scope_mismatch"}), path="reason_proof")
    if reason == "PROTECTED_NATIVE_ONLY":
        fields = frozenset({"protected_registry_id", "protected_consumer", "protected_route", "protected_path", "protected_sha256", "forbidden_target", "new_target"})
        return _closed_mapping(proof, allowed=fields, required=fields, path="reason_proof")
    if reason == "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT":
        errors = _closed_mapping(proof, allowed=frozenset({"exact_profile", "searched_contracts", "search_result", "anti_omission", "anti_omission_pass"}), required=frozenset({"exact_profile", "searched_contracts", "search_result", "anti_omission", "anti_omission_pass"}), path="reason_proof")
        if isinstance(proof, Mapping):
            errors.extend(_closed_mapping(proof.get("exact_profile"), allowed=frozenset({"id", "version", "sha256"}), required=frozenset({"id", "version", "sha256"}), path="reason_proof.exact_profile"))
            contracts = proof.get("searched_contracts")
            names = frozenset({"root_templates", "named_stats", "inheritance", "visual_banks", "ordered_components", "provider_maps", "uuid_path_hash_aliases"})
            errors.extend(_closed_mapping(contracts, allowed=names, required=names, path="reason_proof.searched_contracts"))
            if isinstance(contracts, Mapping):
                for name in names:
                    errors.extend(_link_contract(contracts.get(name), f"reason_proof.searched_contracts.{name}"))
            for name in ("search_result", "anti_omission"):
                errors.extend(_link_contract(proof.get(name), f"reason_proof.{name}"))
        return errors
    if reason == "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE":
        return _closed_mapping(proof, allowed=frozenset({"selected_profile_id", "alternate_profile_id", "forbidden_module_relationship", "alternate_artifact"}), required=frozenset({"selected_profile_id", "alternate_profile_id", "forbidden_module_relationship", "alternate_artifact"}), path="reason_proof")
    if reason == "NO_SAFE_GEOMETRY_AVAILABLE":
        allowed = frozenset({"hard_contract_impossibility", "architecture_results", "fixed_gates", "final_available_safe_tooling_failure"})
        errors = _closed_mapping(proof, allowed=allowed, required=frozenset({"architecture_results", "fixed_gates"}), path="reason_proof")
        if isinstance(proof, Mapping):
            architectures = proof.get("architecture_results")
            if not isinstance(architectures, list):
                errors.append("reason_proof.architecture_results:INVALID_TYPE")
            else:
                fields = frozenset({"method_id", "method_family", "implementation_path", "implementation_sha256", "candidate_count", "status", "components"})
                for index, result in enumerate(architectures):
                    errors.extend(_closed_mapping(result, allowed=fields, required=fields, path=f"reason_proof.architecture_results[{index}]"))
                    if isinstance(result, Mapping):
                        components = result.get("components")
                        if not isinstance(components, list) or not components:
                            errors.append(f"reason_proof.architecture_results[{index}].components:INVALID_TYPE")
                        else:
                            for component_index, component in enumerate(components):
                                errors.extend(_closed_mapping(component, allowed=frozenset({"component_id", "status", "evidence_path", "evidence_sha256"}), required=frozenset({"component_id", "status", "evidence_path", "evidence_sha256"}), path=f"reason_proof.architecture_results[{index}].components[{component_index}]"))
            gates = proof.get("fixed_gates")
            errors.extend(_closed_mapping(gates, allowed=frozenset(TERMINAL_GATES), required=frozenset(TERMINAL_GATES) if architectures else frozenset(), path="reason_proof.fixed_gates"))
            if isinstance(gates, Mapping):
                for gate in gates:
                    errors.extend(_closed_mapping(gates[gate], allowed=frozenset({"result", "evidence_path", "evidence_sha256"}), required=frozenset({"result", "evidence_path", "evidence_sha256"}), path=f"reason_proof.fixed_gates.{gate}"))
        return errors
    return ["reason_proof:UNKNOWN_REASON"]


def _terminal_schema_contract_errors(event: Mapping[str, Any]) -> list[str]:
    errors = _closed_mapping(event, allowed=TERMINAL_EVENT_FIELDS, required=TERMINAL_EVENT_REQUIRED, path="event")
    evidence = event.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("event.evidence:INVALID_TYPE")
    else:
        for index, item in enumerate(evidence):
            errors.extend(_closed_mapping(item, allowed=frozenset({"path", "sha256", "claim"}), required=frozenset({"path", "sha256", "claim"}), path=f"event.evidence[{index}]"))
    impact = event.get("protected_impact")
    required_impact = frozenset({"registry_ids", "shared_consumers", "forbidden_targets", "result"})
    errors.extend(_closed_mapping(impact, allowed=required_impact, required=required_impact, path="event.protected_impact"))
    if isinstance(impact, Mapping):
        for name in ("registry_ids", "shared_consumers", "forbidden_targets"):
            value = impact.get(name)
            if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
                errors.append(f"event.protected_impact.{name}:INVALID_TYPE")
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
) -> bool:
    """Validate a selected Task-1 event and the immutable event-file provenance."""
    if "terminal_exclusion" not in record:
        errors.append("MISSING:terminal_exclusion")
        return False
    value = record.get("terminal_exclusion")
    requires_event = (
        record.get("disposition") == "OUT_OF_SCOPE_WITH_PROOF"
        or (
            record.get("release_blocking") is False
            and record.get("disposition") not in NON_EXCLUSION_TERMINAL_DISPOSITIONS
        )
    )
    if value is None:
        if requires_event:
            errors.append("MISSING_VALID_TERMINAL_EXCLUSION")
        return False
    if not isinstance(value, Mapping):
        errors.append("INVALID:terminal_exclusion")
        return False
    if verified_evidence is None or discovered_event_files is None:
        errors.append("MISSING_TERMINAL_EXCLUSION_VALIDATION_CONTEXT")
        return False
    event = value.get("event")
    file_provenance = value.get("event_file")
    valid = isinstance(event, Mapping) and isinstance(file_provenance, Mapping)
    if not isinstance(event, Mapping):
        errors.append("TERMINAL_EXCLUSION_EVENT_INVALID:INVALID:event")
    if not isinstance(file_provenance, Mapping):
        errors.append("TERMINAL_EXCLUSION_EVENT_FILE_INVALID")
    if isinstance(event, Mapping):
        for error in _terminal_schema_contract_errors(event):
            errors.append(f"TERMINAL_EXCLUSION_SCHEMA:{error}")
            valid = False
        for error in validate_exclusion_event(
            event, ledger_record=record, evidence_hashes=verified_evidence
        ):
            errors.append(f"TERMINAL_EXCLUSION_EVENT_INVALID:{error}")
            valid = False
    if isinstance(file_provenance, Mapping):
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
            or discovered_event_files.get(relative_path) != digest
        ):
            errors.append("TERMINAL_EXCLUSION_EVENT_FILE_INVALID")
            valid = False
    if isinstance(event, Mapping) and event.get("mode") not in EXCLUSION_MODES:
        errors.append("TERMINAL_EXCLUSION_EVENT_INVALID:INVALID_MODE")
        valid = False
    if isinstance(event, Mapping) and event.get("reason") not in EXCLUSION_REASONS:
        errors.append("TERMINAL_EXCLUSION_EVENT_INVALID:INVALID_EXCLUSION_REASON")
        valid = False
    if valid and (record.get("disposition") != "OUT_OF_SCOPE_WITH_PROOF" or record.get("release_blocking") is not False):
        errors.append("TERMINAL_EXCLUSION_STATE_MISMATCH")
        valid = False
    elif not valid and requires_event:
        errors.append("MISSING_VALID_TERMINAL_EXCLUSION")
    return valid


def validate_record(
    record: dict[str, object], *, verified_evidence: Mapping[str, str] | None = None,
    discovered_event_files: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable errors for an emitted record; an empty list is valid."""
    if not isinstance(record, dict):
        return ["INVALID:record"]

    errors: list[str] = []
    _validate_text_values(record, errors)
    _validate_sequence_values(record, errors)
    _validate_mapping_fields(record, "gates", _GATES, errors)
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
                )
            )
        summary = document.get("summary")
        if isinstance(summary, Mapping) and summary.get("record_count") != len(records):
            errors.append("SUMMARY_MISMATCH:record_count")
    return errors
