"""Independent raw-byte inventories for the release master ledger audit."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping

from .audit import InventorySets
from .configuration import VerifiedInput


BASE_GAME_SOURCE_PROFILE_UNRESOLVED = "BASE_GAME_SOURCE_PROFILE_UNRESOLVED"


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
        )


def extract_independent_inventories(
    verified_inputs: list[VerifiedInput],
) -> IndependentInventories:
    payloads = {input_.input_id: _read_verified_json(input_) for input_ in verified_inputs}
    relations = _protected_manifest_relations(verified_inputs, payloads)
    source_observations: set[str] = set()
    prior_evidence = {
        str(input_.path)
        for input_ in verified_inputs
        if input_.kind.upper() == "SUPPORTING_EVIDENCE"
    }
    packaged_records: set[str] = set()
    required_profiles: set[str] = {BASE_GAME_SOURCE_PROFILE_UNRESOLVED}
    complete_profiles: set[str] = set()

    for input_ in verified_inputs:
        payload = payloads[input_.input_id]
        if input_.kind.upper() in {
            "PROTECTED_REGISTRY", "COVERAGE", "TRUE_UNDERWEAR", "VANITYBODY", "BCBSCANTILY",
        }:
            source_observations.update(_source_observation_ids(input_, payload))
        if input_.kind.upper() == "PACKAGE":
            packaged_records.update(_package_ids(payload))
        if input_.input_id == "source_profile_inventory":
            required, complete = _source_profiles(payload)
            required_profiles.update(required)
            complete_profiles.update(complete)

    return IndependentInventories(
        source_observations=frozenset(source_observations),
        prior_evidence=frozenset(prior_evidence),
        packaged_records=frozenset(packaged_records),
        required_source_profiles=frozenset(required_profiles),
        complete_source_profiles=frozenset(complete_profiles),
        protected_manifest_relations=relations,
    )


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
    keys_by_kind = {
        "PROTECTED_REGISTRY": ("entries", "records"),
        "COVERAGE": ("records",),
        "TRUE_UNDERWEAR": ("records",),
        "VANITYBODY": ("records",),
        "BCBSCANTILY": ("items", "records"),
    }
    records = _records(payload, keys_by_kind[input_.kind.upper()])
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


def _source_profile_id(module: Mapping[str, object]) -> str:
    uuid = module.get("uuid")
    version64 = module.get("version64")
    if not isinstance(uuid, str) or not uuid or not isinstance(version64, str) or not version64:
        raise InventoryIntegrityError("SOURCE_PROFILE_MODULE_IDENTITY_INVALID")
    return f"SOURCE_PROFILE:{uuid}:{version64}"


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
