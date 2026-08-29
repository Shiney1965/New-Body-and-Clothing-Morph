"""Accessor-aware real-GLB structure evidence; never writes a mesh."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GlbProfile:
    components: tuple[tuple[str, int, int], ...]
    file_sha256: str
    position_sha256: str


@dataclass(frozen=True)
class BoundaryFinding:
    status: str
    reason: str


def inspect_glb(path: Path) -> GlbProfile:
    """Inspect a caller-provided local GLB; does not discover staging inputs."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise ValueError(f"not a GLB: {path}")
    json_length = struct.unpack("<I", raw[12:16])[0]
    document = json.loads(raw[20 : 20 + json_length])
    bin_start = 20 + json_length + 8
    components: list[tuple[str, int, int]] = []
    position_stream = bytearray()
    for mesh in document["meshes"]:
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            position_accessor = primitive.get("attributes", {}).get("POSITION")
            if position_accessor is None:
                continue
            accessor = document["accessors"][position_accessor]
            view = document["bufferViews"][accessor["bufferView"]]
            stride = view.get("byteStride", 12)
            start = bin_start + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            count = accessor["count"]
            components.append((mesh.get("name", ""), count, primitive_index))
            for index in range(count):
                position_stream.extend(raw[start + index * stride : start + index * stride + 12])
    return GlbProfile(
        components=tuple(components),
        file_sha256=hashlib.sha256(raw).hexdigest().upper(),
        position_sha256=hashlib.sha256(position_stream).hexdigest().upper(),
    )


def wedding_boundary(profile: GlbProfile) -> BoundaryFinding:
    if profile.components == (("HUM_F_NKD_Body_A_Mesh", 7996, 0),):
        return BoundaryFinding(
            status="UNPROVEN_EMBEDDED_BODY",
            reason="single exported component is explicitly named as a naked body mesh",
        )
    return BoundaryFinding(status="UNASSESSED", reason="manual component-contract review required")
