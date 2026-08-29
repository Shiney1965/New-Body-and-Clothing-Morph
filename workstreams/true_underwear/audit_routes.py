from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .inventory import build_inventory
    from .local_boundary import CANONICAL_AUDIT, CANONICAL_SOURCE_CONFIG, require_canonical_config, require_generated_file
    from .route_audit import audits_to_json, audit_routes
    from .source_config import load_source_roots
except ImportError:  # Direct script execution from this directory only.
    from inventory import build_inventory
    from local_boundary import CANONICAL_AUDIT, CANONICAL_SOURCE_CONFIG, require_canonical_config, require_generated_file
    from route_audit import audits_to_json, audit_routes
    from source_config import load_source_roots


def write_audit(
    config_path: str | Path = CANONICAL_SOURCE_CONFIG,
    output_path: str | Path = CANONICAL_AUDIT,
) -> int:
    """Write only the canonical ignored local route-audit output."""

    require_canonical_config(config_path)
    output_path = require_generated_file(output_path, CANONICAL_AUDIT)

    records = build_inventory(load_source_roots(config_path))
    audits = audit_routes(records, {}, {})
    payload = {
        "schema": "clothmorph-true-underwear-route-audit-v1",
        "summary": {
            "records": len(audits),
            "ready_for_test": sum(audit.status == "READY FOR TEST" for audit in audits),
            "missing_route_or_build": sum(audit.status == "MISSING ROUTE / BUILD" for audit in audits),
            "out_of_scope": sum(audit.status == "OUT_OF_SCOPE" for audit in audits),
        },
        "audits": audits_to_json(audits),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the canonical ignored local true-underwear route audit."
    )
    parser.parse_args(argv)
    return write_audit()


if __name__ == "__main__":
    raise SystemExit(main())
