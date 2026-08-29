from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Mapping

try:
    from .inventory import GarmentRecord
except ImportError:  # Direct script execution from this directory only.
    from inventory import GarmentRecord


@dataclass(frozen=True)
class ModeRoute:
    target_vr: str
    target_path: str
    target_sha256: str
    protected: bool
    evidence_status: str


@dataclass(frozen=True)
class RouteAudit:
    source: str
    stats_entry: str
    root_template_uuid: str
    source_vr: str
    status: str
    vanilla: ModeRoute
    sbbf: ModeRoute
    bcb: ModeRoute


EMPTY_ROUTE = ModeRoute("", "", "", False, "MISSING")
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
# Only this state records the completed target-path/hash/provenance contract.
ROUTE_READY_EVIDENCE_STATUSES = {"PROVENANCE_VALIDATED"}


def _map_route(
    source_vr: str, mode: str, refit_maps: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> ModeRoute:
    mapping = refit_maps.get(mode, {}).get(source_vr, {})
    target_vr = mapping.get("target_vr", "")
    return ModeRoute(
        target_vr=target_vr,
        target_path=mapping.get("target_path", ""),
        target_sha256=mapping.get("target_sha256", ""),
        protected=mapping.get("protected") is True,
        evidence_status=mapping.get("evidence_status", "MISSING"),
    )


def _route_contract_complete(route: ModeRoute) -> bool:
    return (
        bool(route.target_vr)
        and bool(route.target_path)
        and SHA256_PATTERN.fullmatch(route.target_sha256) is not None
        and route.evidence_status in ROUTE_READY_EVIDENCE_STATUSES
    )


def audit_one(
    record: GarmentRecord,
    visual_banks: Mapping[str, object],
    refit_maps: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> RouteAudit:
    """Audit route provenance without promoting unknown routes to accepted."""

    del visual_banks
    if record.effective_slot != "Underwear":
        return RouteAudit(record.source, record.stats_entry, record.root_template_uuid, record.source_visual_resource_uuid, "OUT_OF_SCOPE", EMPTY_ROUTE, EMPTY_ROUTE, EMPTY_ROUTE)

    vanilla = _map_route(record.source_visual_resource_uuid, "Vanilla", refit_maps)
    sbbf = _map_route(record.source_visual_resource_uuid, "SBBF", refit_maps)
    bcb = _map_route(record.source_visual_resource_uuid, "BCB", refit_maps)

    complete_targets = all(_route_contract_complete(route) for route in (vanilla, sbbf, bcb))
    status = "READY FOR TEST" if complete_targets else "MISSING ROUTE / BUILD"
    return RouteAudit(record.source, record.stats_entry, record.root_template_uuid, record.source_visual_resource_uuid, status, vanilla, sbbf, bcb)


def audit_routes(
    records: list[GarmentRecord],
    visual_banks: Mapping[str, object],
    refit_maps: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> list[RouteAudit]:
    return [audit_one(record, visual_banks, refit_maps) for record in records]


def audits_to_json(audits: list[RouteAudit]) -> list[dict[str, object]]:
    return [asdict(audit) for audit in audits]
