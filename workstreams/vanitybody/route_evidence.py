"""Opt-in reader for private route evidence; unavailable in portable runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from .local_integration import LocalIntegration, load_local_integration


@dataclass(frozen=True)
class PayloadEvidence:
    visual_resource_uuid: str
    path: str
    sha256: str


@dataclass(frozen=True)
class RouteEvidence:
    root_uuid: str
    mode: str
    target_visual_resource_uuid: str
    target_path: str
    target_sha256: str
    protected_payloads: dict[str, PayloadEvidence]
    visual_evidence_pointer: str
    route_evidence_pointer: str


def load_route_evidence(integration: LocalIntegration | None = None) -> dict[tuple[str, str], RouteEvidence]:
    """Read only an explicitly configured local input; never auto-discover it."""
    path = (integration or load_local_integration()).route_evidence
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    return {
        (record["root_uuid"], record["mode"]): RouteEvidence(
            root_uuid=record["root_uuid"],
            mode=record["mode"],
            target_visual_resource_uuid=record["target"]["visual_resource_uuid"],
            target_path=record["target"]["path"],
            target_sha256=record["target"]["sha256"],
            protected_payloads={
                mode: PayloadEvidence(**payload)
                for mode, payload in record["protected_payloads"].items()
            },
            visual_evidence_pointer=record["visual_evidence"]["pointer"],
            route_evidence_pointer=record["route_evidence"]["pointer"],
        )
        for record in records
    }
