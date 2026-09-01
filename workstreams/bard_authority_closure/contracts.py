"""Immutable current-evidence contracts for Bard and Robe of Authority."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable


class ContractViolation(ValueError):
    """Raised when a proposed candidate escapes a frozen contract boundary."""


@dataclass(frozen=True)
class ComponentContract:
    name: str
    visual_resource_uuid: str
    source_file: str
    sha256: str
    object_ids: tuple[str, ...]
    bone_count: int

    @property
    def object_count(self) -> int:
        return len(self.object_ids)


@dataclass(frozen=True)
class FailureEvidence:
    flips: int
    new_zero_area: int
    below_area_floor: int
    minimum_area_ratio: float


@dataclass(frozen=True)
class ProtectedBCBIdentity:
    component_hashes: tuple[str, str]
    replacement_routes: int


@dataclass(frozen=True)
class BardContract:
    item_uuid: str
    components: tuple[ComponentContract, ComponentContract]
    protected_bcb: ProtectedBCBIdentity
    failure_evidence: tuple[tuple[str, str, FailureEvidence], ...]

    def failure(self, mode: str, stream: str) -> FailureEvidence:
        for evidence_mode, evidence_stream, evidence in self.failure_evidence:
            if (evidence_mode, evidence_stream) == (mode, stream):
                return evidence
        raise ContractViolation(f"BARD_FAILURE_EVIDENCE_MISSING:{mode}:{stream}")

    def require_emittable_pair(self, mode: str, components: Iterable[str]) -> tuple[str, str]:
        pair = tuple(components)
        if mode == "bcb":
            raise ContractViolation("BARD_BCB_PROTECTED_NO_REPLACEMENT")
        if mode not in {"vanilla", "sbbf"}:
            raise ContractViolation(f"BARD_UNSUPPORTED_MODE:{mode}")
        expected = tuple(component.name for component in self.components)
        if pair != expected:
            raise ContractViolation("BARD_INCOMPLETE_COMPONENT_PAIR")
        return expected


@dataclass(frozen=True)
class AuthorityRouteContract:
    item_uuid: str
    main: ComponentContract
    skirt: ComponentContract | None


@dataclass(frozen=True)
class AuthorityContract:
    main_component: ComponentContract
    skirt_component: ComponentContract
    routes: tuple[AuthorityRouteContract, ...]
    unresolved_geometry_ids: tuple[str, str, str, str]

    def route_for_item(self, item_uuid: str) -> AuthorityRouteContract:
        for route in self.routes:
            if route.item_uuid == item_uuid:
                return route
        raise ContractViolation(f"AUTHORITY_ITEM_NOT_CONTRACTED:{item_uuid}")

    def require_main_candidate(self, object_ids: Iterable[str]) -> tuple[str, ...]:
        candidate = tuple(object_ids)
        if any("Netherstone" in object_id for object_id in candidate):
            raise ContractViolation("AUTHORITY_NETHERSTONE_SUBSTITUTE_FORBIDDEN")
        if len(candidate) != self.main_component.object_count:
            raise ContractViolation("AUTHORITY_MAIN_OBJECT_COUNT_MISMATCH")
        if candidate != self.main_component.object_ids:
            raise ContractViolation("AUTHORITY_MAIN_OBJECT_CONTRACT_MISMATCH")
        return candidate

    def require_geometry_admitted(self, geometry_ids: Iterable[str]) -> tuple[str, ...]:
        requested = tuple(geometry_ids)
        for geometry_id in requested:
            if geometry_id in self.unresolved_geometry_ids:
                raise ContractViolation(f"AUTHORITY_UNRESOLVED_GEOMETRY:{geometry_id}")
        return requested


_BARD_BASE = ComponentContract(
    name="base",
    visual_resource_uuid="c4e56439-38a8-4b9a-bec2-4c603f7473cc",
    source_file="Generated/Public/BCBScantily/Assets/HUM_F_CLT_Bard_Dress_Base_KEL.GR2",
    sha256="AF11F500DF0CC18F255CDE6D7A96B50961DBEF4C9859B0B44022B0EF108797F7",
    object_ids=(
        "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Blazer_Alt.0",
        "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Boots.1",
        "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Legging.2",
        "TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Sleeves.3",
    ),
    bone_count=82,
)
_BARD_THONG = ComponentContract(
    name="thong",
    visual_resource_uuid="24657ffb-4b65-446e-9884-3098f2440a98",
    source_file="Generated/Public/BCBScantily/Assets/HUM_F_CLT_Bard_Dress_Thong_KEL.GR2",
    sha256="F3CB8A47CF887B28C29F0689A4EAB4152710D5D303E44C73B58271E345BD814D",
    object_ids=("TIF_F_OFT_Bard_Dress.TIF_F_ARM_Bard_Belt_Alt.0",),
    bone_count=82,
)

_AUTHORITY_MAIN = ComponentContract(
    name="authority_main",
    visual_resource_uuid="aec60cfa-c6a1-4a77-8148-b2fa01e4d988",
    source_file="Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe.GR2",
    sha256="03E2EED348D29649E3E222E613592ACD497D49C8EE3B226E84B2072BAF1BC07B",
    object_ids=(
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Gloves.0",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Knee.1",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Robe.2",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Sash.3",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Shawl.4",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Sleeve.5",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Stiletto.6",
        "HUM_F_ARM_Authority_Robe.HUM_F_NKD_Breast.7",
        "HUM_F_ARM_Authority_Robe.HUM_F_ARM_Authority_Skirt.8",
    ),
    bone_count=82,
)
_AUTHORITY_SKIRT = ComponentContract(
    name="authority_skirt",
    visual_resource_uuid="122d5812-e27d-4638-905d-5e520cc26202",
    source_file="Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe_Skirt_KEL.GR2",
    sha256="20B32325E017682E1C2EC17CD858F7EDA15DF596F8EBDAD5EAAA4477BE4242AE",
    object_ids=("HUM_F_ARM_Authority_Robe_Skirt_KEL.HUM_F_ARM_Authority_Skirt.0",),
    bone_count=82,
)


@lru_cache(maxsize=1)
def load_bard_contract() -> BardContract:
    """Return the frozen Bard source, protected-BCB, and failure-evidence contract."""
    return BardContract(
        item_uuid="42092137-4e81-4598-bb18-34939fbb8719",
        components=(_BARD_BASE, _BARD_THONG),
        protected_bcb=ProtectedBCBIdentity(
            component_hashes=(_BARD_BASE.sha256, _BARD_THONG.sha256),
            replacement_routes=0,
        ),
        failure_evidence=(
            ("vanilla", "BodyTop", FailureEvidence(0, 0, 4, 0.20319298429926863)),
            ("vanilla", "Footwear", FailureEvidence(39, 0, 4, 0.1655718748294266)),
            ("vanilla", "Pants", FailureEvidence(1, 0, 1, 0.22793790846010978)),
            ("vanilla", "Sleeves", FailureEvidence(179, 0, 59, 0.03589030264608348)),
            ("vanilla", "Thong", FailureEvidence(181, 0, 20, 0.05640343759001028)),
            ("sbbf", "Sleeves", FailureEvidence(0, 0, 1, 0.159049789992582)),
            ("sbbf", "Thong", FailureEvidence(0, 0, 0, 0.5175596977399949)),
        ),
    )


@lru_cache(maxsize=1)
def load_authority_contract() -> AuthorityContract:
    """Return the frozen BCB Authority route contract and unresolved-ID gate."""
    return AuthorityContract(
        main_component=_AUTHORITY_MAIN,
        skirt_component=_AUTHORITY_SKIRT,
        routes=(
            AuthorityRouteContract("56d78c52-e349-4386-81c0-d8ee8bc8f10e", _AUTHORITY_MAIN, None),
            AuthorityRouteContract("3f869845-badc-4035-ad51-e4ed25f43068", _AUTHORITY_MAIN, _AUTHORITY_SKIRT),
            AuthorityRouteContract("b8c94f92-e857-4725-a59a-5db58bb9a8e6", _AUTHORITY_MAIN, _AUTHORITY_SKIRT),
        ),
        unresolved_geometry_ids=(
            "a913de25-257e-4e42-a677-c663effbe25a",
            "f1f789d3-c09e-485b-8f84-173e41fe9f96",
            "9bebc3db-3e3a-4faf-85fe-f19f589c247d",
            "94e2bcb1-8c38-4687-9833-c761536f0b0a",
        ),
    )
