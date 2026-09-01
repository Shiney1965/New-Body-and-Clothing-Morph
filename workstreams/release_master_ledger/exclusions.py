"""Fail-closed validation and selection of terminal-exclusion events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
import posixpath
import re

from .identity import canonical_json, sha256_text


EXCLUSION_SCHEMA = "clothmorph.terminal-exclusion"
EXCLUSION_SCHEMA_VERSION = 1
EXCLUSION_REASONS = frozenset({
    "SOURCE_ABSENT_EXACT_PROFILE", "NO_RELEASE_PERMISSION",
    "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE", "PROTECTED_NATIVE_ONLY",
    "NO_SAFE_GEOMETRY_AVAILABLE", "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT",
    "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE",
})
EXCLUSION_MODES = frozenset({"vanilla", "sbbf", "bcb", "external", "source"})
PROTECTED_DISPOSITIONS = frozenset({
    "ACCEPTED_PROTECTED", "SOURCE_NATIVE_PROTECTED", "PACKAGE_ONLY_PROTECTED",
    "SHIPPED_NATIVE_PASSTHROUGH",
})
GEOMETRY_GATES = (
    "topology", "component", "material", "skin", "clearance", "silhouette",
    "deterministic_readback", "nontriviality",
)
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
RECORD_ID_RE = re.compile(r"^LEDGER_[0-9A-F]{64}$")
TIEFLING_PAK = "ClothMorphTieflingBT1_TEST.pak"
TIEFLING_UUID = "b57bab2c-5679-5445-8fee-ca8c282990a5"
TIEFLING_SHA256 = "01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141"


@dataclass(frozen=True)
class ExclusionSelection:
    """The sole current event for a route, or a fail-closed error set."""

    event: Mapping[str, object] | None
    errors: tuple[str, ...] = ()


def canonical_exclusion_payload(event: Mapping[str, object]) -> str:
    """Serialize all digest-bound fields, omitting only the self-referential ID."""
    return canonical_json({key: value for key, value in event.items() if key != "event_id"})


def exclusion_event_id(event: Mapping[str, object]) -> str:
    """Return the uppercase ID bound to the complete canonical event payload."""
    return f"EXCLUSION_{sha256_text(canonical_exclusion_payload(event))}"


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == ()


def _record_mapping(record: object) -> Mapping[str, object] | None:
    if isinstance(record, Mapping):
        return record
    to_dict = getattr(record, "to_dict", None)
    candidate = to_dict() if callable(to_dict) else None
    return candidate if isinstance(candidate, Mapping) else None


def _profile_id(record: Mapping[str, object]) -> object:
    module = record.get("source_module")
    return module.get("profile_id", module.get("folder")) if isinstance(module, Mapping) else None


def _normal_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    normalized = posixpath.normpath(value.replace("\\", "/"))
    if normalized in {".", ".."} or normalized.startswith("../") or normalized.startswith("/"):
        return None
    return normalized


def _verified_registry(value: object, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        errors.append("INVALID_VERIFIED_EVIDENCE_REGISTRY")
        return {}
    registry: dict[str, str] = {}
    for path, digest in value.items():
        normalized = _normal_path(path)
        if normalized is None or normalized != path or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append("INVALID_VERIFIED_EVIDENCE_REGISTRY")
            return {}
        registry[normalized] = digest
    return registry


def _validate_text(event: Mapping[str, object], field: str, errors: list[str]) -> None:
    if field not in event:
        errors.append(f"MISSING:{field}")
    elif _is_blank(event[field]):
        errors.append(f"BLANK:{field}")
    elif not isinstance(event[field], str):
        errors.append(f"INVALID_TYPE:{field}")


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return None


def _validate_link(value: object, registry: Mapping[str, str], event_links: set[tuple[str, str]]) -> bool:
    if not isinstance(value, Mapping):
        return False
    path = value.get("evidence_path", value.get("path"))
    digest = value.get("evidence_sha256", value.get("sha256"))
    normalized = _normal_path(path)
    return (
        normalized is not None and normalized == path and isinstance(digest, str)
        and registry.get(normalized) == digest and (normalized, digest) in event_links
    )


def _validate_event_evidence(
    event: Mapping[str, object], registry: Mapping[str, str], errors: list[str]
) -> set[tuple[str, str]]:
    evidence = event.get("evidence")
    links: set[tuple[str, str]] = set()
    if not isinstance(evidence, (list, tuple)):
        errors.append("INVALID:evidence")
        return links
    if not evidence:
        errors.append("EVIDENCE_REQUIRED")
        return links
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            errors.append(f"INVALID:evidence[{index}]")
            continue
        path, digest, claim = item.get("path"), item.get("sha256"), item.get("claim")
        for field, value in (("path", path), ("sha256", digest), ("claim", claim)):
            if _is_blank(value):
                errors.append(f"BLANK:evidence[{index}].{field}")
            elif not isinstance(value, str):
                errors.append(f"INVALID_TYPE:evidence[{index}].{field}")
        normalized = _normal_path(path)
        if normalized is None or normalized != path:
            errors.append(f"INVALID_EVIDENCE_PATH:{index}")
        elif not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append(f"INVALID_SHA256:evidence[{index}].sha256")
        elif registry.get(normalized) != digest:
            errors.append(f"EVIDENCE_PATH_HASH_MISMATCH:{index}")
        else:
            links.add((normalized, digest))
    return links


def _required_mapping(proof: Mapping[str, object], key: str, errors: list[str]) -> Mapping[str, object] | None:
    value = proof.get(key)
    if not isinstance(value, Mapping):
        errors.append(f"MISSING_REASON_PROOF:{key}")
        return None
    return value


def _nonblank_fields(value: Mapping[str, object], fields: tuple[str, ...], errors: list[str]) -> bool:
    valid = True
    for field in fields:
        member = value.get(field)
        if not isinstance(member, str) or not member:
            errors.append(f"MISSING_REASON_PROOF:{field}")
            valid = False
    return valid


def _validate_exact_profile(proof: Mapping[str, object], record: Mapping[str, object], errors: list[str]) -> None:
    profile = _required_mapping(proof, "exact_profile", errors)
    if profile is None:
        return
    if not _nonblank_fields(profile, ("id", "version", "sha256"), errors):
        return
    module = record.get("source_module")
    if not isinstance(module, Mapping) or (
        profile.get("id") != _profile_id(record) or profile.get("version") != module.get("version64")
        or profile.get("sha256") != module.get("profile_digest") or SHA256_RE.fullmatch(profile["sha256"]) is None
    ):
        errors.append("EXACT_PROFILE_MISMATCH")


def _validate_linked_result(
    proof: Mapping[str, object], key: str, expected: str, registry: Mapping[str, str], links: set[tuple[str, str]], errors: list[str]
) -> None:
    result = _required_mapping(proof, key, errors)
    if result is None:
        return
    if result.get("result") != expected or not _validate_link(result, registry, links):
        errors.append(f"INVALID_REASON_PROOF:{key}")


def _validate_reason_proof(
    event: Mapping[str, object], record: Mapping[str, object], registry: Mapping[str, str], links: set[tuple[str, str]], errors: list[str]
) -> None:
    reason = event.get("reason")
    proof = event.get("reason_proof")
    if not isinstance(reason, str) or reason not in EXCLUSION_REASONS:
        return
    if not isinstance(proof, Mapping):
        errors.append("INVALID:reason_proof")
        return
    if reason == "SOURCE_ABSENT_EXACT_PROFILE":
        _validate_exact_profile(proof, record, errors)
        _validate_linked_result(proof, "complete_source_inventory", "COMPLETE", registry, links, errors)
        _validate_linked_result(proof, "zero_route_result", "ZERO_ROUTE", registry, links, errors)
        _validate_linked_result(proof, "anti_omission", "PASS", registry, links, errors)
    elif reason == "NO_RELEASE_PERMISSION":
        permission = _required_mapping(proof, "permission_text", errors)
        if permission is not None and not _validate_link(permission, registry, links):
            errors.append("INVALID_REASON_PROOF:permission_text")
        _nonblank_fields(proof, ("date", "credit", "derivative_scope", "redistribution_scope", "exact_source_version"), errors)
        module = record.get("source_module")
        if isinstance(module, Mapping) and proof.get("exact_source_version") != module.get("version64"):
            errors.append("EXACT_SOURCE_VERSION_MISMATCH")
    elif reason == "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE":
        _nonblank_fields(proof, ("exact_slot", "source_contract", "release_scope_mismatch"), errors)
        body_tuple = proof.get("exact_body_tuple")
        if not isinstance(body_tuple, (list, tuple)) or not body_tuple or not all(isinstance(item, str) and item for item in body_tuple):
            errors.append("MISSING_REASON_PROOF:exact_body_tuple")
        classification = record.get("classification")
        if isinstance(classification, Mapping) and proof.get("exact_slot") != classification.get("effective_slot"):
            errors.append("EXACT_SLOT_MISMATCH")
        record_tuple = record.get("body_tuple")
        if isinstance(record_tuple, Mapping):
            expected_tuple = [record_tuple.get(key) for key in ("race", "sex", "body_type")]
            if body_tuple != expected_tuple:
                errors.append("EXACT_BODY_TUPLE_MISMATCH")
    elif reason == "PROTECTED_NATIVE_ONLY":
        _nonblank_fields(proof, ("protected_registry_id", "protected_consumer", "protected_route", "protected_path", "protected_sha256"), errors)
        digest = proof.get("protected_sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None or digest not in registry.values():
            errors.append("INVALID_REASON_PROOF:protected_sha256")
    elif reason == "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT":
        _validate_exact_profile(proof, record, errors)
        searches = _required_mapping(proof, "searches", errors)
        if searches is not None:
            for key in ("root_templates", "stats", "inheritance", "visual_banks", "provider_maps"):
                if searches.get(key) != "COMPLETE":
                    errors.append(f"MISSING_REASON_PROOF:searches.{key}")
        if proof.get("result") not in {"ZERO_RESULT", "CONTRADICTORY_RESULT"}:
            errors.append("INVALID_REASON_PROOF:result")
        _validate_linked_result(proof, "anti_omission", "PASS", registry, links, errors)
    elif reason == "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE":
        _nonblank_fields(proof, ("selected_profile_id", "alternate_profile_id", "forbidden_module_relationship"), errors)
        if proof.get("selected_profile_id") != _profile_id(record):
            errors.append("SELECTED_PROFILE_MISMATCH")
        if proof.get("forbidden_module_relationship") != "MUTUALLY_EXCLUSIVE":
            errors.append("INVALID_REASON_PROOF:forbidden_module_relationship")
        alternate = _required_mapping(proof, "alternate_artifact", errors)
        if alternate is not None and not _validate_link(alternate, registry, links):
            errors.append("INVALID_REASON_PROOF:alternate_artifact")
    elif reason == "NO_SAFE_GEOMETRY_AVAILABLE":
        _validate_geometry_proof(proof, registry, links, errors)


def _validate_geometry_proof(proof: Mapping[str, object], registry: Mapping[str, str], links: set[tuple[str, str]], errors: list[str]) -> None:
    hard_contract = proof.get("hard_contract_impossibility")
    if isinstance(hard_contract, Mapping):
        if not _nonblank_fields(hard_contract, ("protected_object_id", "protected_object_path", "protected_object_sha256", "forbidden_boundary"), errors):
            return
        digest = hard_contract.get("protected_object_sha256")
        if hard_contract.get("result") != "HARD_CONTRACT_IMPOSSIBILITY" or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None or not _validate_link(hard_contract, registry, links):
            errors.append("INVALID_HARD_CONTRACT_IMPOSSIBILITY")
        return
    results = proof.get("architecture_results")
    if not isinstance(results, (list, tuple)) or len(results) < 3:
        errors.append("INSUFFICIENT_ARCHITECTURE_RESULTS")
    else:
        families: list[object] = []
        for result in results:
            if not isinstance(result, Mapping) or not _nonblank_fields(result, ("family_name", "material_distinction"), errors):
                errors.append("INVALID_ARCHITECTURE_RESULT")
                continue
            families.append(result.get("family_name"))
            components = result.get("components")
            if not isinstance(components, (list, tuple)) or not components:
                errors.append("INVALID_ARCHITECTURE_COMPONENT_EVIDENCE")
                continue
            for component in components:
                if not isinstance(component, Mapping) or not _nonblank_fields(component, ("component_id", "status"), errors) or component.get("status") not in {"FAIL", "BLOCKED"} or not _validate_link(component, registry, links):
                    errors.append("INVALID_ARCHITECTURE_COMPONENT_EVIDENCE")
        if len(set(families)) != len(families):
            errors.append("NON_DISTINCT_ARCHITECTURE_FAMILIES")
    gates = proof.get("fixed_gates")
    if not isinstance(gates, Mapping):
        errors.append("INVALID_FIXED_GATES")
    else:
        for gate in GEOMETRY_GATES:
            value = gates.get(gate)
            if not isinstance(value, Mapping):
                errors.append(f"MISSING_FIXED_GATE:{gate}")
            elif value.get("result") != "FAIL" or not _validate_link(value, registry, links):
                errors.append(f"INVALID_FIXED_GATE:{gate}")
    final = proof.get("final_available_safe_tooling_failure")
    if not isinstance(final, Mapping) or final.get("result") != "UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING" or not _validate_link(final, registry, links):
        errors.append("MISSING_FINAL_SAFE_TOOLING_FAILURE")


def _protected_or_accepted(record: Mapping[str, object]) -> bool:
    if record.get("disposition") in PROTECTED_DISPOSITIONS:
        return True
    acceptance = record.get("acceptance_event_id")
    if isinstance(acceptance, str) and acceptance not in {"", "UNKNOWN_ACCEPTANCE_EVENT"}:
        return True
    relations = record.get("protected_relations")
    return isinstance(relations, Mapping) and any(bool(value) for value in relations.values())


def _is_accepted_tiefling(record: Mapping[str, object]) -> bool:
    module = record.get("source_module")
    if not isinstance(module, Mapping):
        return False
    return any((module.get("pak") == TIEFLING_PAK, module.get("uuid") == TIEFLING_UUID, module.get("pak_sha256") == TIEFLING_SHA256))


def validate_exclusion_event(event: Mapping[str, object], *, ledger_record: object, evidence_hashes: object) -> list[str]:
    """Return stable errors for one event against one record and verified evidence map."""
    if not isinstance(event, Mapping):
        return ["INVALID:event"]
    record = _record_mapping(ledger_record)
    if record is None:
        return ["INVALID:ledger_record"]
    errors: list[str] = []
    registry = _verified_registry(evidence_hashes, errors)
    if event.get("schema") != EXCLUSION_SCHEMA:
        errors.append("INVALID:schema")
    if event.get("schema_version") != EXCLUSION_SCHEMA_VERSION or isinstance(event.get("schema_version"), bool):
        errors.append("INVALID:schema_version")
    for field in ("event_id", "record_id", "identity_sha256", "source_profile_id", "mode", "reason", "scope_statement", "next_project_if_reopened", "approved_by", "approved_reason", "created_utc"):
        _validate_text(event, field, errors)
    if isinstance(event.get("event_id"), str) and event.get("event_id") != exclusion_event_id(event):
        errors.append("EVENT_ID_MISMATCH")
    if isinstance(event.get("record_id"), str) and RECORD_ID_RE.fullmatch(event["record_id"]) is None:
        errors.append("INVALID_RECORD_ID")
    if isinstance(event.get("identity_sha256"), str) and SHA256_RE.fullmatch(event["identity_sha256"]) is None:
        errors.append("INVALID_SHA256:identity_sha256")
    if _timestamp(event.get("created_utc")) is None:
        errors.append("INVALID_CREATED_UTC")
    if isinstance(event.get("mode"), str) and event.get("mode") and event.get("mode") not in EXCLUSION_MODES:
        errors.append(f"INVALID_MODE:{event['mode']}")
    if isinstance(event.get("reason"), str) and event.get("reason") and event.get("reason") not in EXCLUSION_REASONS:
        errors.append(f"INVALID_EXCLUSION_REASON:{event['reason']}")
    if not isinstance(event.get("attempted_architectures"), (list, tuple)):
        errors.append("INVALID:attempted_architectures")
    if not isinstance(event.get("fixed_acceptance_gates"), Mapping):
        errors.append("INVALID:fixed_acceptance_gates")
    links = _validate_event_evidence(event, registry, errors)
    impact = event.get("protected_impact")
    if not isinstance(impact, Mapping):
        errors.append("INVALID:protected_impact")
    else:
        for field in ("registry_ids", "shared_consumers", "forbidden_targets"):
            if not isinstance(impact.get(field), (list, tuple)):
                errors.append(f"INVALID_TYPE:protected_impact.{field}")
            elif impact[field]:
                errors.append(f"PROTECTED_IMPACT_DECLARED:{field}")
        if impact.get("result") != "NO_PROTECTED_MUTATION":
            errors.append("PROTECTED_MUTATION_RESULT")
    _validate_reason_proof(event, record, registry, links, errors)
    if event.get("record_id") != record.get("record_id"):
        errors.append("RECORD_ID_MISMATCH")
    if event.get("identity_sha256") != record.get("identity_sha256"):
        errors.append("IDENTITY_SHA256_MISMATCH")
    if event.get("source_profile_id") != _profile_id(record):
        errors.append("SOURCE_PROFILE_ID_MISMATCH")
    if _protected_or_accepted(record):
        errors.append("EXCLUSION_FORBIDDEN_PROTECTED_OR_ACCEPTED_RECORD")
    if _is_accepted_tiefling(record):
        errors.append("EXCLUSION_FORBIDDEN_ACCEPTED_TIEFLING")
    return errors


def select_current_exclusion(
    events: Iterable[Mapping[str, object]], record_id: str, mode: str, *, ledger_record: object, evidence_hashes: object
) -> ExclusionSelection:
    """Choose only a valid newest unrevoked event from an unambiguous full history."""
    relevant = [event for event in events if isinstance(event, Mapping) and event.get("record_id") == record_id and event.get("mode") == mode]
    dated: list[tuple[int, datetime, Mapping[str, object]]] = []
    for index, event in enumerate(relevant):
        stamp = _timestamp(event.get("created_utc"))
        if stamp is None:
            return ExclusionSelection(None, (f"INVALID_EVENT:{index}:INVALID_EVENT_CREATED_UTC",))
        dated.append((index, stamp, event))
    normal = [(index, stamp, event) for index, stamp, event in dated if event.get("event_type", "EXCLUSION") == "EXCLUSION"]
    validation_errors = [f"INVALID_EVENT:{index}:{error}" for index, _, event in normal for error in validate_exclusion_event(event, ledger_record=ledger_record, evidence_hashes=evidence_hashes)]
    if validation_errors:
        return ExclusionSelection(None, tuple(validation_errors))
    ids = [event.get("event_id") for _, _, event in normal]
    if len(ids) != len(set(ids)):
        return ExclusionSelection(None, ("DUPLICATE_EXCLUSION_EVENT_ID",))
    for stamp in {stamp for _, stamp, _ in normal}:
        if sum(1 for _, candidate, _ in normal if candidate == stamp) > 1:
            return ExclusionSelection(None, ("CONFLICTING_EXCLUSION_EVENTS",))
    for stamp in {stamp for _, stamp, _ in dated}:
        simultaneous = [event for _, candidate, event in dated if candidate == stamp]
        if len(simultaneous) > 1 and any(event.get("event_type") == "REVOCATION" for event in simultaneous):
            return ExclusionSelection(None, ("CONFLICTING_EXCLUSION_EVENTS",))
    dated.sort(key=lambda item: item[1])
    prior_ids: set[object] = set()
    revoked: set[object] = set()
    for _, _, event in dated:
        if event.get("event_type", "EXCLUSION") == "EXCLUSION":
            prior_ids.add(event.get("event_id"))
        elif event.get("event_type") == "REVOCATION":
            target = event.get("revokes_event_id")
            if target not in prior_ids:
                return ExclusionSelection(None, ("REVOCATION_WITHOUT_PRIOR_EVENT",))
            revoked.add(target)
        else:
            return ExclusionSelection(None, ("INVALID_EVENT_TYPE",))
    active = [(stamp, event) for _, stamp, event in normal if event.get("event_id") not in revoked]
    return ExclusionSelection(active[-1][1]) if active else ExclusionSelection(None)
