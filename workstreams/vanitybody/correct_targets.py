"""The five new visual-resource identities owned by this correction provider."""

from __future__ import annotations

from dataclasses import dataclass

from .anchors import AnchorContract


TARGET_VISUAL_RESOURCES = {
    ("50bf6831-84ff-42d1-aa18-a97dc3f96a6a", "vanilla"): "ca10d1ad-fb9e-547e-b502-05b78b69a22f",
    ("50bf6831-84ff-42d1-aa18-a97dc3f96a6a", "sbbf"): "c6fe859e-4fc8-5851-b100-3537ac229f13",
    ("50ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25", "vanilla"): "8717bc1f-a404-5289-815f-400cfd37a706",
    ("17ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25", "vanilla"): "ad0484d1-950c-5c94-89c2-eba88d833f95",
    ("82bf6831-84ff-42d1-aa18-a97dc3f96a6a", "vanilla"): "8c1a9d80-4f5e-5d69-b2b9-7de558f70c3b",
}


@dataclass(frozen=True)
class CorrectionTarget:
    garment: str
    root_uuid: str
    mode: str
    target_visual_resource_uuid: str


def correction_targets(anchors: tuple[AnchorContract, ...]) -> tuple[CorrectionTarget, ...]:
    """Bind only the exact approved anchor/mode pairs; fail closed on additions."""
    actual = {(anchor.root_uuid, anchor.mode) for anchor in anchors}
    expected = set(TARGET_VISUAL_RESOURCES)
    if actual != expected:
        raise ValueError(f"anchor set changed: expected {expected}, got {actual}")
    return tuple(
        CorrectionTarget(
            garment=anchor.garment,
            root_uuid=anchor.root_uuid,
            mode=anchor.mode,
            target_visual_resource_uuid=TARGET_VISUAL_RESOURCES[(anchor.root_uuid, anchor.mode)],
        )
        for anchor in anchors
    )
