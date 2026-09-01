"""Hash-locked local evidence configuration for the closure workstream."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


WORKSTREAM_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT_NAME = "local"
CONFIG_NAME = "config.json"
SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


class ConfigurationError(ValueError):
    """Raised when the local evidence configuration is not safe to consume."""


class EvidenceIntegrityError(ConfigurationError):
    """Raised when a registered evidence input does not match its hash lock."""


@dataclass(frozen=True)
class EvidenceInput:
    """One local evidence file which must match an explicit SHA-256 digest."""

    input_id: str
    kind: str
    path: Path
    expected_sha256: str


@dataclass(frozen=True)
class LocalConfiguration:
    """The complete local-only evidence configuration."""

    inputs: tuple[EvidenceInput, ...]


@dataclass(frozen=True)
class VerifiedInput:
    """A local evidence file whose bytes match its declared SHA-256 digest."""

    input_id: str
    kind: str
    path: Path
    bytes: int
    expected_sha256: str
    actual_sha256: str


def _canonical_config_path(workstream_root: Path) -> Path:
    return workstream_root.resolve(strict=False) / LOCAL_ROOT_NAME / CONFIG_NAME


def _required_text(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"CONFIGURATION_INVALID_{key.upper()}")
    return value


def _resolve_config_path(config_path: Path, configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (config_path.parent / candidate).resolve(strict=False)


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
    """Load only the ignored local/config.json evidence registry."""
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
    return LocalConfiguration(inputs=inputs)


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


def verify_evidence_inputs(config: LocalConfiguration) -> tuple[VerifiedInput, ...]:
    """Verify every registered input before any downstream reader may consume it."""
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
    return tuple(verified)
