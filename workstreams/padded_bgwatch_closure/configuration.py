"""Hash-pinned local input boundary for offline Padded BG Watch work."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .models import BASELINES


WORKSTREAM_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT_NAME = "local"
CONFIG_NAME = "config.json"
GENERATED_ROOT_NAME = "generated"


class ConfigurationError(ValueError):
    """Raised when a local configuration violates the offline boundary."""


class EvidenceIntegrityError(ConfigurationError):
    """Raised when a configured input does not match its required hash."""


@dataclass(frozen=True)
class HashPinnedInput:
    """A local path bound to a public immutable SHA-256 identity."""

    input_id: str
    path: Path
    expected_sha256: str


@dataclass(frozen=True)
class LocalConfiguration:
    """The only two geometry inputs allowed to enter the closure workstream."""

    pristine_source_dae: HashPinnedInput
    bcb_body_glb: HashPinnedInput

    @property
    def inputs(self) -> tuple[HashPinnedInput, HashPinnedInput]:
        """Return inputs in the required hash-first verification order."""
        return (self.pristine_source_dae, self.bcb_body_glb)


@dataclass(frozen=True)
class VerifiedInput:
    """A byte-streamed input that matched its hash and may now be parsed."""

    input_id: str
    path: Path
    bytes: int
    expected_sha256: str
    actual_sha256: str


def _local_root(workstream_root: Path) -> Path:
    return workstream_root.resolve(strict=False) / LOCAL_ROOT_NAME


def canonical_local_config_path(workstream_root: Path = WORKSTREAM_ROOT) -> Path:
    """Return the sole permitted, ignored local configuration location."""
    return _local_root(workstream_root) / CONFIG_NAME


def _resolve_input_path(config_path: Path, value: object, expected_suffix: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfigurationError("CONFIGURATION_INVALID_INPUT_PATH")
    candidate = Path(value)
    resolved = candidate.resolve(strict=False) if candidate.is_absolute() else (
        config_path.parent / candidate
    ).resolve(strict=False)
    if resolved.suffix.lower() != expected_suffix:
        raise ConfigurationError("CONFIGURATION_INVALID_INPUT_SUFFIX")
    return resolved


def load_local_configuration(workstream_root: Path = WORKSTREAM_ROOT) -> LocalConfiguration:
    """Load paths only; callers must hash-verify them before geometry parsing."""
    config_path = canonical_local_config_path(workstream_root)
    if not config_path.is_file():
        raise ConfigurationError("CANONICAL_LOCAL_CONFIG_MISSING")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigurationError("CONFIGURATION_INVALID_JSON") from error
    if not isinstance(payload, dict):
        raise ConfigurationError("CONFIGURATION_INVALID_ROOT")
    required = {"pristine_source_dae", "bcb_body_glb"}
    if set(payload) != required:
        raise ConfigurationError("CONFIGURATION_INVALID_INPUT_SET")
    return LocalConfiguration(
        pristine_source_dae=HashPinnedInput(
            input_id="pristine_source_dae",
            path=_resolve_input_path(config_path, payload["pristine_source_dae"], ".dae"),
            expected_sha256=BASELINES.pristine_source_dae.sha256,
        ),
        bcb_body_glb=HashPinnedInput(
            input_id="bcb_body_glb",
            path=_resolve_input_path(config_path, payload["bcb_body_glb"], ".glb"),
            expected_sha256=BASELINES.bcb_body_glb.sha256,
        ),
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


def verify_input_hashes(configuration: LocalConfiguration) -> tuple[VerifiedInput, ...]:
    """Stream-hash every input before any caller is permitted to parse it."""
    verified: list[VerifiedInput] = []
    for input_ in configuration.inputs:
        byte_count, actual_sha256 = _hash_input(input_.path)
        if actual_sha256 != input_.expected_sha256:
            raise EvidenceIntegrityError(f"EVIDENCE_HASH_MISMATCH:{input_.input_id}")
        verified.append(VerifiedInput(
            input_id=input_.input_id,
            path=input_.path,
            bytes=byte_count,
            expected_sha256=input_.expected_sha256,
            actual_sha256=actual_sha256,
        ))
    return tuple(verified)


def generated_output_path(workstream_root: Path, relative_path: str | Path) -> Path:
    """Resolve one output path only when it remains below local/generated."""
    generated_root = _local_root(workstream_root) / GENERATED_ROOT_NAME
    candidate = generated_root / Path(relative_path)
    resolved_root = generated_root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate == resolved_root or resolved_root not in resolved_candidate.parents:
        raise ConfigurationError("OUTPUT_OUTSIDE_LOCAL_GENERATED")
    return resolved_candidate
