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

    configuration_path: Path
    inputs: tuple[HashPinnedInput, ...]

    @property
    def pristine_source_dae(self) -> HashPinnedInput:
        """Return the pristine DAE input after canonical configuration loading."""
        return self.inputs[0]

    @property
    def bcb_body_glb(self) -> HashPinnedInput:
        """Return the BCB GLB input after canonical configuration loading."""
        return self.inputs[1]


@dataclass(frozen=True)
class VerifiedInput:
    """Exact immutable content that matched its hash and may now be parsed."""

    input_id: str
    content: bytes
    byte_count: int
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


def _canonical_input_contract() -> tuple[tuple[str, str, str], ...]:
    """Return the sole allowed input IDs, suffixes, and immutable digests."""
    return (
        (
            "pristine_source_dae",
            ".dae",
            BASELINES.pristine_source_dae.sha256,
        ),
        (
            "bcb_body_glb",
            ".glb",
            BASELINES.bcb_body_glb.sha256,
        ),
    )


def _validate_canonical_configuration(
    configuration: LocalConfiguration,
    workstream_root: Path,
) -> None:
    """Reject any configuration that is not the exact public two-input contract."""
    if type(configuration) is not LocalConfiguration:
        raise ConfigurationError("CANONICAL_INPUT_CONTRACT_VIOLATION")
    if configuration.configuration_path.resolve(strict=False) != canonical_local_config_path(
        workstream_root
    ).resolve(strict=False):
        raise ConfigurationError("CANONICAL_INPUT_CONTRACT_VIOLATION")
    expected = _canonical_input_contract()
    if len(configuration.inputs) != len(expected):
        raise ConfigurationError("CANONICAL_INPUT_CONTRACT_VIOLATION")
    for input_, (input_id, suffix, sha256) in zip(configuration.inputs, expected):
        if (
            input_.input_id != input_id
            or input_.path.suffix.lower() != suffix
            or input_.expected_sha256 != sha256
        ):
            raise ConfigurationError("CANONICAL_INPUT_CONTRACT_VIOLATION")


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
        configuration_path=config_path,
        inputs=(
            HashPinnedInput(
                input_id="pristine_source_dae",
                path=_resolve_input_path(config_path, payload["pristine_source_dae"], ".dae"),
                expected_sha256=BASELINES.pristine_source_dae.sha256,
            ),
            HashPinnedInput(
                input_id="bcb_body_glb",
                path=_resolve_input_path(config_path, payload["bcb_body_glb"], ".glb"),
                expected_sha256=BASELINES.bcb_body_glb.sha256,
            ),
        ),
    )


def _read_and_hash_input(path: Path) -> tuple[bytes, str]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                chunks.append(chunk)
                digest.update(chunk)
    except FileNotFoundError as error:
        raise EvidenceIntegrityError(f"EVIDENCE_INPUT_MISSING:{path}") from error
    except OSError as error:
        raise EvidenceIntegrityError(f"EVIDENCE_INPUT_UNREADABLE:{path}") from error
    return b"".join(chunks), digest.hexdigest().upper()


def _verify_canonical_configuration(
    configuration: LocalConfiguration,
    workstream_root: Path,
) -> tuple[VerifiedInput, ...]:
    """Test-only lower-level verifier; public callers use the canonical loader."""
    _validate_canonical_configuration(configuration, workstream_root)
    verified: list[VerifiedInput] = []
    for input_ in configuration.inputs:
        content, actual_sha256 = _read_and_hash_input(input_.path)
        if actual_sha256 != input_.expected_sha256:
            raise EvidenceIntegrityError(f"EVIDENCE_HASH_MISMATCH:{input_.input_id}")
        verified.append(VerifiedInput(
            input_id=input_.input_id,
            content=content,
            byte_count=len(content),
            expected_sha256=input_.expected_sha256,
            actual_sha256=actual_sha256,
        ))
    return tuple(verified)


def load_and_verify_canonical_inputs(
    workstream_root: Path = WORKSTREAM_ROOT,
) -> tuple[VerifiedInput, ...]:
    """Return immutable verified input bytes from the sole canonical local config."""
    configuration = load_local_configuration(workstream_root)
    return _verify_canonical_configuration(configuration, workstream_root)


def generated_output_path(workstream_root: Path, relative_path: str | Path) -> Path:
    """Resolve one output path only when it remains below local/generated."""
    generated_root = _local_root(workstream_root) / GENERATED_ROOT_NAME
    candidate = generated_root / Path(relative_path)
    resolved_root = generated_root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate == resolved_root or resolved_root not in resolved_candidate.parents:
        raise ConfigurationError("OUTPUT_OUTSIDE_LOCAL_GENERATED")
    return resolved_candidate
