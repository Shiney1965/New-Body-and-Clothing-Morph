from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

try:
    from .inventory import classify_creation_paths
    from .local_boundary import CANONICAL_REJECTIONS, CANONICAL_SOURCE_CONFIG, GENERATED_ROOT, require_canonical_config, require_generated_dir, require_generated_file
    from .source_config import load_source_roots
except ImportError:  # Direct script execution from this directory only.
    from inventory import classify_creation_paths
    from local_boundary import CANONICAL_REJECTIONS, CANONICAL_SOURCE_CONFIG, GENERATED_ROOT, require_canonical_config, require_generated_dir, require_generated_file
    from source_config import load_source_roots


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_rejections(rejections: tuple[dict[str, object], ...] | list[dict[str, object]]) -> None:
    """Persist rejection evidence only at the fixed ignored local filename."""

    output_path = require_generated_file(CANONICAL_REJECTIONS, CANONICAL_REJECTIONS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rejections, indent=2) + "\n", encoding="utf-8")


def write_ledger(
    config_path: str | Path = CANONICAL_SOURCE_CONFIG,
    output_dir: str | Path = GENERATED_ROOT,
) -> int:
    """Generate only the canonical ignored local ledger outputs."""

    require_canonical_config(config_path)
    output_dir = require_generated_dir(output_dir)

    roots = load_source_roots(config_path)
    classification = classify_creation_paths(roots)
    records = [
        record
        for record in classification.records
        if record.effective_slot == "Underwear"
    ]
    if any(record.effective_slot != "Underwear" for record in records):
        raise RuntimeError("true-underwear ledger contains a non-Underwear record")
    if any(record.disposition == "UNCLASSIFIED" for record in records):
        raise RuntimeError("true-underwear ledger contains an unclassified record")
    write_rejections(classification.rejections)
    source_paths = [path for source in roots.sources for path in (*source.stats, *source.roots)]
    source_manifests = []
    for source in roots.sources:
        members = [*source.stats, *source.roots, source.meta_path]
        source_manifests.append({
            "source": source.source,
            "module_identity": {"folder": source.module_folder, "name": source.module_name, "uuid": source.module_uuid, "version64": source.version64},
            "original_pak": ({"path": str(source.original_pak), "sha256": sha256(source.original_pak)} if source.original_pak else {"status": "NO_PAK_INPUT_BASE_OR_WORKTREE_EXTRACTION"}),
            "extraction_members": [{"path": str(path), "sha256": sha256(path)} for path in members if path and path.exists()],
        })
    payload = {
        "schema": "clothmorph-true-underwear-ledger-v2",
        "classification_rule": "effective Slot resolved through using inheritance equals Underwear",
        "scope": [source.source for source in roots.sources],
        "source_inputs": [
            {"path": str(path), "sha256": sha256(path)}
            for path in (*roots.shared_stats, *source_paths)
            if path.exists()
        ],
        "source_manifests": source_manifests,
        "summary": {
            "records": len(records),
            "by_source": {
                source: sum(record.source == source for record in records)
                for source in [source.source for source in roots.sources]
            },
            "unclassified": 0,
        },
        "records": [asdict(record) for record in records],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "TRUE_UNDERWEAR_LEDGER.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["# True Underwear Ledger", "", "Classification: effective `Slot = Underwear` only.", "", "| Source | Records |", "|---|---:|"]
    lines.extend(f"| {source} | {count} |" for source, count in payload["summary"]["by_source"].items())
    lines.extend(["", "Gameplay status for every record: `NOT RUN`.", ""])
    (output_dir / "TRUE_UNDERWEAR_LEDGER.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the canonical ignored local true-underwear ledger."
    )
    parser.parse_args(argv)
    return write_ledger()


if __name__ == "__main__":
    raise SystemExit(main())
