"""Hash-locked local configuration boundary for release-ledger evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


WORKSTREAM_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT_NAME = "local"
CONFIG_NAME = "config.json"
GENERATED_ROOT_NAME = "generated"
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


class ConfigurationError(ValueError):
    """Raised when the public local configuration violates its boundary."""


class EvidenceIntegrityError(ConfigurationError):
    """Raised when a registered evidence input cannot be hash-verified."""


@dataclass(frozen=True)
class EvidenceInput:
    """One configured evidence input that must be verified before adaptation."""

    input_id: str
    kind: str
    path: Path
    expected_sha256: str


@dataclass(frozen=True)
class LocalConfiguration:
    """The complete local-only evidence configuration for this workstream."""

    inputs: tuple[EvidenceInput, ...]
    output_path: Path
    exclusion_events_dir: Path | None = None


@dataclass(frozen=True)
class VerifiedInput:
    """A registered input whose exact bytes match its declared SHA-256 digest."""

    input_id: str
    kind: str
    path: Path
    bytes: int
    expected_sha256: str
    actual_sha256: str


def _local_root(workstream_root: Path) -> Path:
    return workstream_root.resolve(strict=False) / LOCAL_ROOT_NAME


def _canonical_config_path(workstream_root: Path) -> Path:
    return _local_root(workstream_root) / CONFIG_NAME


def _resolve_config_path(config_path: Path, configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (config_path.parent / candidate).resolve(strict=False)


def validate_output_path(path: Path, workstream_root: Path) -> Path:
    """Resolve an output path only when it is strictly below local/generated."""
    generated_root = _local_root(workstream_root) / GENERATED_ROOT_NAME
    resolved_output = path.resolve(strict=False)
    resolved_generated_root = generated_root.resolve(strict=False)
    if resolved_output == resolved_generated_root or resolved_generated_root not in resolved_output.parents:
        raise ConfigurationError("OUTPUT_OUTSIDE_LOCAL_GENERATED")
    return resolved_output


def validate_exclusion_events_dir(path: Path, workstream_root: Path) -> Path:
    """Resolve an event history directory only when it stays below local/."""
    local_root = _local_root(workstream_root).resolve(strict=False)
    resolved = path.resolve(strict=False)
    if resolved == local_root or local_root not in resolved.parents:
        raise ConfigurationError("EXCLUSION_EVENTS_OUTSIDE_LOCAL")
    return resolved


def _required_text(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"CONFIGURATION_INVALID_{key.upper()}")
    return value


def _parse_input(config_path: Path, value: object) -> EvidenceInput:
    if not isinstance(value, dict):
        raise ConfigurationError("CONFIGURATION_INVALID_INPUT")
    expected_sha256 = _required_text(value, "expected_sha256")
    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise ConfigurationError("CONFIGURATION_INVALID_EXPECTED_SHA256")
    return EvidenceInput(
        input_id=_required_text(value, "input_id"),
        kind=_required_text(value, "kind"),
        path=_resolve_config_path(config_path, _required_text(value, "path")),
        expected_sha256=expected_sha256,
    )


def load_local_configuration() -> LocalConfiguration:
    """Load only workstreams/release_master_ledger/local/config.json."""
    config_path = _canonical_config_path(WORKSTREAM_ROOT)
    if not config_path.is_file():
        raise ConfigurationError("CANONICAL_LOCAL_CONFIG_MISSING")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigurationError("CONFIGURATION_INVALID_JSON") from error
    if not isinstance(payload, dict):
        raise ConfigurationError("CONFIGURATION_INVALID_ROOT")
    raw_inputs = payload.get("inputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise ConfigurationError("CONFIGURATION_INVALID_INPUTS")
    inputs = tuple(_parse_input(config_path, value) for value in raw_inputs)
    if len({input_.input_id for input_ in inputs}) != len(inputs):
        raise ConfigurationError("CONFIGURATION_DUPLICATE_INPUT_ID")
    output_path = validate_output_path(
        _resolve_config_path(config_path, _required_text(payload, "output_path")),
        WORKSTREAM_ROOT,
    )
    exclusion_events_dir = None
    if "exclusion_events_dir" in payload:
        exclusion_events_dir = validate_exclusion_events_dir(
            _resolve_config_path(
                config_path, _required_text(payload, "exclusion_events_dir")
            ),
            WORKSTREAM_ROOT,
        )
    return LocalConfiguration(
        inputs=inputs,
        output_path=output_path,
        exclusion_events_dir=exclusion_events_dir,
    )


def _hash_input(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                byte_count += len(chunk)
                digest.update(chunk)
    except FileNotFoundError as error:
        raise EvidenceIntegrityError(f"EVIDENCE_INPUT_MISSING:{path}") from error
    except OSError as error:
        raise EvidenceIntegrityError(f"EVIDENCE_INPUT_UNREADABLE:{path}") from error
    return byte_count, digest.hexdigest().upper()


def verify_evidence_inputs(config: LocalConfiguration) -> list[VerifiedInput]:
    """Hash every registered input before any downstream adapter may parse it."""
    verified: list[VerifiedInput] = []
    for input_ in config.inputs:
        byte_count, actual_sha256 = _hash_input(input_.path)
        if actual_sha256 != input_.expected_sha256:
            raise EvidenceIntegrityError(
                f"EVIDENCE_HASH_MISMATCH:{input_.input_id}:{input_.path}"
            )
        verified.append(VerifiedInput(
            input_id=input_.input_id,
            kind=input_.kind,
            path=input_.path,
            bytes=byte_count,
            expected_sha256=input_.expected_sha256,
            actual_sha256=actual_sha256,
        ))
    return verified
