"""Standard-library validation for public release-ledger records."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .identity import build_identity
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


def _validate_blocker_codes(record: Mapping[str, Any], errors: list[str]) -> None:
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
    if not blocker_codes and (
        bool(record.get("release_blocking")) or _contains_unknown_or_blocking(record)
    ):
        errors.append("BLOCKER_CODES_REQUIRED")


def validate_record(record: dict[str, object]) -> list[str]:
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

    _validate_blocker_codes(record, errors)

    fields = _identity_fields_from_record(record)
    if fields is not None:
        canonical_identity, identity_sha256 = build_identity(fields)
        if (
            record.get("canonical_identity") != canonical_identity
            or record.get("identity_sha256") != identity_sha256
        ):
            errors.append("IDENTITY_MISMATCH")

    return errors
