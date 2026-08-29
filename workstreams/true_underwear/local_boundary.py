"""Canonical containment rules for ignored local inputs and generated output."""

from __future__ import annotations

from pathlib import Path


WORKSTREAM_ROOT = Path(__file__).resolve().parent
LOCAL_ROOT = WORKSTREAM_ROOT / "local"
CANONICAL_SOURCE_CONFIG = LOCAL_ROOT / "source_config.json"
GENERATED_ROOT = LOCAL_ROOT / "generated"
CANONICAL_REJECTIONS = GENERATED_ROOT / "TRUE_UNDERWEAR_REJECTIONS.json"
CANONICAL_LEDGER_JSON = GENERATED_ROOT / "TRUE_UNDERWEAR_LEDGER.json"
CANONICAL_LEDGER_MD = GENERATED_ROOT / "TRUE_UNDERWEAR_LEDGER.md"
CANONICAL_AUDIT = GENERATED_ROOT / "TRUE_UNDERWEAR_ROUTE_AUDIT.json"


def _same_path(actual: str | Path, expected: Path) -> bool:
    return Path(actual).resolve(strict=False) == expected.resolve(strict=False)


def require_canonical_config(path: str | Path) -> Path:
    if not _same_path(path, CANONICAL_SOURCE_CONFIG):
        raise ValueError("source config must be workstreams/true_underwear/local/source_config.json")
    return CANONICAL_SOURCE_CONFIG


def require_generated_dir(path: str | Path) -> Path:
    if not _same_path(path, GENERATED_ROOT):
        raise ValueError("generated output must stay under workstreams/true_underwear/local/generated")
    return GENERATED_ROOT


def require_generated_file(path: str | Path, expected: Path) -> Path:
    if not _same_path(path, expected):
        raise ValueError("generated output must use its canonical local/generated filename")
    return expected
