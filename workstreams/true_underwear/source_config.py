"""Load explicitly supplied, portable source locations for offline inventory work."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .inventory import SourceInput, SourceRoots
    from .local_boundary import CANONICAL_REJECTIONS, require_canonical_config, require_generated_file
except ImportError:  # Direct script execution from this directory only.
    from inventory import SourceInput, SourceRoots
    from local_boundary import CANONICAL_REJECTIONS, require_canonical_config, require_generated_file


def _relative_path(config_dir: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.drive:
        raise ValueError("source-config paths must be relative to the config file")
    return config_dir / candidate


def _path_list(config_dir: Path, values: list[str]) -> tuple[Path, ...]:
    return tuple(_relative_path(config_dir, value) for value in values)


def _optional_path(config_dir: Path, value: str | None) -> Path | None:
    return None if value is None else _relative_path(config_dir, value)


def _source(config_dir: Path, data: dict[str, Any]) -> SourceInput:
    return SourceInput(
        source=data["source"],
        module_folder=data["module_folder"],
        module_name=data["module_name"],
        module_uuid=data["module_uuid"],
        version64=data["version64"],
        stats=_path_list(config_dir, data["stats"]),
        roots=_path_list(config_dir, data["roots"]),
        meta_path=_optional_path(config_dir, data.get("meta_path")),
        original_pak=_optional_path(config_dir, data.get("original_pak")),
        dependency_stats=_path_list(config_dir, data.get("dependency_stats", [])),
    )


def load_source_roots(config_path: str | Path) -> SourceRoots:
    """Return source roots from the one canonical ignored local configuration."""

    path = require_canonical_config(config_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source config must contain a JSON object")
    try:
        config_dir = path.parent
        roots = SourceRoots(
            shared_stats=_path_list(config_dir, payload["shared_stats"]),
            sources=tuple(_source(config_dir, source) for source in payload["sources"]),
            rejections_path=_relative_path(config_dir, payload["rejections_path"]),
        )
        require_generated_file(roots.rejections_path, CANONICAL_REJECTIONS)
        return roots
    except (KeyError, TypeError) as error:
        raise ValueError("source config is missing a required field") from error
