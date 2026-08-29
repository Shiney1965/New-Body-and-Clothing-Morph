from pathlib import Path

import pytest

from true_underwear.audit_routes import main as audit_main
from true_underwear.audit_routes import write_audit
from true_underwear import generate_ledger
from true_underwear.generate_ledger import main as ledger_main
from true_underwear.generate_ledger import write_ledger


def test_ledger_rejects_outside_config_and_output_without_creating_them(tmp_path):
    outside_config = tmp_path / "source_config.json"
    outside_output = tmp_path / "generated"

    with pytest.raises(ValueError):
        write_ledger(outside_config, outside_output)

    assert not outside_config.exists()
    assert not outside_output.exists()


def test_audit_rejects_outside_config_and_output_without_creating_them(tmp_path):
    outside_config = tmp_path / "source_config.json"
    outside_output = tmp_path / "audit.json"

    with pytest.raises(ValueError):
        write_audit(outside_config, outside_output)

    assert not outside_config.exists()
    assert not outside_output.exists()


def test_ledger_cli_rejects_an_output_override_without_creating_it(tmp_path):
    outside_output = tmp_path / "generated"

    with pytest.raises(SystemExit):
        ledger_main(["--output-dir", str(outside_output)])

    assert not outside_output.exists()


def test_audit_cli_rejects_an_output_override_without_creating_it(tmp_path):
    outside_output = tmp_path / "audit.json"

    with pytest.raises(SystemExit):
        audit_main(["--output", str(outside_output)])

    assert not outside_output.exists()


def test_canonical_rejection_writer_persists_only_its_canonical_filename(tmp_path, monkeypatch):
    canonical_rejection = tmp_path / "local" / "generated" / "TRUE_UNDERWEAR_REJECTIONS.json"
    monkeypatch.setattr(generate_ledger, "CANONICAL_REJECTIONS", canonical_rejection)

    generate_ledger.write_rejections([{"category": "FIXTURE_REJECTION"}])

    assert canonical_rejection.exists()
    assert "FIXTURE_REJECTION" in canonical_rejection.read_text(encoding="utf-8")
