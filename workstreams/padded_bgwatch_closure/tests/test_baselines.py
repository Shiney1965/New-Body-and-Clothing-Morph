"""Public contract tests for the Padded BG Watch position-only closure."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from workstreams.padded_bgwatch_closure.configuration import (
    ConfigurationError,
    EvidenceIntegrityError,
    generated_output_path,
    load_local_configuration,
    verify_input_hashes,
)
from workstreams.padded_bgwatch_closure.models import BASELINES


def _write_local_config(root: Path, pristine_path: str, body_path: str) -> None:
    local_root = root / "local"
    local_root.mkdir(parents=True)
    (local_root / "config.json").write_text(
        json.dumps({
            "pristine_source_dae": pristine_path,
            "bcb_body_glb": body_path,
        }),
        encoding="utf-8",
    )


def test_baselines_pin_the_exact_geometry_identities_and_historical_metrics():
    """Catches accidental drift in an identity or fixed evidence metric."""
    assert BASELINES.pristine_source_dae.sha256 == (
        "DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262"
    )
    assert BASELINES.bcb_body_glb.sha256 == (
        "51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C"
    )
    assert BASELINES.pristine_source_dae.vertex_count == 8_033
    assert BASELINES.pristine_source_dae.face_count == 14_943
    assert BASELINES.local_repair.confident_penetrations == 421
    assert BASELINES.local_repair.confident_deep_penetrations == 411
    assert BASELINES.local_repair.fixed_cohort_coverage_loss == 40
    assert BASELINES.local_repair.topology_safe is True
    assert BASELINES.historical_post_clip.flipped_faces == 115
    assert BASELINES.historical_post_clip.sub_half_area_faces == 1_574
    assert BASELINES.historical_post_clip.fixed_cohort_coverage_loss == 31

    with pytest.raises(dataclasses.FrozenInstanceError):
        BASELINES.local_repair.confident_penetrations = 0  # type: ignore[misc]


def test_canonical_config_binds_only_the_hash_pinned_dae_and_glb_inputs(tmp_path: Path):
    """Catches a configuration path being given a caller-controlled identity."""
    pristine = tmp_path / "inputs" / "covering.dae"
    body = tmp_path / "inputs" / "body.glb"
    pristine.parent.mkdir()
    pristine.write_bytes(b"placeholder dae bytes")
    body.write_bytes(b"placeholder glb bytes")
    _write_local_config(tmp_path, "../inputs/covering.dae", "../inputs/body.glb")

    config = load_local_configuration(tmp_path)

    assert config.pristine_source_dae.path == pristine.resolve()
    assert config.pristine_source_dae.expected_sha256 == BASELINES.pristine_source_dae.sha256
    assert config.bcb_body_glb.path == body.resolve()
    assert config.bcb_body_glb.expected_sha256 == BASELINES.bcb_body_glb.sha256


def test_hash_mismatch_is_rejected_before_any_input_is_released_for_parsing(tmp_path: Path):
    """Catches an adapter receiving bytes whose required identity was not verified."""
    pristine = tmp_path / "inputs" / "covering.dae"
    body = tmp_path / "inputs" / "body.glb"
    pristine.parent.mkdir()
    pristine.write_bytes(b"not the pinned pristine DAE")
    body.write_bytes(b"not the pinned BCB GLB")
    _write_local_config(tmp_path, "../inputs/covering.dae", "../inputs/body.glb")

    with pytest.raises(EvidenceIntegrityError, match="EVIDENCE_HASH_MISMATCH:pristine_source_dae"):
        verify_input_hashes(load_local_configuration(tmp_path))


def test_generated_output_paths_are_confined_to_local_generated(tmp_path: Path):
    """Catches a future writer escaping the ignored local/generated boundary."""
    assert generated_output_path(tmp_path, "reports/position_only_search.json") == (
        tmp_path / "local" / "generated" / "reports" / "position_only_search.json"
    )

    with pytest.raises(ConfigurationError, match="OUTPUT_OUTSIDE_LOCAL_GENERATED"):
        generated_output_path(tmp_path, "../position_only_search.json")
    with pytest.raises(ConfigurationError, match="OUTPUT_OUTSIDE_LOCAL_GENERATED"):
        generated_output_path(tmp_path, tmp_path / "outside.json")


@pytest.mark.parametrize("field_name, unsafe_path", [
    ("pristine_source_dae", "../inputs/covering.gr2"),
    ("bcb_body_glb", "../inputs/body.pak"),
])
def test_configuration_refuses_non_dae_or_glb_inputs(
    tmp_path: Path,
    field_name: str,
    unsafe_path: str,
):
    """Catches a GR2/PAK path entering this DAE/GLB-only offline boundary."""
    values = {
        "pristine_source_dae": "../inputs/covering.dae",
        "bcb_body_glb": "../inputs/body.glb",
    }
    values[field_name] = unsafe_path
    _write_local_config(tmp_path, values["pristine_source_dae"], values["bcb_body_glb"])

    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID_INPUT_SUFFIX"):
        load_local_configuration(tmp_path)
