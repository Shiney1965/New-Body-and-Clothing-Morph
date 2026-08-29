"""Binding contracts for the explicitly approved VanityBody correction modes."""

from __future__ import annotations

from dataclasses import dataclass


WEDDING_ROOT = "50bf6831-84ff-42d1-aa18-a97dc3f96a6a"
SATIN_ROOT = "50ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25"
SERIOUS_BUSINESS_ROOT = "17ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25"
SEXY_CATSUIT_ROOT = "82bf6831-84ff-42d1-aa18-a97dc3f96a6a"


@dataclass(frozen=True)
class AnchorContract:
    garment: str
    root_uuid: str
    mode: str
    protected_modes: tuple[str, ...]
    defect_region: dict[str, float]


def load_anchor_contracts() -> tuple[AnchorContract, ...]:
    """Return the public, narrow anchor boundary without reading private evidence."""
    region = {"x_abs_max": 0.2, "y_min": 0.6, "y_max": 1.2, "z_min": -0.2, "z_max": 0.2}
    return (
        AnchorContract("Wedding Body Suit", WEDDING_ROOT, "vanilla", ("bcb",), region),
        AnchorContract("Wedding Body Suit", WEDDING_ROOT, "sbbf", ("bcb",), region),
        AnchorContract("Satin Thong", SATIN_ROOT, "vanilla", ("sbbf", "bcb"), region),
        AnchorContract("Serious Business Lady", SERIOUS_BUSINESS_ROOT, "vanilla", ("sbbf", "bcb"), region),
        AnchorContract("Sexy Catsuit", SEXY_CATSUIT_ROOT, "vanilla", ("sbbf", "bcb"), region),
    )
