"""Standard-library validation for public release-ledger records."""

import re
from collections.abc import Mapping
from typing import Any


DISPOSITIONS = frozenset(
    {
        "ACCEPTED / PROTECT",
        "READY FOR TEST",
        "CONFIRMED DEFECT / CORRECT",
        "MISSING ROUTE / BUILD",
        "DEFERRED WITH CAUSE",
        "OUT OF SCOPE",
    }
)
MODE_ROUTES = ("vanilla", "sbbf", "bcb", "external")
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")

_REQUIRED_VALUES = (
    ("identity",),
    ("identity_fields", "source_module_uuid"),
    ("identity_fields", "source_profile_digest"),
    ("identity_fields", "creation_path_kind"),
    ("identity_fields", "root_template_uuid"),
    ("identity_fields", "stats_entry"),
    ("identity_fields", "inheritance_digest"),
    ("identity_fields", "effective_slot"),
    ("identity_fields", "body_tuple"),
    ("identity_fields", "ordered_source_vrs"),
    ("identity_fields", "component_contract_digest"),
    ("source_module", "uuid"),
    ("source_module", "profile_digest"),
    ("creation_path", "kind"),
    ("creation_path", "root_template_uuid"),
    ("creation_path", "stats_entry"),
    ("creation_path", "inheritance_digest"),
    ("classification", "effective_slot"),
    ("classification", "body_tuple"),
    ("component_contract", "digest"),
    ("disposition",),
    ("next_action",),
)

_SHA256_VALUES = (
    ("identity",),
    ("identity_fields", "source_profile_digest"),
    ("identity_fields", "inheritance_digest"),
    ("identity_fields", "component_contract_digest"),
    ("source_module", "profile_digest"),
    ("creation_path", "inheritance_digest"),
    ("component_contract", "digest"),
)


def _value_at(record: Mapping[str, Any], path: tuple[str, ...]) -> tuple[bool, object]:
    current: object = record
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == [] or value == ()


def validate_record(record: dict[str, object]) -> list[str]:
    """Return stable errors for an emitted record; an empty list is valid."""
    if not isinstance(record, dict):
        return ["INVALID:record"]

    errors: list[str] = []
    for path in _REQUIRED_VALUES:
        present, value = _value_at(record, path)
        dotted_path = ".".join(path)
        if not present:
            errors.append(f"MISSING:{dotted_path}")
        elif _is_blank(value):
            errors.append(f"BLANK:{dotted_path}")

    for path in _SHA256_VALUES:
        present, value = _value_at(record, path)
        if present and not _is_blank(value) and (
            not isinstance(value, str) or not SHA256_RE.fullmatch(value)
        ):
            errors.append(f"INVALID_SHA256:{'.'.join(path)}")

    mode_routes = record.get("mode_routes")
    if isinstance(mode_routes, Mapping):
        for mode in MODE_ROUTES:
            if mode not in mode_routes:
                errors.append(f"MISSING:mode_routes.{mode}")
    else:
        errors.append("INVALID:mode_routes")

    disposition = record.get("disposition")
    if disposition == "UNCLASSIFIED":
        errors.append("FORBIDDEN_DISPOSITION:UNCLASSIFIED")
    elif isinstance(disposition, str) and disposition and disposition not in DISPOSITIONS:
        errors.append(f"INVALID_DISPOSITION:{disposition}")

    return errors
