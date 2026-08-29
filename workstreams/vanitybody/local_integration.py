"""Opt-in boundary for private VanityBody inputs and generated local results.

This module deliberately does not discover evidence, staging, or workstation
paths.  A maintainer must create ``local/config.json`` from the documented
contract before integration-only commands can read any private input.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


LOCAL_ROOT = Path(__file__).with_name("local").resolve()
DEFAULT_CONFIG = LOCAL_ROOT / "config.json"


class LocalIntegrationUnavailable(RuntimeError):
    """Raised instead of falling back to ignored evidence or staging data."""


@dataclass(frozen=True)
class LocalIntegration:
    anchor_evidence: Path
    route_evidence: Path
    glb_directory: Path
    ledger_input: Path
    output_directory: Path


def _existing_file(value: object, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise LocalIntegrationUnavailable(f"{name} must name a local file")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise LocalIntegrationUnavailable(f"{name} is unavailable: {path}")
    return path


def load_local_integration(config_path: Path | None = None) -> LocalIntegration:
    """Load explicitly configured private inputs, with a fixed local/ output root."""
    canonical = DEFAULT_CONFIG.resolve()
    config = (config_path or canonical).resolve()
    if config != canonical:
        raise LocalIntegrationUnavailable("local integration must use canonical local/config.json")
    if not config.is_file():
        raise LocalIntegrationUnavailable("local integration is not configured")
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalIntegrationUnavailable("local integration configuration is unreadable") from exc
    if not isinstance(data, dict):
        raise LocalIntegrationUnavailable("local integration configuration must be an object")
    output = (LOCAL_ROOT / "generated").resolve()
    declared_output = data.get("output_dir", "generated")
    if declared_output != "generated":
        raise LocalIntegrationUnavailable("output_dir must be the fixed local/generated boundary")
    glb_directory = _existing_file(data.get("glb_manifest"), "glb_manifest").parent
    return LocalIntegration(
        anchor_evidence=_existing_file(data.get("anchor_evidence"), "anchor_evidence"),
        route_evidence=_existing_file(data.get("route_evidence"), "route_evidence"),
        glb_directory=glb_directory,
        ledger_input=_existing_file(data.get("ledger_input"), "ledger_input"),
        output_directory=output,
    )


def local_output_directory(value: Path) -> Path:
    """Reject any generated-output destination outside fixed ``local/generated``."""
    candidate = Path(value).resolve()
    expected = (LOCAL_ROOT / "generated").resolve()
    if candidate != expected:
        raise LocalIntegrationUnavailable("output_dir must be the fixed local/generated boundary")
    return candidate
