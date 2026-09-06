"""Assess Robe of Authority geometry under retained safe tooling only.

This module does not admit conditional geometry, invent defect regions, create
landmark/cage solvers, mint GR2/PAK files, mutate protected BCB routes, or attach
terminal exclusion events. It produces an evidence-bound classification for the
Authority Task 4 geometry spike.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from pathlib import Path

from . import authority_contracts as contracts
from .authority_gap_audit import (
    GAP_ROOT,
    LEGACY_ROOT,
    canonical_bytes,
    inspect_glb_semantics,
    sha256_file,
)


WORKSTREAM = Path(__file__).resolve().parent
FINDINGS_PATH = LEGACY_ROOT / "BCBSCANTILY_CLASS_FINDINGS.md"
INVENTORY_PATH = LEGACY_ROOT / "evidence" / "GEOMETRY_INVENTORY.json"
GEOMETRY_DIR = GAP_ROOT / "geometry"

CLASSIFICATION_ADMITTED = "admitted"
CLASSIFICATION_UNFIXABLE = "unfixable"
CLASSIFICATION_UNASSESSABLE = "unassessable"
STATUS_UNASSESSABLE = "GEOMETRY_ASSESSMENT_COMPLETE_UNASSESSABLE"
METHODS = (
    "retained_findings_defect_scan",
    "retained_inventory_defect_scan",
    "gap_audit_geometry_defect_scan",
    "glb_semantic_readback",
    "netherstone_substitute_gate",
    "bcb_slot_vs_physical_mesh_gate",
    "conditional_geometry_module_absence_gate",
)

_DEFECT_CLAIM_RE = re.compile(
    r"defect[\s_-]*(region|coordinate|triangle|face)|face[_\s-]*ratio|sub-?25%|flipped faces",
    re.IGNORECASE,
)
_AUTHORITY_RE = re.compile(r"Authority|Robe_of_Authority|Authority_Robe", re.IGNORECASE)
_NONHUMAN_STEMS = (
    "HFL_F_ARM_Authority_Robe",
    "HFL_F_ARM_Authority_Robe_Alt",
    "TIF_FS_ARM_Authority_Robe",
    "TIF_FS_ARM_Authority_Robe_Alt",
)
_BCB_STEMS = ("bcbscantily_main_gr2", "bcbscantily_skirt_gr2")
_ALL_STEMS = _BCB_STEMS + _NONHUMAN_STEMS + (
    "SCO_HUM_F_ARM_Authority_Robe",
    "SCO_HUM_F_ARM_Authority_Robe_Alt",
    "SBBF_HUM_F_ARM_Authority_Robe",
    "SBBF_HUM_F_ARM_Authority_Robe_Alt",
)


class GeometryAssessmentError(ValueError):
    """Raised when geometry assessment inputs contradict retained safe tooling."""


@dataclass(frozen=True)
class AuthorityGeometryAssessment:
    status: str
    geometry_admitted: bool
    classification: str
    methods_tested: tuple[str, ...]
    defect_region: None
    exclusion_event_input: None
    ready_for_attachment: bool
    release_blocking: bool
    landmark_cage_present: bool
    evidence: tuple[dict[str, object], ...]
    findings: dict[str, object]
    inventory: dict[str, object]
    gap_geometry: dict[str, object]
    glb_readbacks: dict[str, object]
    netherstone_routes: tuple[str, ...]
    slot_mesh_discrepancies: tuple[dict[str, object], ...]
    blockers: tuple[str, ...]


def _pin(path: Path, claim: str) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "claim": claim,
    }


def _require_source_complete(gap_audit: dict[str, object]) -> None:
    if gap_audit.get("status") != "SOURCE_AUDIT_COMPLETE_GEOMETRY_UNASSESSED":
        raise GeometryAssessmentError("AUTHORITY_GEOMETRY_REQUIRES_SOURCE_COMPLETE_AUDIT")
    if gap_audit.get("source_audit_complete") is not True:
        raise GeometryAssessmentError("AUTHORITY_GEOMETRY_REQUIRES_SOURCE_COMPLETE_AUDIT")
    if gap_audit.get("geometry_admitted") is not False:
        raise GeometryAssessmentError("AUTHORITY_GAP_AUDIT_GEOMETRY_FLAG_CORRUPT")
    if gap_audit.get("defect_region") is not None:
        raise GeometryAssessmentError("AUTHORITY_GAP_AUDIT_DEFECT_CORRUPT")
    if gap_audit.get("geometry_methods_tested") != []:
        raise GeometryAssessmentError("AUTHORITY_GAP_AUDIT_METHODS_CORRUPT")
    if gap_audit.get("exclusion_event_input") is not None:
        raise GeometryAssessmentError("AUTHORITY_GAP_AUDIT_EXCLUSION_CORRUPT")


def _scan_findings(text: str, digest: str) -> dict[str, object]:
    authority_lines = []
    defectish_authority_lines = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not _AUTHORITY_RE.search(line):
            continue
        authority_lines.append({"line": number, "text": line})
        if _DEFECT_CLAIM_RE.search(line):
            defectish_authority_lines.append({"line": number, "text": line})
    return {
        "path": str(FINDINGS_PATH),
        "sha256": digest,
        "authority_line_count": len(authority_lines),
        "authority_lines": authority_lines,
        "defect_claim_lines": defectish_authority_lines,
        "source_bound_defect_region_present": False,
        "conclusion": (
            "Authority findings defer the exact nine-object/optional-skirt contract and "
            "supply no source-bound defect-region coordinates or correction candidate."
        ),
    }


def _scan_inventory(payload: dict[str, object], digest: str) -> dict[str, object]:
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        raise GeometryAssessmentError("AUTHORITY_INVENTORY_SHAPE_INVALID")
    authority = {
        path: value
        for path, value in sources.items()
        if isinstance(path, str) and "Authority" in path and isinstance(value, dict)
    }
    expected = {
        "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe.GR2",
        "Generated/Public/BCBScantily/Assets/HUM_F_ARM_Authority_Robe_Skirt_KEL.GR2",
    }
    if set(authority) != expected:
        raise GeometryAssessmentError("AUTHORITY_INVENTORY_SET_UNEXPECTED")
    for path, record in authority.items():
        if record.get("inspection_status") != "COMPLETE":
            raise GeometryAssessmentError("AUTHORITY_INVENTORY_INCOMPLETE")
        if "defect_region" in record and record["defect_region"]:
            raise GeometryAssessmentError("AUTHORITY_INVENTORY_INVENTED_DEFECT")
        if record.get("geometry_admitted") is True:
            raise GeometryAssessmentError("AUTHORITY_INVENTORY_FALSE_ADMISSION")
    return {
        "path": str(INVENTORY_PATH),
        "sha256": digest,
        "authority_source_count": len(authority),
        "authority_sources": {
            path: {
                "sha256": record["sha256"],
                "bytes": record["bytes"],
                "mesh_order": list(record["mesh_order"]),
                "topology": record["topology"],
                "inspection_status": record["inspection_status"],
            }
            for path, record in sorted(authority.items())
        },
        "source_bound_defect_region_present": False,
        "conclusion": (
            "Retained BCB Authority inventory records topology/bones only; no defect "
            "region or fit-failure metric is present."
        ),
    }


def _scan_gap_geometry(geometry: dict[str, object]) -> dict[str, object]:
    if set(geometry) != set(_ALL_STEMS):
        raise GeometryAssessmentError("AUTHORITY_GAP_GEOMETRY_SET_UNEXPECTED")
    summaries = {}
    netherstone = []
    discrepancies = []
    for stem, record in sorted(geometry.items()):
        if record.get("geometry_admitted") is not False or record.get("defect_region") is not None:
            raise GeometryAssessmentError("AUTHORITY_GAP_GEOMETRY_ADMISSION_CORRUPT")
        objects = record["visual_contract"]["objects"]
        object_ids = [entry["object_id"] for entry in objects]
        has_netherstone = any("Netherstone" in object_id for object_id in object_ids)
        if stem in _NONHUMAN_STEMS and not has_netherstone:
            raise GeometryAssessmentError("AUTHORITY_NONHUMAN_NETHERSTONE_MISSING")
        if has_netherstone:
            netherstone.append(stem)
        slots = len(objects)
        meshes = record["gr2"]["mesh_count"]
        if slots != meshes:
            discrepancies.append({
                "stem": stem,
                "visual_slots": slots,
                "physical_mesh_bindings": meshes,
                "meaning": (
                    "Exact source metadata/physical count difference; not a fit defect "
                    "region and not license to invent missing geometry."
                ),
            })
        summaries[stem] = {
            "source_sha256": record["source_sha256"],
            "source_family": record["source_family"],
            "visual_resource_uuid": record["visual_resource_uuid"],
            "visual_object_slot_count": slots,
            "physical_mesh_count": meshes,
            "object_ids": object_ids,
            "has_netherstone": has_netherstone,
            "glb_sha256": record["glb"]["glb_sha256"],
            "geometry_admitted": False,
            "defect_region": None,
        }
    return {
        "records": summaries,
        "netherstone_stems": netherstone,
        "slot_mesh_discrepancies": discrepancies,
        "source_bound_defect_region_present": False,
    }


def _read_glbs(stems: tuple[str, ...]) -> dict[str, object]:
    readbacks = {}
    for stem in stems:
        path = GEOMETRY_DIR / f"{stem}.glb"
        if not path.is_file():
            raise GeometryAssessmentError(f"AUTHORITY_GLB_MISSING:{stem}")
        decoded = inspect_glb_semantics(path)
        if decoded.get("defect_region") is not None:
            raise GeometryAssessmentError("AUTHORITY_GLB_INVENTED_DEFECT")
        if decoded.get("geometry_method_tested") is not False:
            raise GeometryAssessmentError("AUTHORITY_GLB_FALSE_METHOD_FLAG")
        readbacks[stem] = {
            "path": str(path),
            "glb_sha256": decoded["glb_sha256"],
            "glb_bytes": decoded["glb_bytes"],
            "mesh_count": len(decoded["meshes"]),
            "skin_count": len(decoded["skins"]),
            "material_names": [entry.get("name", "") for entry in decoded["materials"]],
            "node_semantics_sha256": decoded["node_semantics_sha256"],
            "defect_region": None,
            "geometry_method_tested": False,
            "readback_scope": decoded["readback_scope"],
        }
    return readbacks


def assess_authority_geometry(
    *,
    gap_audit: dict[str, object] | None = None,
) -> AuthorityGeometryAssessment:
    """Classify Authority geometry admission from retained safe tooling only."""
    if gap_audit is None:
        snapshot = contracts.load_current_authority_snapshot(include_gap_audit=True)
        if snapshot.source_gap_audit is None:
            raise GeometryAssessmentError("AUTHORITY_GAP_AUDIT_MISSING")
        gap_audit = snapshot.source_gap_audit
    _require_source_complete(gap_audit)

    findings_text = FINDINGS_PATH.read_text(encoding="utf-8")
    findings_digest = hashlib.sha256(findings_text.encode("utf-8")).hexdigest().upper()
    findings = _scan_findings(findings_text, findings_digest)
    if findings["defect_claim_lines"]:
        # A textual hit is still not coordinates; fail closed rather than invent regions.
        raise GeometryAssessmentError("AUTHORITY_FINDINGS_DEFECT_TEXT_REQUIRES_MANUAL_BIND")

    inventory_payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    inventory = _scan_inventory(inventory_payload, sha256_file(INVENTORY_PATH))

    gap_geometry = _scan_gap_geometry(gap_audit["geometry"])
    glb_readbacks = _read_glbs(_ALL_STEMS)

    for stem, summary in gap_geometry["records"].items():
        if summary["glb_sha256"] != glb_readbacks[stem]["glb_sha256"]:
            raise GeometryAssessmentError("AUTHORITY_GLB_HASH_MISMATCH")
        if summary["physical_mesh_count"] != glb_readbacks[stem]["mesh_count"]:
            raise GeometryAssessmentError("AUTHORITY_GLB_MESH_COUNT_MISMATCH")

    if not set(_NONHUMAN_STEMS) <= set(gap_geometry["netherstone_stems"]):
        raise GeometryAssessmentError("AUTHORITY_NONHUMAN_NETHERSTONE_SET_UNEXPECTED")
    if any(stem in gap_geometry["netherstone_stems"] for stem in _BCB_STEMS):
        raise GeometryAssessmentError("AUTHORITY_BCB_NETHERSTONE_UNEXPECTED")
    # Raw SCO/SBBF Human overlays also carry Netherstone; they remain non-substitutes.
    if not {"SCO_HUM_F_ARM_Authority_Robe", "SCO_HUM_F_ARM_Authority_Robe_Alt",
            "SBBF_HUM_F_ARM_Authority_Robe", "SBBF_HUM_F_ARM_Authority_Robe_Alt"} <= set(gap_geometry["netherstone_stems"]):
        raise GeometryAssessmentError("AUTHORITY_SCO_SBBF_NETHERSTONE_SET_UNEXPECTED")

    landmark_cage_present = (WORKSTREAM / "authority_landmark_cage.py").exists() or (
        WORKSTREAM / "tests" / "test_authority_landmark_cage.py"
    ).exists()
    if landmark_cage_present:
        raise GeometryAssessmentError("AUTHORITY_LANDMARK_CAGE_FORBIDDEN_BEFORE_ADMISSION")

    evidence = (
        _pin(FINDINGS_PATH, "Complete class findings; Authority deferred without defect coordinates"),
        _pin(INVENTORY_PATH, "Retained BCB Authority topology inventory without defect regions"),
        _pin(
            WORKSTREAM / "local" / "task-4-gap-audit-output-20260902" / "run-1" / "authority-eleven-gap-audit.json",
            "Deterministic eleven-gap source audit packet used as geometry-assessment baseline",
        ),
        *(
            _pin(GEOMETRY_DIR / f"{stem}.glb", f"Read-only GLB semantic readback for {stem}")
            for stem in _ALL_STEMS
        ),
    )

    blockers = (
        "No source-bound defect region exists in retained findings, inventory, gap-audit geometry, or GLB readbacks.",
        "HFL/TIF normal and Alt VisualBank contracts retain Netherstone objects and are forbidden substitutes for the BCB nine-object main.",
        "BCB metadata-slot versus physical-mesh count differences are recorded source facts, not fit defect regions.",
        "Conditional Authority landmark/cage tooling remains absent because geometry was not admitted.",
        "No terminal exclusion event is attached by this assessment; release_blocking remains true.",
    )

    return AuthorityGeometryAssessment(
        status=STATUS_UNASSESSABLE,
        geometry_admitted=False,
        classification=CLASSIFICATION_UNASSESSABLE,
        methods_tested=METHODS,
        defect_region=None,
        exclusion_event_input=None,
        ready_for_attachment=False,
        release_blocking=True,
        landmark_cage_present=False,
        evidence=evidence,
        findings=findings,
        inventory=inventory,
        gap_geometry=gap_geometry,
        glb_readbacks=glb_readbacks,
        netherstone_routes=tuple(sorted(stem for stem in gap_geometry["netherstone_stems"] if stem in _NONHUMAN_STEMS)),
        slot_mesh_discrepancies=tuple(gap_geometry["slot_mesh_discrepancies"]),
        blockers=blockers,
    )


def assessment_payload(assessment: AuthorityGeometryAssessment) -> dict[str, object]:
    payload = asdict(assessment)
    payload.update({
        "schema": "clothmorph.authority-geometry-assessment",
        "schema_version": 1,
        "garment": "Robe of Authority / Authority",
        "author": "SerpentineShel",
        "spike": "Astarion Geometry Spike",
        "scope": (
            "Task 4 Authority geometry assessment under retained safe tooling only; "
            "no Padded/BG Watch, Bard Vanilla/SBBF, Soul Vest/Alt, Alfira, or Spike #2 reopen."
        ),
    })
    return payload


def write_authority_geometry_assessment(output_directory: Path) -> Path:
    """Write a new immutable local proof package; never attaches a terminal exclusion."""
    output_directory = Path(output_directory)
    if output_directory.exists():
        raise FileExistsError("AUTHORITY_GEOMETRY_OUTPUT_DIRECTORY_EXISTS")
    assessment = assess_authority_geometry()
    if assessment.geometry_admitted or assessment.exclusion_event_input is not None:
        raise GeometryAssessmentError("AUTHORITY_GEOMETRY_ASSESSMENT_BOUNDARY_VIOLATION")
    if assessment.classification != CLASSIFICATION_UNASSESSABLE:
        raise GeometryAssessmentError("AUTHORITY_GEOMETRY_UNEXPECTED_CLASSIFICATION")
    output_directory.mkdir(parents=True, exist_ok=False)
    target = output_directory / "authority-geometry-assessment.json"
    with target.open("xb") as stream:
        stream.write(canonical_bytes(assessment_payload(assessment)))
    return target
