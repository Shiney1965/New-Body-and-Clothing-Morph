"""Independent raw-byte inventories for the release master ledger audit."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import posixpath
import re
from typing import Mapping

from .audit import InventorySets
from .configuration import VerifiedInput


BASE_GAME_SOURCE_PROFILE_UNRESOLVED = "BASE_GAME_SOURCE_PROFILE_UNRESOLVED"
RELEASE_MODES = ("vanilla", "sbbf", "bcb", "external")
RECORD_ID_RE = re.compile(r"^LEDGER_[0-9A-F]{64}$")


class InventoryIntegrityError(ValueError):
    """Raised when independently inventoried evidence is internally inconsistent."""


@dataclass(frozen=True)
class ProtectedManifestRelation:
    registry_id: str
    protected_path: str
    bytes: int
    sha256: str
    manifest_evidence_path: str
    manifest_input_id: str
    manifest_input_sha256: str


@dataclass(frozen=True)
class IndependentInventories:
    source_observations: frozenset[str] = frozenset()
    prior_evidence: frozenset[str] = frozenset()
    packaged_records: frozenset[str] = frozenset()
    required_source_profiles: frozenset[str] = frozenset()
    complete_source_profiles: frozenset[str] = frozenset()
    protected_manifest_relations: Mapping[str, ProtectedManifestRelation] = field(default_factory=dict)
    provider_claims: Mapping[object, object] = field(default_factory=dict)
    package_claims: Mapping[object, object] = field(default_factory=dict)
    provider_authority_present: bool = False
    provider_authority_complete: bool = False
    package_authority_present: bool = False
    package_authority_complete: bool = False
    freeze_bound_source_profiles: frozenset[str] = frozenset()
    freeze_missing_source_profiles: frozenset[str] = frozenset()
    census_incomplete_source_profiles: frozenset[str] = frozenset()

    @property
    def missing_source_profiles(self) -> tuple[str, ...]:
        return tuple(sorted(self.required_source_profiles - self.complete_source_profiles))

    def to_audit_sets(self) -> InventorySets:
        return InventorySets(
            source_observations=self.source_observations,
            prior_evidence=self.prior_evidence,
            packaged_records=self.packaged_records,
            required_source_profiles=self.required_source_profiles,
            complete_source_profiles=self.complete_source_profiles,
            freeze_bound_source_profiles=self.freeze_bound_source_profiles,
            freeze_missing_source_profiles=self.freeze_missing_source_profiles,
            census_incomplete_source_profiles=self.census_incomplete_source_profiles,
        )


def extract_independent_inventories(
    verified_inputs: list[VerifiedInput],
) -> IndependentInventories:
    payloads = {input_.input_id: _read_verified_json(input_) for input_ in verified_inputs}
    relations = _protected_manifest_relations(verified_inputs, payloads)
    (
        provider_claims,
        provider_authority_present,
        provider_authority_complete,
    ) = _provider_claim_inventory(verified_inputs, payloads)
    (
        package_claims,
        package_authority_present,
        package_authority_complete,
    ) = _package_claim_inventory(verified_inputs, payloads)
    source_observations: set[str] = set()
    prior_evidence = {
        str(input_.path)
        for input_ in verified_inputs
        if input_.kind.upper() == "SUPPORTING_EVIDENCE"
        or is_claim_authority(input_, payloads[input_.input_id])
    }
    packaged_records: set[str] = set()
    required_profiles: set[str] = {BASE_GAME_SOURCE_PROFILE_UNRESOLVED}
    complete_profiles: set[str] = set()
    freeze_keys: set[tuple[str, str]] = set()
    freeze_bound: set[str] = set()
    census_incomplete: set[str] = set()

    for payload in payloads.values():
        census_required, census_complete, keys, bound, incomplete = _census_profiles(payload)
        required_profiles.update(census_required)
        complete_profiles.update(census_complete)
        freeze_keys.update(keys)
        freeze_bound.update(bound)
        census_incomplete.update(incomplete)

    for input_ in verified_inputs:
        payload = payloads[input_.input_id]
        if is_claim_authority(input_, payload):
            continue
        if input_.kind.upper() in {
            "PROTECTED_REGISTRY", "COVERAGE", "TRUE_UNDERWEAR", "VANITYBODY", "BCBSCANTILY",
            "PACKAGE", "NAMED_TARGET",
        }:
            source_observations.update(_source_observation_ids(input_, payload))
        if input_.kind.upper() == "PERMISSION":
            source_observations.update(
                _permission_source_observation_ids(input_, payload, freeze_keys)
            )
        if input_.kind.upper() == "PACKAGE":
            packaged_records.update(_package_ids(payload))
        if input_.input_id == "source_profile_inventory":
            required, complete = _source_profiles(payload)
            required_profiles.update(required)
            complete_profiles.update(complete)

    permission_by_key = _permission_binding_index(verified_inputs, payloads)
    for payload in payloads.values():
        for candidate in _census_candidate_rows(payload):
            contract = candidate["contract"]
            assert isinstance(contract, Mapping)
            module = contract.get("module")
            if not isinstance(module, Mapping):
                continue
            try:
                assert isinstance(contract, Mapping)
                profile_id = _census_bound_profile_id(contract, module)
            except InventoryIntegrityError:
                continue
            if profile_id in complete_profiles:
                continue
            built = _admissible_contract_from_freeze_permission_join(
                candidate, permission_by_key,
            )
            completed_id = (
                _complete_source_profile(built, required_profiles) if built is not None else None
            )
            if completed_id is not None:
                complete_profiles.add(completed_id)

    freeze_missing = set(required_profiles) - freeze_bound
    census_incomplete = (census_incomplete | freeze_bound) - complete_profiles

    return IndependentInventories(
        source_observations=frozenset(source_observations),
        prior_evidence=frozenset(prior_evidence),
        packaged_records=frozenset(packaged_records),
        required_source_profiles=frozenset(required_profiles),
        complete_source_profiles=frozenset(complete_profiles),
        freeze_bound_source_profiles=frozenset(freeze_bound),
        freeze_missing_source_profiles=frozenset(freeze_missing),
        census_incomplete_source_profiles=frozenset(census_incomplete),
        protected_manifest_relations=relations,
        provider_claims=provider_claims,
        package_claims=package_claims,
        provider_authority_present=provider_authority_present,
        provider_authority_complete=provider_authority_complete,
        package_authority_present=package_authority_present,
        package_authority_complete=package_authority_complete,
    )


def is_claim_authority(
    input_: VerifiedInput, payload: object, role: str | None = None,
) -> bool:
    """Recognize authority evidence using the same ID, kind, and schema contract."""
    return any(
        input_.input_id == f"{candidate}_claim_inventory"
        or input_.kind.upper() == f"{candidate.upper()}_CLAIM_INVENTORY"
        or (
            isinstance(payload, Mapping)
            and payload.get("schema") == f"clothmorph.{candidate}-claim-inventory"
        )
        for candidate in ((role,) if role is not None else ("provider", "package"))
    )


def _claim_authority_inputs(
    verified_inputs: list[VerifiedInput], payloads: Mapping[str, object], role: str,
) -> list[VerifiedInput]:
    return [
        input_
        for input_ in verified_inputs
        if is_claim_authority(input_, payloads[input_.input_id], role)
    ]


def _claim_key(route: Mapping[str, object]) -> tuple[str, str]:
    record_id_present = "record_id" in route
    canonical_source_key_present = "canonical_source_key" in route
    if record_id_present == canonical_source_key_present:
        raise InventoryIntegrityError("CLAIM_INVENTORY_IDENTITY_INVALID")
    record_id = route["record_id"] if record_id_present else None
    canonical_source_key = (
        route["canonical_source_key"] if canonical_source_key_present else None
    )
    mode = route.get("mode")
    if (record_id is None) == (canonical_source_key is None):
        raise InventoryIntegrityError("CLAIM_INVENTORY_IDENTITY_INVALID")
    if record_id is not None and (
        not isinstance(record_id, str) or RECORD_ID_RE.fullmatch(record_id) is None
    ):
        raise InventoryIntegrityError("CLAIM_INVENTORY_RECORD_ID_INVALID")
    if canonical_source_key is not None and (
        not isinstance(canonical_source_key, str)
        or not canonical_source_key.startswith("OBSERVATION:")
        or not canonical_source_key.removeprefix("OBSERVATION:")
    ):
        raise InventoryIntegrityError("CLAIM_INVENTORY_CANONICAL_SOURCE_KEY_INVALID")
    if not isinstance(mode, str) or mode not in RELEASE_MODES:
        raise InventoryIntegrityError("CLAIM_INVENTORY_MODE_INVALID")
    return str(record_id if record_id is not None else canonical_source_key), mode


def _reject_unexpected_keys(
    value: Mapping[str, object], allowed: frozenset[str], error_prefix: str,
) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise InventoryIntegrityError(f"{error_prefix}:{unexpected[0]}")


def _claim_text(route: Mapping[str, object], field: str, label: str) -> list[str]:
    if field not in route:
        return []
    value = route[field]
    if not isinstance(value, str) or not value:
        raise InventoryIntegrityError(f"CLAIM_INVENTORY_{field.upper()}_INVALID")
    return [f"{label}:{value}"]


def _claim_sequence(
    route: Mapping[str, object], field: str, label: str, *, hashes: bool = False,
    paths: bool = False,
) -> list[str]:
    if field not in route:
        return []
    value = route[field]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise InventoryIntegrityError(f"CLAIM_INVENTORY_{field.upper()}_INVALID")
    normalized: list[str] = []
    for item in value:
        if hashes:
            if not _valid_sha256(item):
                raise InventoryIntegrityError(f"CLAIM_INVENTORY_{field.upper()}_INVALID")
            item = item.upper()
        elif paths:
            item = posixpath.normpath(item.replace("\\", "/"))
        normalized.append(f"{label}:{item}")
    return normalized


def _provider_claim_inventory(
    verified_inputs: list[VerifiedInput], payloads: Mapping[str, object],
) -> tuple[dict[object, tuple[str, ...]], bool, bool]:
    collected: dict[object, set[str]] = {}
    authorities = _claim_authority_inputs(verified_inputs, payloads, "provider")
    if len(authorities) > 1:
        raise InventoryIntegrityError("PROVIDER_CLAIM_AUTHORITY_DUPLICATE")
    for authority in authorities:
        payload = payloads[authority.input_id]
        if not isinstance(payload, Mapping) or payload.get("schema") != "clothmorph.provider-claim-inventory":
            raise InventoryIntegrityError("PROVIDER_CLAIM_INVENTORY_SCHEMA_INVALID")
        if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
            raise InventoryIntegrityError("PROVIDER_CLAIM_INVENTORY_SCHEMA_INVALID")
        _reject_unexpected_keys(
            payload,
            frozenset({"schema", "schema_version", "routes"}),
            "PROVIDER_CLAIM_INVENTORY_UNEXPECTED_KEY",
        )
        routes = payload.get("routes")
        if not isinstance(routes, list):
            raise InventoryIntegrityError("PROVIDER_CLAIM_INVENTORY_ROUTES_INVALID")
        for route in routes:
            if not isinstance(route, Mapping):
                raise InventoryIntegrityError("PROVIDER_CLAIM_INVENTORY_ROUTE_INVALID")
            _reject_unexpected_keys(
                route,
                frozenset({
                    "record_id", "canonical_source_key", "mode", "provider_id",
                    "target_vrs", "target_paths", "payload_hashes", "provenance",
                }),
                "PROVIDER_CLAIM_INVENTORY_ROUTE_UNEXPECTED_KEY",
            )
            key = _claim_key(route)
            claims = [
                *_claim_text(route, "provider_id", "provider_id"),
                *_claim_sequence(route, "target_vrs", "target_vr"),
                *_claim_sequence(route, "target_paths", "target_path", paths=True),
                *_claim_sequence(route, "payload_hashes", "payload_hash", hashes=True),
                *_claim_text(route, "provenance", "provenance"),
            ]
            if claims:
                collected.setdefault(key, set()).update(claims)
    for input_ in verified_inputs:
        if input_.kind.upper() not in {"PACKAGE", "PROVIDER"}:
            continue
        payload = payloads[input_.input_id]
        for record in _records(payload, ("records",)):
            route_count = record.get("route_count", 0)
            if isinstance(route_count, bool) or not isinstance(route_count, int) or route_count < 0:
                raise InventoryIntegrityError("PROVIDER_ROUTE_COUNT_INVALID")
            routes = record.get("routes")
            if route_count > 0 and (
                not isinstance(routes, list) or len(routes) != route_count
            ):
                for mode in RELEASE_MODES:
                    collected.setdefault(mode, set()).add(
                        f"missing_provider_route_inventory:{input_.input_id}"
                    )
    claims = {
        key: tuple(sorted(values))
        for key, values in sorted(collected.items(), key=lambda item: str(item[0]))
    }
    present = bool(authorities)
    return claims, present, present


def _normalize_package_id(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("PACKAGE_SHA256:"):
        raise InventoryIntegrityError("CLAIM_INVENTORY_PACKAGE_ID_INVALID")
    digest = value.removeprefix("PACKAGE_SHA256:")
    if not _valid_sha256(digest):
        raise InventoryIntegrityError("CLAIM_INVENTORY_PACKAGE_ID_INVALID")
    return f"PACKAGE_SHA256:{digest.upper()}"


def _package_claim_inventory(
    verified_inputs: list[VerifiedInput], payloads: Mapping[str, object],
) -> tuple[dict[tuple[str, str], tuple[str, ...]], bool, bool]:
    collected: dict[tuple[str, str], set[str]] = {}
    authorities = _claim_authority_inputs(verified_inputs, payloads, "package")
    if len(authorities) > 1:
        raise InventoryIntegrityError("PACKAGE_CLAIM_AUTHORITY_DUPLICATE")
    for authority in authorities:
        payload = payloads[authority.input_id]
        if not isinstance(payload, Mapping) or payload.get("schema") != "clothmorph.package-claim-inventory":
            raise InventoryIntegrityError("PACKAGE_CLAIM_INVENTORY_SCHEMA_INVALID")
        if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
            raise InventoryIntegrityError("PACKAGE_CLAIM_INVENTORY_SCHEMA_INVALID")
        _reject_unexpected_keys(
            payload,
            frozenset({"schema", "schema_version", "routes"}),
            "PACKAGE_CLAIM_INVENTORY_UNEXPECTED_KEY",
        )
        routes = payload.get("routes")
        if not isinstance(routes, list):
            raise InventoryIntegrityError("PACKAGE_CLAIM_INVENTORY_ROUTES_INVALID")
        for route in routes:
            if not isinstance(route, Mapping):
                raise InventoryIntegrityError("PACKAGE_CLAIM_INVENTORY_ROUTE_INVALID")
            _reject_unexpected_keys(
                route,
                frozenset({
                    "record_id", "canonical_source_key", "mode", "package_ids",
                    "shipped_package_id",
                }),
                "PACKAGE_CLAIM_INVENTORY_ROUTE_UNEXPECTED_KEY",
            )
            key = _claim_key(route)
            claims: list[str] = []
            if "package_ids" in route:
                raw_package_ids = route["package_ids"]
                if not isinstance(raw_package_ids, list):
                    raise InventoryIntegrityError("CLAIM_INVENTORY_PACKAGE_IDS_INVALID")
                claims.extend(
                    f"package_id:{_normalize_package_id(package_id)}"
                    for package_id in raw_package_ids
                )
            if "shipped_package_id" in route:
                claims.append(
                    "shipped_package_id:"
                    + _normalize_package_id(route["shipped_package_id"])
                )
            if claims:
                collected.setdefault(key, set()).update(claims)
    for input_ in verified_inputs:
        if input_.kind.upper() != "PACKAGE":
            continue
        for index, record in enumerate(_records(payloads[input_.input_id], ("records",))):
            candidate = record.get("candidate_pak_sha256")
            if not _valid_sha256(candidate):
                continue
            local_id = (
                record.get("observation_id")
                or record.get("identity")
                or record.get("id")
                or record.get("item_uuid")
                or f"{input_.input_id}:{index}"
            )
            if not isinstance(local_id, str) or not local_id:
                raise InventoryIntegrityError("PACKAGE_CLAIM_OBSERVATION_ID_INVALID")
            source_key = f"OBSERVATION:{input_.input_id}:{local_id}"
            package_id = f"PACKAGE_SHA256:{str(candidate).upper()}"
            for mode in RELEASE_MODES:
                collected.setdefault((source_key, mode), set()).add(
                    f"package_id:{package_id}"
                )
    claims = {
        key: tuple(sorted(values))
        for key, values in sorted(collected.items())
    }
    present = bool(authorities)
    return claims, present, present


def _read_verified_json(input_: VerifiedInput) -> object:
    try:
        content = input_.path.read_bytes()
    except OSError as error:
        raise InventoryIntegrityError(f"INVENTORY_INPUT_UNREADABLE:{input_.input_id}") from error
    actual = hashlib.sha256(content).hexdigest().upper()
    if (
        len(content) != input_.bytes
        or actual != input_.expected_sha256
        or actual != input_.actual_sha256
    ):
        raise InventoryIntegrityError(f"INVENTORY_INPUT_HASH_MISMATCH:{input_.input_id}")
    if input_.path.suffix.lower() == ".md":
        return {"document_sha256": actual}
    try:
        return json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryIntegrityError(f"INVENTORY_JSON_INVALID:{input_.input_id}") from error


def _records(payload: object, keys: tuple[str, ...]) -> list[Mapping[str, object]]:
    value = payload
    if isinstance(payload, Mapping):
        for key in keys:
            if key in payload:
                value = payload[key]
                break
        else:
            value = [payload]
    if not isinstance(value, list):
        raise InventoryIntegrityError("INVENTORY_RECORDS_NOT_LIST")
    records: list[Mapping[str, object]] = []
    for index, record in enumerate(value):
        if not isinstance(record, Mapping):
            raise InventoryIntegrityError(f"INVENTORY_RECORD_INVALID:{index}")
        records.append(record)
    return records


def _source_observation_ids(input_: VerifiedInput, payload: object) -> set[str]:
    kind = input_.kind.upper()
    if kind == "NAMED_TARGET" and input_.path.suffix.lower() == ".md":
        # Markdown named targets emit exactly one adapter observation keyed by input_id.
        return {f"{input_.input_id}:{input_.input_id}"}
    keys_by_kind = {
        "PROTECTED_REGISTRY": ("entries", "records"),
        "COVERAGE": ("records",),
        "TRUE_UNDERWEAR": ("records",),
        "VANITYBODY": ("records",),
        "BCBSCANTILY": ("items", "records"),
        "PACKAGE": ("records",),
        "NAMED_TARGET": ("records",),
    }
    records = _records(payload, keys_by_kind[kind])
    identities: set[str] = set()
    for index, record in enumerate(records):
        candidate = (
            record.get("observation_id")
            or record.get("identity")
            or record.get("id")
            or record.get("item_uuid")
        )
        local_id = candidate if isinstance(candidate, str) and candidate else f"{input_.input_id}:{index}"
        observation_id = f"{input_.input_id}:{local_id}"
        if observation_id in identities:
            raise InventoryIntegrityError(f"SOURCE_INVENTORY_DUPLICATE_ID:{observation_id}")
        identities.add(observation_id)
    return identities


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _package_ids(payload: object) -> set[str]:
    ids: set[str] = set()
    for record in _records(payload, ("records",)):
        candidate = record.get("candidate_pak_sha256")
        if _valid_sha256(candidate):
            ids.add(f"PACKAGE_SHA256:{str(candidate).upper()}")
    return ids



def _census_candidate_rows(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping) and isinstance(payload.get("candidates"), list):
        rows = payload["candidates"]
    else:
        return []
    if not rows:
        return []
    first = rows[0]
    if not isinstance(first, Mapping):
        return []
    if not isinstance(first.get("discovery_profile_id"), str):
        return []
    if not isinstance(first.get("contract"), Mapping):
        return []
    normalized: list[Mapping[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise InventoryIntegrityError(f"CENSUS_CANDIDATE_INVALID:{index}")
        if not isinstance(row.get("discovery_profile_id"), str) or not row.get("discovery_profile_id"):
            raise InventoryIntegrityError(f"CENSUS_CANDIDATE_ID_INVALID:{index}")
        if not isinstance(row.get("contract"), Mapping):
            raise InventoryIntegrityError(f"CENSUS_CANDIDATE_CONTRACT_INVALID:{index}")
        normalized.append(row)
    return normalized


def _census_profiles(
    payload: object,
) -> tuple[set[str], set[str], set[tuple[str, str]], set[str], set[str]]:
    """Collect required/complete/freeze-bound identities from census candidates.

    BCBPak (1d24059d-...) and BCBUniqueTav (28c82588-...) may both freeze-bind as
    alternate body-path source profiles. They are mutually exclusive installs (XOR),
    not additive dual-body; ledger completeness does not authorize co-loading.
    All garments present in each pak are in-scope (no forced 200-item cap).
    """
    required: set[str] = set()
    complete: set[str] = set()
    freeze_keys: set[tuple[str, str]] = set()
    freeze_bound: set[str] = set()
    incomplete: set[str] = set()
    for candidate in _census_candidate_rows(payload):
        contract = candidate["contract"]
        assert isinstance(contract, Mapping)
        module = contract.get("module")
        if not isinstance(module, Mapping):
            raise InventoryIntegrityError("CENSUS_CANDIDATE_MODULE_INVALID")
        profile_id = _census_bound_profile_id(contract, module)
        required.add(profile_id)
        freeze_bound.add(profile_id)
        sha = module.get("pak_sha256")
        uuid = module.get("uuid")
        if isinstance(uuid, str) and uuid and _valid_sha256(sha):
            freeze_keys.add((uuid.lower(), str(sha).upper()))
        admissible = candidate.get("admissible_contract")
        release_complete = candidate.get("release_profile_complete") is True
        completed_id = None
        if release_complete and admissible is not None:
            completed_id = _complete_source_profile(admissible, required)
        if completed_id is None and release_complete:
            completed_id = _complete_source_profile(contract, required)
        if completed_id is not None:
            complete.add(completed_id)
        else:
            incomplete.add(profile_id)
    return required, complete, freeze_keys, freeze_bound, incomplete


def _permission_source_observation_ids(
    input_: VerifiedInput, payload: object, freeze_keys: set[tuple[str, str]],
) -> set[str]:
    if not freeze_keys:
        return set()
    identities: set[str] = set()
    for index, record in enumerate(_records(payload, ("records",))):
        uuid = record.get("mod_uuid")
        sha = record.get("pak_sha256")
        if not isinstance(uuid, str) or not uuid or not _valid_sha256(sha):
            continue
        if (uuid.lower(), str(sha).upper()) not in freeze_keys:
            continue
        scopes = record.get("scope_resolved")
        if not isinstance(scopes, list):
            continue
        for scope_index, mesh in enumerate(scopes):
            if not isinstance(mesh, str) or not mesh:
                continue
            local_id = f"{input_.input_id}:{index}:{scope_index}"
            observation_id = f"{input_.input_id}:{local_id}"
            if observation_id in identities:
                raise InventoryIntegrityError(f"SOURCE_INVENTORY_DUPLICATE_ID:{observation_id}")
            identities.add(observation_id)
    return identities



def _permission_binding_index(
    verified_inputs: list[VerifiedInput], payloads: Mapping[str, object],
) -> dict[tuple[str, str], Mapping[str, object]]:
    """Index independently inventoried permission rows by freeze uuid+pak hash."""
    index: dict[tuple[str, str], Mapping[str, object]] = {}
    for input_ in verified_inputs:
        if input_.kind.upper() != "PERMISSION":
            continue
        payload = payloads[input_.input_id]
        for record in _records(payload, ("records",)):
            uuid = record.get("mod_uuid")
            sha = record.get("pak_sha256")
            if not isinstance(uuid, str) or not uuid or not _valid_sha256(sha):
                continue
            key = (uuid.lower(), str(sha).upper())
            # First exact binding wins; later duplicates are ignored for admission.
            index.setdefault(key, record)
    return index


def _permission_state(flag: Mapping[str, object]) -> str | None:
    token = flag.get("permission")
    if token == "granted":
        return "release_cleared"
    if token in {"denied", "blocked"}:
        return "blocked"
    if token == "private_test_only":
        return "private_test_only"
    return None


def _permission_evidence_sha256(record: Mapping[str, object], flag: Mapping[str, object]) -> str | None:
    evidence = record.get("evidence")
    if not isinstance(evidence, Mapping):
        evidence = flag.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    payload = json.dumps(evidence, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def _admissible_contract_from_freeze_permission_join(
    candidate: Mapping[str, object],
    permission_by_key: Mapping[tuple[str, str], Mapping[str, object]],
) -> dict[str, object] | None:
    """Build a section-7.1 contract from freeze census digests + permission evidence.

    Does not invent meshes or flatten routes. Census may remain
    release_profile_complete=false; this only fills fields supported by real
    freeze/permission evidence. Self-declared candidate.admissible_contract is
    ignored here (anti self-authorization).
    """
    contract = candidate.get("contract")
    if not isinstance(contract, Mapping):
        return None
    module = contract.get("module")
    if not isinstance(module, Mapping):
        return None
    uuid = module.get("uuid")
    sha = module.get("pak_sha256")
    version64 = module.get("version64")
    if not isinstance(uuid, str) or not uuid or not isinstance(version64, str) or not version64:
        return None
    if not _valid_sha256(sha):
        return None
    permission_record = permission_by_key.get((uuid.lower(), str(sha).upper()))
    if permission_record is None:
        return None
    flag = permission_record.get("flag")
    if not isinstance(flag, Mapping):
        return None
    state = _permission_state(flag)
    credit = flag.get("credit_line")
    if state is None or not isinstance(credit, str) or not credit:
        return None
    evidence_sha = _permission_evidence_sha256(permission_record, flag)
    if evidence_sha is None:
        return None
    if any(not _valid_sha256(contract.get(key)) for key in (
        "content_manifest_sha256", "root_stats_visualbank_digest",
    )):
        return None
    route = candidate.get("observed_creation_paths_digest")
    if not _valid_sha256(route):
        route = contract.get("route_partition_digest")
    if not _valid_sha256(route):
        return None
    deps = contract.get("required_dependencies")
    if not isinstance(deps, list):
        return None
    forbidden = contract.get("forbidden_modules")
    bodies = contract.get("supported_body_tuples")
    # Honest empty lists when census left authority fields unresolved/None.
    if forbidden is None:
        forbidden = []
    if bodies is None:
        bodies = []
    if not isinstance(forbidden, list) or not isinstance(bodies, list):
        return None
    exclude = flag.get("exclude")
    limits = (
        list(exclude)
        if isinstance(exclude, list) and all(isinstance(item, str) for item in exclude)
        else []
    )
    module_text = ("pak_filename", "folder", "name", "uuid", "version64")
    if any(not isinstance(module.get(key), str) or not module.get(key) for key in module_text):
        return None
    declared = contract.get("profile_id")
    profile_id = (
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED
        if declared == BASE_GAME_SOURCE_PROFILE_UNRESOLVED
        else f"SOURCE_PROFILE:{uuid}:{version64}"
    )
    return {
        "schema": "clothmorph.source-profile",
        "schema_version": 1,
        "profile_id": profile_id,
        "module": {
            "pak_filename": module["pak_filename"],
            "folder": module["folder"],
            "name": module["name"],
            "uuid": module["uuid"],
            "version64": module["version64"],
            "pak_sha256": str(sha).upper(),
        },
        "content_manifest_sha256": str(contract["content_manifest_sha256"]).upper(),
        "root_stats_visualbank_digest": str(contract["root_stats_visualbank_digest"]).upper(),
        "required_dependencies": list(deps),
        "forbidden_modules": list(forbidden),
        "supported_body_tuples": list(bodies),
        "permission": {
            "state": state,
            "evidence_sha256": evidence_sha,
            "credit_line": credit,
            "distribution_limits": limits,
        },
        "route_partition_digest": str(route).upper(),
    }


def _source_profile_id(module: Mapping[str, object]) -> str:
    uuid = module.get("uuid")
    version64 = module.get("version64")
    if not isinstance(uuid, str) or not uuid or not isinstance(version64, str) or not version64:
        raise InventoryIntegrityError("SOURCE_PROFILE_MODULE_IDENTITY_INVALID")
    return f"SOURCE_PROFILE:{uuid}:{version64}"


def _census_bound_profile_id(contract: Mapping[str, object], module: Mapping[str, object]) -> str:
    """Prefer explicit BASE_GAME aggregate profile_id over module uuid:version.

    Retained base-game capture evidence binds BASE_GAME_SOURCE_PROFILE_UNRESOLVED
    without inventing a new SOURCE_PROFILE:<Shared uuid> package-freeze identity.
    """
    profile_id = contract.get("profile_id")
    if profile_id == BASE_GAME_SOURCE_PROFILE_UNRESOLVED:
        return BASE_GAME_SOURCE_PROFILE_UNRESOLVED
    return _source_profile_id(module)


def _complete_source_profile(contract: object, required_profiles: set[str]) -> str | None:
    if not isinstance(contract, Mapping):
        return None
    module = contract.get("module")
    permission = contract.get("permission")
    if not isinstance(module, Mapping) or not isinstance(permission, Mapping):
        return None
    profile_id = contract.get("profile_id")
    if not isinstance(profile_id, str) or profile_id not in required_profiles:
        return None
    if contract.get("schema") != "clothmorph.source-profile" or contract.get("schema_version") != 1:
        return None
    module_text = ("pak_filename", "folder", "name", "uuid", "version64")
    if any(not isinstance(module.get(key), str) or not module.get(key) for key in module_text):
        return None
    expected_id = (
        BASE_GAME_SOURCE_PROFILE_UNRESOLVED
        if profile_id == BASE_GAME_SOURCE_PROFILE_UNRESOLVED
        else f"SOURCE_PROFILE:{module['uuid']}:{module['version64']}"
    )
    if profile_id != expected_id or not _valid_sha256(module.get("pak_sha256")):
        return None
    if any(not _valid_sha256(contract.get(key)) for key in (
        "content_manifest_sha256", "root_stats_visualbank_digest", "route_partition_digest",
    )):
        return None
    if any(not isinstance(contract.get(key), list) for key in (
        "required_dependencies", "forbidden_modules", "supported_body_tuples",
    )):
        return None
    if permission.get("state") not in {"private_test_only", "release_cleared", "blocked"}:
        return None
    if not _valid_sha256(permission.get("evidence_sha256")):
        return None
    if not isinstance(permission.get("credit_line"), str) or not permission.get("credit_line"):
        return None
    if not isinstance(permission.get("distribution_limits"), list):
        return None
    return profile_id


def _source_profiles(payload: object) -> tuple[set[str], set[str]]:
    if not isinstance(payload, Mapping):
        raise InventoryIntegrityError("SOURCE_PROFILE_INVENTORY_INVALID")
    modules = payload.get("modules")
    if not isinstance(modules, list):
        raise InventoryIntegrityError("SOURCE_PROFILE_MODULES_NOT_LIST")
    required = {BASE_GAME_SOURCE_PROFILE_UNRESOLVED}
    for module in modules:
        if not isinstance(module, Mapping):
            raise InventoryIntegrityError("SOURCE_PROFILE_MODULE_INVALID")
        required.add(_source_profile_id(module))
    contracts = payload.get("source_profiles", [])
    if not isinstance(contracts, list):
        raise InventoryIntegrityError("SOURCE_PROFILE_CONTRACTS_NOT_LIST")
    complete = {
        profile_id
        for contract in contracts
        for profile_id in (_complete_source_profile(contract, required),)
        if profile_id is not None
    }
    return required, complete


def _protected_manifest_relations(
    verified_inputs: list[VerifiedInput], payloads: Mapping[str, object]
) -> dict[str, ProtectedManifestRelation]:
    registries = [item for item in verified_inputs if item.kind.upper() == "PROTECTED_REGISTRY"]
    manifests = [item for item in verified_inputs if "protected_hash_manifest" in item.input_id.lower()]
    if not registries and not manifests:
        return {}
    if len(registries) != 1 or len(manifests) != 1:
        raise InventoryIntegrityError("PROTECTED_MANIFEST_INPUT_PAIR_INVALID")
    registry_input, manifest_input = registries[0], manifests[0]
    registry_payload = payloads[registry_input.input_id]
    manifest_payload = payloads[manifest_input.input_id]
    if not isinstance(registry_payload, Mapping) or not isinstance(manifest_payload, Mapping):
        raise InventoryIntegrityError("PROTECTED_MANIFEST_ROOT_INVALID")
    entries = _records(registry_payload, ("entries", "records"))
    files = _records(manifest_payload, ("files", "records"))
    if registry_payload.get("entry_count") != len(entries) or manifest_payload.get("file_count") != len(files):
        raise InventoryIntegrityError("PROTECTED_MANIFEST_DECLARED_COUNT_MISMATCH")
    registry_by_id: dict[str, Mapping[str, object]] = {}
    registry_paths: set[str] = set()
    for entry in entries:
        registry_id = entry.get("id")
        protected = entry.get("protected_file")
        if not isinstance(registry_id, str) or not registry_id:
            raise InventoryIntegrityError("PROTECTED_REGISTRY_ID_INVALID")
        if registry_id in registry_by_id:
            raise InventoryIntegrityError("PROTECTED_REGISTRY_DUPLICATE_ID")
        if not isinstance(protected, Mapping):
            raise InventoryIntegrityError("PROTECTED_REGISTRY_FILE_INVALID")
        path = protected.get("path")
        if not isinstance(path, str) or not path:
            raise InventoryIntegrityError("PROTECTED_REGISTRY_PATH_INVALID")
        if path in registry_paths:
            raise InventoryIntegrityError("PROTECTED_REGISTRY_DUPLICATE_PATH")
        registry_paths.add(path)
        registry_by_id[registry_id] = entry

    manifest_by_path: dict[str, Mapping[str, object]] = {}
    consumers: set[str] = set()
    for file_ in files:
        path = file_.get("path")
        file_consumers = file_.get("consumers")
        if not isinstance(path, str) or not path:
            raise InventoryIntegrityError("PROTECTED_MANIFEST_PATH_INVALID")
        if path in manifest_by_path:
            raise InventoryIntegrityError("PROTECTED_MANIFEST_DUPLICATE_PATH")
        if not isinstance(file_consumers, list) or len(file_consumers) != 1 or not isinstance(file_consumers[0], str):
            raise InventoryIntegrityError("PROTECTED_MANIFEST_CONSUMER_CARDINALITY")
        consumer = file_consumers[0]
        if consumer in consumers:
            raise InventoryIntegrityError("PROTECTED_MANIFEST_DUPLICATE_CONSUMER")
        consumers.add(consumer)
        manifest_by_path[path] = file_

    if len(entries) != len(files):
        raise InventoryIntegrityError("PROTECTED_MANIFEST_COUNT_MISMATCH")
    if consumers != set(registry_by_id) or set(manifest_by_path) != registry_paths:
        raise InventoryIntegrityError("PROTECTED_MANIFEST_RELATIONSHIP_MISMATCH")
    relations: dict[str, ProtectedManifestRelation] = {}
    for registry_id, entry in registry_by_id.items():
        protected = entry["protected_file"]
        assert isinstance(protected, Mapping)
        path = protected["path"]
        assert isinstance(path, str)
        file_ = manifest_by_path[path]
        if (
            file_.get("bytes") != protected.get("bytes")
            or file_.get("sha256") != protected.get("sha256")
            or file_.get("consumers") != [registry_id]
        ):
            raise InventoryIntegrityError("PROTECTED_MANIFEST_METADATA_CONFLICT")
        byte_count = protected.get("bytes")
        sha256 = protected.get("sha256")
        if not isinstance(byte_count, int) or not _valid_sha256(sha256):
            raise InventoryIntegrityError("PROTECTED_MANIFEST_METADATA_INVALID")
        relations[registry_id] = ProtectedManifestRelation(
            registry_id=registry_id,
            protected_path=path,
            bytes=byte_count,
            sha256=str(sha256).upper(),
            manifest_evidence_path=str(manifest_input.path),
            manifest_input_id=manifest_input.input_id,
            manifest_input_sha256=manifest_input.actual_sha256,
        )
    return relations
