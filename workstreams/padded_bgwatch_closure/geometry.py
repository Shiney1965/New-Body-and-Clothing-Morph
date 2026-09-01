"""Byte-only geometry parsing and exact surface contracts for Padded BG Watch."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET

import numpy as np

from .configuration import VerifiedInput


COLLADA_NS = "http://www.collada.org/2005/11/COLLADASchema"
NS = {"c": COLLADA_NS}
TARGET_CLEARANCE_M = 0.001
_GLB_COMPONENT_DTYPES = {
    5121: np.dtype("<u1"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
_GLB_TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _readonly(values: object, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(values, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


def _validate_mesh(positions: object, faces: object) -> tuple[np.ndarray, np.ndarray]:
    checked_positions = _readonly(positions, np.float64)
    checked_faces = _readonly(faces, np.int64)
    if checked_positions.ndim != 2 or checked_positions.shape[1] != 3:
        raise ValueError("positions must have shape (N,3)")
    if checked_faces.ndim != 2 or checked_faces.shape[1] != 3:
        raise ValueError("faces must have shape (M,3)")
    if len(checked_positions) == 0 or len(checked_faces) == 0:
        raise ValueError("triangle mesh must not be empty")
    if np.any(checked_faces < 0) or np.any(checked_faces >= len(checked_positions)):
        raise ValueError("face index is outside the position array")
    if not np.all(np.isfinite(checked_positions)):
        raise ValueError("positions must be finite")
    return checked_positions, checked_faces


@dataclass(frozen=True)
class TriangleMesh:
    """Read-only indexed triangle mesh in one exact coordinate frame."""

    positions: np.ndarray
    faces: np.ndarray

    def __post_init__(self) -> None:
        positions, faces = _validate_mesh(self.positions, self.faces)
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "faces", faces)


@dataclass(frozen=True)
class ParsedColladaGeometry(TriangleMesh):
    """Selected DAE geometry plus immutable source/semantic identities."""

    geometry_id: str
    content_sha256: str
    non_position_sha256: str
    face_indices_sha256: str


@dataclass(frozen=True)
class RoiContract:
    """Connected movable vertices with their fixed exterior one-ring."""

    active_ids: tuple[int, ...]
    movable_ids: tuple[int, ...]
    boundary_ids: tuple[int, ...]
    roi_ids: tuple[int, ...]


@dataclass(frozen=True)
class SurfaceConstraints:
    """Exact closest-triangle targets for the original active vertices."""

    active_ids: tuple[int, ...]
    closest_points: np.ndarray
    surface_normals: np.ndarray
    signed_clearances: np.ndarray
    target_positions: np.ndarray
    face_ids: np.ndarray
    barycentric: np.ndarray
    ambiguous: np.ndarray | None = None
    body_mesh: TriangleMesh | None = None

    def __post_init__(self) -> None:
        count = len(self.active_ids)
        arrays = {
            "closest_points": (_readonly(self.closest_points, np.float64), (count, 3)),
            "surface_normals": (_readonly(self.surface_normals, np.float64), (count, 3)),
            "signed_clearances": (_readonly(self.signed_clearances, np.float64), (count,)),
            "target_positions": (_readonly(self.target_positions, np.float64), (count, 3)),
            "face_ids": (_readonly(self.face_ids, np.int64), (count,)),
            "barycentric": (_readonly(self.barycentric, np.float64), (count, 3)),
        }
        for name, (values, expected_shape) in arrays.items():
            if values.shape != expected_shape:
                raise ValueError(f"{name} must have shape {expected_shape}")
            if values.dtype.kind == "f" and not np.all(np.isfinite(values)):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, values)
        ambiguous = (
            np.zeros(count, dtype=bool)
            if self.ambiguous is None else _readonly(self.ambiguous, bool)
        )
        if ambiguous.shape != (count,):
            raise ValueError(f"ambiguous must have shape {(count,)}")
        ambiguous.setflags(write=False)
        object.__setattr__(self, "ambiguous", ambiguous)
        lengths = np.linalg.norm(self.surface_normals, axis=1)
        if np.any(np.abs(lengths - 1.0) > 1e-9):
            raise ValueError("surface normals must be unit vectors")
        if self.body_mesh is not None and not isinstance(self.body_mesh, TriangleMesh):
            raise TypeError("body_mesh must be a TriangleMesh when retained")


def _position_source(mesh: ET.Element) -> tuple[str, ET.Element, int]:
    vertices = mesh.find("c:vertices", NS)
    if vertices is None:
        raise ValueError("DAE mesh has no vertices element")
    source_id = None
    for input_node in vertices.findall("c:input", NS):
        if input_node.get("semantic") == "POSITION":
            source_id = (input_node.get("source") or "").lstrip("#")
            break
    if not source_id:
        raise ValueError("DAE vertices element has no POSITION input")
    for source in mesh.findall("c:source", NS):
        if source.get("id") != source_id:
            continue
        array = source.find("c:float_array", NS)
        accessor = source.find("c:technique_common/c:accessor", NS)
        if array is None or not array.text:
            raise ValueError("DAE POSITION source has no float array")
        stride = int(accessor.get("stride", "3")) if accessor is not None else 3
        if stride < 3:
            raise ValueError("DAE POSITION stride is smaller than three")
        return source_id, array, stride
    raise ValueError("DAE POSITION source is missing")


def _dae_faces(mesh: ET.Element) -> np.ndarray:
    faces: list[tuple[int, int, int]] = []
    for primitive in mesh.findall("c:triangles", NS):
        inputs = primitive.findall("c:input", NS)
        if not inputs:
            raise ValueError("DAE triangles element has no inputs")
        stride = max(int(node.get("offset", "0")) for node in inputs) + 1
        offsets = [
            int(node.get("offset", "0"))
            for node in inputs
            if node.get("semantic") in {"VERTEX", "POSITION"}
        ]
        if len(offsets) != 1:
            raise ValueError("DAE triangles require exactly one vertex index stream")
        declared = int(primitive.get("count", "0"))
        before = len(faces)
        for index_node in primitive.findall("c:p", NS):
            values = [int(value) for value in (index_node.text or "").split()]
            if len(values) % (stride * 3):
                raise ValueError("DAE triangle stream length is not divisible by stride*3")
            for start in range(0, len(values), stride * 3):
                offset = offsets[0]
                faces.append((
                    values[start + offset],
                    values[start + stride + offset],
                    values[start + 2 * stride + offset],
                ))
        if len(faces) - before != declared:
            raise ValueError("DAE declared triangle count does not match index stream")
    if not faces:
        raise ValueError("DAE mesh has no triangle primitives")
    return np.asarray(faces, dtype=np.int64)


def _non_position_digest(content: bytes, array_id: str) -> str:
    text = content.decode("utf-8")
    pattern = re.compile(
        rf'(<float_array\b[^>]*\bid=["\']{re.escape(array_id)}["\'][^>]*>).*?(</float_array>)',
        re.DOTALL,
    )
    replaced, count = pattern.subn(r"\1__POSITION_VALUES__\2", text, count=1)
    if count != 1:
        raise ValueError("DAE POSITION float array cannot be isolated in verified bytes")
    return hashlib.sha256(replaced.encode("utf-8")).hexdigest().upper()


def parse_collada_geometry(verified: VerifiedInput) -> ParsedColladaGeometry:
    """Parse the largest triangle geometry from verified bytes without reopening a path."""
    if verified.input_id != "pristine_source_dae":
        raise ValueError("COLLADA parser requires pristine_source_dae verified content")
    if len(verified.content) != verified.byte_count:
        raise ValueError("verified DAE byte count mismatch")
    digest = hashlib.sha256(verified.content).hexdigest().upper()
    if digest != verified.actual_sha256 or digest != verified.expected_sha256:
        raise ValueError("verified DAE digest mismatch")
    try:
        root = ET.fromstring(verified.content)
    except ET.ParseError as error:
        raise ValueError("invalid COLLADA XML") from error
    candidates: list[tuple[int, str, np.ndarray, np.ndarray, str]] = []
    for geometry in root.iter(f"{{{COLLADA_NS}}}geometry"):
        mesh = geometry.find("c:mesh", NS)
        if mesh is None:
            continue
        _source_id, array, stride = _position_source(mesh)
        values = np.asarray([float(value) for value in (array.text or "").split()], dtype=np.float64)
        if len(values) % stride:
            raise ValueError("DAE POSITION value count is not divisible by stride")
        positions = values.reshape(-1, stride)[:, :3]
        faces = _dae_faces(mesh)
        geometry_id = geometry.get("id") or geometry.get("name") or ""
        candidates.append((len(positions), geometry_id, positions, faces, array.get("id") or ""))
    if not candidates:
        raise ValueError("DAE contains no indexed triangle geometry")
    _, geometry_id, positions, faces, array_id = max(candidates, key=lambda item: item[0])
    checked_positions, checked_faces = _validate_mesh(positions, faces)
    return ParsedColladaGeometry(
        positions=checked_positions,
        faces=checked_faces,
        geometry_id=geometry_id,
        content_sha256=digest,
        non_position_sha256=_non_position_digest(verified.content, array_id),
        face_indices_sha256=hashlib.sha256(checked_faces.tobytes(order="C")).hexdigest().upper(),
    )


def _read_glb(content: bytes) -> tuple[dict, bytes]:
    if len(content) < 20:
        raise ValueError("GLB content is too short")
    magic, version, total_length = struct.unpack_from("<4sII", content, 0)
    if magic != b"glTF" or version != 2 or total_length != len(content):
        raise ValueError("invalid GLB 2.0 header")
    document = None
    binary = None
    offset = 12
    while offset < len(content):
        if offset + 8 > len(content):
            raise ValueError("truncated GLB chunk header")
        chunk_length, chunk_type = struct.unpack_from("<II", content, offset)
        offset += 8
        payload = content[offset:offset + chunk_length]
        if len(payload) != chunk_length:
            raise ValueError("truncated GLB chunk")
        offset += chunk_length
        if chunk_type == 0x4E4F534A:
            document = json.loads(payload.rstrip(b" \t\r\n\x00").decode("utf-8"))
        elif chunk_type == 0x004E4942:
            binary = payload
    if document is None or binary is None:
        raise ValueError("GLB lacks JSON or BIN content")
    return document, binary


def _glb_accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    if "sparse" in accessor or accessor.get("normalized", False):
        raise ValueError("sparse or normalized GLB accessors are unsupported")
    view = document["bufferViews"][accessor["bufferView"]]
    if int(view.get("buffer", 0)) != 0:
        raise ValueError("only the GLB BIN buffer is supported")
    dtype = _GLB_COMPONENT_DTYPES.get(int(accessor["componentType"]))
    width = _GLB_TYPE_WIDTHS.get(accessor["type"])
    if dtype is None or width is None:
        raise ValueError("unsupported GLB accessor encoding")
    count = int(accessor["count"])
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    packed_stride = dtype.itemsize * width
    stride = int(view.get("byteStride", packed_stride))
    if stride < packed_stride:
        raise ValueError("GLB byte stride is smaller than the accessor element")
    if start < 0 or start + (count - 1) * stride + packed_stride > len(binary):
        raise ValueError("GLB accessor exceeds BIN content")
    if stride == packed_stride:
        return np.frombuffer(binary, dtype=dtype, count=count * width, offset=start).reshape(count, width).copy()
    return np.ndarray(
        shape=(count, width), dtype=dtype, buffer=binary, offset=start,
        strides=(stride, dtype.itemsize),
    ).copy()


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape((4, 4), order="F")
    translation = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64)
    scale = np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float64)
    x, y, z, w = np.asarray(node.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
    matrix = np.array([
        [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w, 0],
        [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w, 0],
        [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y, 0],
        [0, 0, 0, 1],
    ], dtype=np.float64)
    matrix[:3, :3] *= scale[np.newaxis, :]
    matrix[:3, 3] = translation
    return matrix


def _scene_nodes(document: dict) -> list[tuple[int, np.ndarray]]:
    nodes = document.get("nodes", [])
    roots = (
        document["scenes"][int(document.get("scene", 0))].get("nodes", [])
        if "scenes" in document else list(range(len(nodes)))
    )
    found: list[tuple[int, np.ndarray]] = []

    def visit(index: int, parent: np.ndarray) -> None:
        world = parent @ _node_matrix(nodes[index])
        found.append((index, world))
        for child in nodes[index].get("children", []):
            visit(int(child), world)

    for root_index in roots:
        visit(int(root_index), np.eye(4))
    return found


def parse_glb_surface(verified: VerifiedInput) -> TriangleMesh:
    """Parse the largest non-LOD triangle primitive from verified GLB bytes."""
    if verified.input_id != "bcb_body_glb":
        raise ValueError("GLB parser requires bcb_body_glb verified content")
    digest = hashlib.sha256(verified.content).hexdigest().upper()
    if len(verified.content) != verified.byte_count or digest != verified.actual_sha256 or digest != verified.expected_sha256:
        raise ValueError("verified GLB content contract mismatch")
    document, binary = _read_glb(verified.content)
    candidates: list[tuple[bool, int, np.ndarray, np.ndarray]] = []
    for node_index, world in _scene_nodes(document):
        node = document["nodes"][node_index]
        if "mesh" not in node:
            continue
        mesh = document["meshes"][int(node["mesh"])]
        is_lod = "_LOD" in str(mesh.get("name", "")).upper() or "_LOD" in str(node.get("name", "")).upper()
        for primitive in mesh.get("primitives", []):
            if int(primitive.get("mode", 4)) != 4:
                raise ValueError("GLB surface contains a non-triangle primitive")
            attributes = primitive.get("attributes", {})
            if "POSITION" not in attributes or "indices" not in primitive:
                raise ValueError("GLB triangle primitive lacks positions or indices")
            local = _glb_accessor(document, binary, int(attributes["POSITION"])).astype(np.float64)
            raw_faces = _glb_accessor(document, binary, int(primitive["indices"])).reshape(-1)
            if local.shape[1] != 3 or len(raw_faces) % 3:
                raise ValueError("GLB triangle primitive has invalid dimensions")
            homogeneous = np.column_stack([local, np.ones(len(local))])
            positions = (world @ homogeneous.T).T[:, :3]
            faces = raw_faces.astype(np.int64).reshape(-1, 3)
            candidates.append((is_lod, len(positions), positions, faces))
    if not candidates:
        raise ValueError("GLB contains no indexed triangle primitive")
    non_lod = [item for item in candidates if not item[0]]
    _, _, positions, faces = max(non_lod or candidates, key=lambda item: item[1])
    return TriangleMesh(positions, faces)


def _adjacency(vertex_count: int, faces: np.ndarray) -> tuple[tuple[int, ...], ...]:
    neighbors = [set() for _ in range(vertex_count)]
    for a, b, c in faces:
        a, b, c = int(a), int(b), int(c)
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))
    return tuple(tuple(sorted(values)) for values in neighbors)


def derive_minimal_roi(
    base_positions: object,
    faces: object,
    active_ids: object,
) -> RoiContract:
    """Connect active vertices by deterministic shortest paths and fix their one-ring."""
    positions, checked_faces = _validate_mesh(base_positions, faces)
    active = tuple(sorted({int(value) for value in active_ids}))
    if not active or active[0] < 0 or active[-1] >= len(positions):
        raise ValueError("active vertex IDs must be a nonempty in-range set")
    adjacency = _adjacency(len(positions), checked_faces)
    connected = {active[0]}
    for target in active[1:]:
        if target in connected:
            continue
        queue: deque[int] = deque(sorted(connected))
        parents: dict[int, int | None] = {value: None for value in connected}
        while queue and target not in parents:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in parents:
                    parents[neighbor] = current
                    queue.append(neighbor)
        if target not in parents:
            raise ValueError("active vertices are not in one connected mesh component")
        cursor: int | None = target
        while cursor is not None and cursor not in connected:
            connected.add(cursor)
            cursor = parents[cursor]
    movable = tuple(sorted(connected))
    boundary = tuple(sorted({
        neighbor
        for vertex_id in movable
        for neighbor in adjacency[vertex_id]
        if neighbor not in connected
    }))
    return RoiContract(
        active_ids=active,
        movable_ids=movable,
        boundary_ids=boundary,
        roi_ids=tuple(sorted((*movable, *boundary))),
    )


def _closest_points(points: np.ndarray, mesh: TriangleMesh) -> tuple[np.ndarray, ...]:
    triangles = mesh.positions[mesh.faces]
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    face_vectors = np.cross(ab, ac)
    face_lengths = np.linalg.norm(face_vectors, axis=1)
    valid_faces = face_lengths > 1e-15
    if not np.any(valid_faces):
        raise ValueError("body surface has no nondegenerate triangle")
    closest = np.empty_like(points)
    normals = np.empty_like(points)
    face_ids = np.empty(len(points), dtype=np.int64)
    barycentric = np.empty_like(points)
    distances = np.empty(len(points), dtype=np.float64)
    ambiguous = np.empty(len(points), dtype=bool)
    for point_index, point in enumerate(points):
        ap = point - a
        d1 = np.einsum("ij,ij->i", ab, ap)
        d2 = np.einsum("ij,ij->i", ac, ap)
        candidates = np.empty_like(a)
        bary = np.empty_like(a)
        chosen = np.zeros(len(triangles), dtype=bool)

        mask = (d1 <= 0.0) & (d2 <= 0.0)
        candidates[mask], bary[mask] = a[mask], [1.0, 0.0, 0.0]
        chosen |= mask

        bp = point - b
        d3 = np.einsum("ij,ij->i", ab, bp)
        d4 = np.einsum("ij,ij->i", ac, bp)
        mask = ~chosen & (d3 >= 0.0) & (d4 <= d3)
        candidates[mask], bary[mask] = b[mask], [0.0, 1.0, 0.0]
        chosen |= mask

        vc = d1 * d4 - d3 * d2
        mask = ~chosen & (vc <= 0.0) & (d1 >= 0.0) & (d3 <= 0.0)
        v = np.divide(d1, d1 - d3, out=np.zeros_like(d1), where=d1 != d3)
        candidates[mask] = a[mask] + v[mask, None] * ab[mask]
        bary[mask] = np.column_stack([1.0 - v[mask], v[mask], np.zeros(np.count_nonzero(mask))])
        chosen |= mask

        cp = point - c
        d5 = np.einsum("ij,ij->i", ab, cp)
        d6 = np.einsum("ij,ij->i", ac, cp)
        mask = ~chosen & (d6 >= 0.0) & (d5 <= d6)
        candidates[mask], bary[mask] = c[mask], [0.0, 0.0, 1.0]
        chosen |= mask

        vb = d5 * d2 - d1 * d6
        mask = ~chosen & (vb <= 0.0) & (d2 >= 0.0) & (d6 <= 0.0)
        w = np.divide(d2, d2 - d6, out=np.zeros_like(d2), where=d2 != d6)
        candidates[mask] = a[mask] + w[mask, None] * ac[mask]
        bary[mask] = np.column_stack([1.0 - w[mask], np.zeros(np.count_nonzero(mask)), w[mask]])
        chosen |= mask

        va = d3 * d6 - d5 * d4
        edge_denominator = (d4 - d3) + (d5 - d6)
        mask = ~chosen & (va <= 0.0) & ((d4 - d3) >= 0.0) & ((d5 - d6) >= 0.0)
        w = np.divide(
            d4 - d3, edge_denominator,
            out=np.zeros_like(d4), where=edge_denominator != 0.0,
        )
        candidates[mask] = b[mask] + w[mask, None] * (c[mask] - b[mask])
        bary[mask] = np.column_stack([np.zeros(np.count_nonzero(mask)), 1.0 - w[mask], w[mask]])
        chosen |= mask

        mask = ~chosen
        denominator = va + vb + vc
        v = np.divide(vb, denominator, out=np.zeros_like(vb), where=denominator != 0.0)
        w = np.divide(vc, denominator, out=np.zeros_like(vc), where=denominator != 0.0)
        candidates[mask] = a[mask] + v[mask, None] * ab[mask] + w[mask, None] * ac[mask]
        bary[mask] = np.column_stack([1.0 - v[mask] - w[mask], v[mask], w[mask]])

        squared = np.einsum("ij,ij->i", candidates - point, candidates - point)
        squared[~valid_faces] = np.inf
        nearest = int(np.argmin(squared))
        if not np.isfinite(squared[nearest]):
            raise ValueError("body surface has no valid closest triangle")
        closest[point_index] = candidates[nearest]
        normals[point_index] = face_vectors[nearest] / face_lengths[nearest]
        face_ids[point_index] = nearest
        barycentric[point_index] = bary[nearest]
        distances[point_index] = squared[nearest]
        finite = squared[np.isfinite(squared)]
        if len(finite) < 2:
            ambiguous[point_index] = False
        else:
            first, second = np.partition(finite, 1)[:2]
            ambiguous[point_index] = (np.sqrt(second) - np.sqrt(first)) <= 1e-9
    return closest, normals, face_ids, barycentric, np.sqrt(distances), ambiguous


def build_surface_constraints(
    base_positions: object,
    body_mesh: TriangleMesh,
    active_ids: object,
) -> SurfaceConstraints:
    """Build exact closest-triangle +1 mm surface constraints for active vertices."""
    base = np.asarray(base_positions, dtype=np.float64)
    if base.ndim != 2 or base.shape[1] != 3 or not np.all(np.isfinite(base)):
        raise ValueError("base positions must have shape (N,3) and be finite")
    active = tuple(int(value) for value in active_ids)
    if not active or len(set(active)) != len(active) or min(active) < 0 or max(active) >= len(base):
        raise ValueError("active IDs must be unique, nonempty, and in range")
    if not isinstance(body_mesh, TriangleMesh):
        raise TypeError("body_mesh must be a TriangleMesh")
    points = base[np.asarray(active, dtype=np.int64)]
    closest, normals, face_ids, barycentric, _distances, ambiguous = _closest_points(points, body_mesh)
    signed = np.einsum("ij,ij->i", points - closest, normals)
    targets = closest + TARGET_CLEARANCE_M * normals
    return SurfaceConstraints(
        active, closest, normals, signed, targets, face_ids, barycentric, ambiguous,
        body_mesh=body_mesh,
    )
