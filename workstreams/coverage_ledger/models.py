from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RouteRecord:
    mode: str
    visual_resource_uuid: str | None
    path: str | None
    provenance: str
    mesh_sha256: str | None = None
    gameplay_result: str = "NOT RUN"


@dataclass
class GarmentRecord:
    identity: str
    source_module: dict[str, str]
    root_template_uuid: str | None
    stats_entry: str | None
    effective_slot: str
    inheritance_chain: list[str]
    source_visual_resource_uuid: str | None
    source_visual_resource_path: str | None
    body_family: str
    garment_family: str
    topology_family: str
    component_contract: str = "UNASSESSED"
    routes: dict[str, RouteRecord] = field(default_factory=dict)
    disposition: str = "DEFERRED WITH CAUSE"
    evidence: list[str] = field(default_factory=list)
    known_defect: str | None = None
    protected_controls: list[str] = field(default_factory=list)
    package_ownership: dict[str, Any] | None = None
    candidate_profile: dict[str, Any] | None = None
    readiness_evidence: list[str] = field(default_factory=list)
    next_action: str = "Preserve static evidence and obtain a bounded gameplay result."
    reconciliation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
