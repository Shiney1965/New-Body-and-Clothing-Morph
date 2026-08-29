import json
from pathlib import Path

import pytest

from workstreams.coverage_ledger import build_ledger, generate_test_cards
from workstreams.coverage_ledger import configuration
from workstreams.coverage_ledger.configuration import (
    LOCAL_CONFIG_ENV,
    LocalConfiguration,
    LocalConfigurationUnavailable,
    load_local_configuration,
)


def test_no_environment_configuration_skips_local_generation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(LOCAL_CONFIG_ENV, raising=False)
    with pytest.raises(LocalConfigurationUnavailable, match="local generation skipped"):
        load_local_configuration()


def test_generation_entry_points_require_an_explicit_local_configuration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(LOCAL_CONFIG_ENV, raising=False)
    with pytest.raises(LocalConfigurationUnavailable, match="local generation skipped"):
        build_ledger.main()
    with pytest.raises(LocalConfigurationUnavailable, match="local generation skipped"):
        generate_test_cards.main()


def test_explicit_configuration_uses_paths_relative_to_its_own_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_dir = tmp_path / "outputs"
    local_dir.mkdir()
    config = local_dir / "local_configuration.json"
    config.write_text(json.dumps({
        "source_registry_path": "../inputs/registry.json",
        "prior_sources_path": "../inputs/prior.json",
        "evidence_dir": "evidence",
        "card_dir": "cards",
    }), encoding="utf-8")

    monkeypatch.setattr(configuration, "LOCAL_OUTPUT_ROOT", local_dir)
    monkeypatch.setattr(configuration, "CANONICAL_LOCAL_CONFIGURATION_PATH", config)
    loaded = load_local_configuration(config)

    assert loaded.source_registry_path.resolve() == tmp_path / "inputs/registry.json"
    assert loaded.prior_sources_path.resolve() == tmp_path / "inputs/prior.json"
    assert loaded.evidence_dir == local_dir / "evidence"
    assert loaded.card_dir == local_dir / "cards"


def test_absolute_or_escape_generated_output_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    config = local_dir / "local_configuration.json"
    config.write_text(json.dumps({
        "source_registry_path": "../inputs/registry.json",
        "prior_sources_path": "../inputs/prior.json",
        "evidence_dir": "../evidence",
        "card_dir": str(tmp_path / "outside" / "cards"),
    }), encoding="utf-8")

    monkeypatch.setattr(configuration, "LOCAL_OUTPUT_ROOT", local_dir)
    monkeypatch.setattr(configuration, "CANONICAL_LOCAL_CONFIGURATION_PATH", config)
    with pytest.raises(LocalConfigurationUnavailable, match="generated output.*local"):
        load_local_configuration(config)


def test_generated_outputs_inside_local_directory_are_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    config = local_dir / "local_configuration.json"
    config.write_text(json.dumps({
        "source_registry_path": "../inputs/registry.json",
        "prior_sources_path": "../inputs/prior.json",
        "evidence_dir": "evidence",
        "card_dir": "test_cards",
    }), encoding="utf-8")

    monkeypatch.setattr(configuration, "LOCAL_OUTPUT_ROOT", local_dir)
    monkeypatch.setattr(configuration, "CANONICAL_LOCAL_CONFIGURATION_PATH", config)
    loaded = load_local_configuration(config)

    assert loaded.evidence_dir == local_dir / "evidence"
    assert loaded.card_dir == local_dir / "test_cards"


def test_alternate_configuration_path_is_rejected_before_read(tmp_path: Path):
    alternate = tmp_path / "alternate.json"
    alternate.write_text("{}", encoding="utf-8")

    with pytest.raises(LocalConfigurationUnavailable, match="canonical local configuration"):
        load_local_configuration(alternate)


def test_build_entry_point_rejects_direct_unsafe_configuration_before_writes(tmp_path: Path):
    unsafe = LocalConfiguration(
        source_registry_path=tmp_path / "registry.json",
        prior_sources_path=tmp_path / "prior.json",
        evidence_dir=tmp_path / "outside-evidence",
        card_dir=tmp_path / "outside-cards",
    )

    with pytest.raises(LocalConfigurationUnavailable, match="generated output.*local"):
        build_ledger.main(unsafe)

    assert not unsafe.evidence_dir.exists()
    assert not unsafe.card_dir.exists()


def test_card_entry_point_rejects_direct_unsafe_configuration_before_writes(tmp_path: Path):
    unsafe = LocalConfiguration(
        source_registry_path=tmp_path / "registry.json",
        prior_sources_path=tmp_path / "prior.json",
        evidence_dir=tmp_path / "outside-evidence",
        card_dir=tmp_path / "outside-cards",
    )

    with pytest.raises(LocalConfigurationUnavailable, match="generated output.*local"):
        generate_test_cards.main(unsafe)

    assert not unsafe.evidence_dir.exists()
    assert not unsafe.card_dir.exists()
