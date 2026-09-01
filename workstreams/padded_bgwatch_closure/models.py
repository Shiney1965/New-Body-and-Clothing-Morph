"""Immutable public evidence records for the Padded BG Watch closure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeometryIdentity:
    """Exact identity and LOD0 shape contract for an offline geometry input."""

    sha256: str
    vertex_count: int | None = None
    face_count: int | None = None


@dataclass(frozen=True)
class LocalRepairBaseline:
    """Fixed outcome metrics for the retained topology-safe local repair."""

    confident_penetrations: int
    confident_deep_penetrations: int
    fixed_cohort_coverage_loss: int
    topology_safe: bool


@dataclass(frozen=True)
class HistoricalPostClipBaseline:
    """Fixed topology and coverage metrics for the historical post-clip output."""

    flipped_faces: int
    sub_half_area_faces: int
    fixed_cohort_coverage_loss: int


@dataclass(frozen=True)
class PaddedBgWatchBaselines:
    """All evidence pins that later offline work must preserve or compare."""

    pristine_source_dae: GeometryIdentity
    bcb_body_glb: GeometryIdentity
    local_repair: LocalRepairBaseline
    historical_post_clip: HistoricalPostClipBaseline


BASELINES = PaddedBgWatchBaselines(
    pristine_source_dae=GeometryIdentity(
        sha256="DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262",
        vertex_count=8_033,
        face_count=14_943,
    ),
    bcb_body_glb=GeometryIdentity(
        sha256="51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C",
    ),
    local_repair=LocalRepairBaseline(
        confident_penetrations=421,
        confident_deep_penetrations=411,
        fixed_cohort_coverage_loss=40,
        topology_safe=True,
    ),
    historical_post_clip=HistoricalPostClipBaseline(
        flipped_faces=115,
        sub_half_area_faces=1_574,
        fixed_cohort_coverage_loss=31,
    ),
)
