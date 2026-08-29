from pathlib import Path

import pytest

from workstreams.vanitybody.local_integration import (
    LocalIntegrationUnavailable,
    local_output_directory,
    load_local_integration,
)


def test_missing_local_configuration_fails_closed_without_reading_evidence():
    """Catches a future fallback that reads ignored evidence in portable runs."""
    with pytest.raises(LocalIntegrationUnavailable, match="local integration is not configured"):
        load_local_integration()


def test_external_configuration_path_is_rejected_before_it_is_read(tmp_path):
    """Catches a public API regression that accepts an alternate config location."""
    external = tmp_path / "config.json"
    external.write_text("not json", encoding="utf-8")
    with pytest.raises(LocalIntegrationUnavailable, match="canonical local/config.json"):
        load_local_integration(external)


def test_canonical_configuration_path_is_accepted_before_local_input_validation(tmp_path, monkeypatch):
    """Catches a fail-closed check that accidentally rejects the sole valid path."""
    canonical = tmp_path / "local" / "config.json"
    canonical.parent.mkdir()
    inputs = {}
    for name in ("anchor_evidence", "route_evidence", "glb_manifest", "ledger_input"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}", encoding="utf-8")
        inputs[name] = str(path)
    canonical.write_text(__import__("json").dumps(inputs), encoding="utf-8")
    monkeypatch.setattr("workstreams.vanitybody.local_integration.DEFAULT_CONFIG", canonical)
    assert load_local_integration(canonical).anchor_evidence == (tmp_path / "anchor_evidence.json")


def test_example_configuration_cannot_escape_the_local_output_boundary(tmp_path, monkeypatch):
    """Catches a future config that lets generated output write outside local/."""
    config = tmp_path / "config.json"
    config.write_text('{"output_dir": "../outside"}', encoding="utf-8")
    monkeypatch.setattr("workstreams.vanitybody.local_integration.DEFAULT_CONFIG", config)
    with pytest.raises(LocalIntegrationUnavailable, match="output_dir"):
        load_local_integration(config)


def test_public_writer_boundary_rejects_an_arbitrary_output_directory(tmp_path):
    """Catches a writer API regression that could publish generated results elsewhere."""
    with pytest.raises(LocalIntegrationUnavailable, match="output_dir"):
        local_output_directory(tmp_path)
