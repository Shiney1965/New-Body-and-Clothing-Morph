"""Portable boundary for optional local ledger generation inputs.

The public unit-test surface deliberately has no dependency on retained source
trees, generated evidence, or a particular workstation layout.  A local
operator may opt into generation by supplying a small JSON configuration file
through ``COVERAGE_LEDGER_LOCAL_CONFIG`` or an explicit path.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


LOCAL_CONFIG_ENV = "COVERAGE_LEDGER_LOCAL_CONFIG"
WORKSTREAM_ROOT = Path(__file__).resolve().parent
LOCAL_OUTPUT_ROOT = WORKSTREAM_ROOT / "local"
CANONICAL_LOCAL_CONFIGURATION_PATH = LOCAL_OUTPUT_ROOT / "local_configuration.json"


class LocalConfigurationUnavailable(RuntimeError):
    """Raised when a caller requests local generation without opt-in inputs."""


@dataclass(frozen=True)
class LocalConfiguration:
    source_registry_path: Path
    prior_sources_path: Path
    evidence_dir: Path
    card_dir: Path


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _contained_output(path: Path) -> Path:
    """Resolve a generated output and reject any path outside the local boundary."""
    resolved_path = path.resolve()
    resolved_root = LOCAL_OUTPUT_ROOT.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise LocalConfigurationUnavailable(
            f"local generation skipped: generated output must remain inside local directory: {path}"
        ) from error
    return resolved_path


def validate_generated_outputs(configuration: LocalConfiguration) -> LocalConfiguration:
    """Enforce the canonical local-output boundary for every caller path."""
    return LocalConfiguration(
        source_registry_path=configuration.source_registry_path,
        prior_sources_path=configuration.prior_sources_path,
        evidence_dir=_contained_output(configuration.evidence_dir),
        card_dir=_contained_output(configuration.card_dir),
    )


def load_local_configuration(config_path: Path | None = None) -> LocalConfiguration:
    """Load explicitly selected local inputs; never infer fixed source paths."""
    selected = config_path or (Path(value) if (value := os.environ.get(LOCAL_CONFIG_ENV)) else None)
    if selected is None:
        raise LocalConfigurationUnavailable(
            f"local generation skipped: set {LOCAL_CONFIG_ENV} to a local JSON configuration file"
        )
    if selected.resolve() != CANONICAL_LOCAL_CONFIGURATION_PATH.resolve():
        raise LocalConfigurationUnavailable(
            f"local generation skipped: configuration must be the canonical local configuration: {CANONICAL_LOCAL_CONFIGURATION_PATH}"
        )
    if not selected.is_file():
        raise LocalConfigurationUnavailable(f"local generation skipped: configuration file not found: {selected}")
    data = json.loads(selected.read_text(encoding="utf-8"))
    required = {"source_registry_path", "prior_sources_path", "evidence_dir", "card_dir"}
    missing = sorted(required - set(data))
    if missing:
        raise LocalConfigurationUnavailable(f"local generation skipped: configuration missing {', '.join(missing)}")
    base = selected.parent
    return validate_generated_outputs(LocalConfiguration(
        source_registry_path=_resolve(base, data["source_registry_path"]),
        prior_sources_path=_resolve(base, data["prior_sources_path"]),
        evidence_dir=_resolve(base, data["evidence_dir"]),
        card_dir=_resolve(base, data["card_dir"]),
    ))
