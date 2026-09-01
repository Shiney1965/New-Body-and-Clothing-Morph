import hashlib
import json
from pathlib import Path

import pytest

from workstreams.release_master_ledger import configuration
from workstreams.release_master_ledger.configuration import (
    ConfigurationError,
    EvidenceInput,
    EvidenceIntegrityError,
    LocalConfiguration,
    load_local_configuration,
    validate_output_path,
    verify_evidence_inputs,
)


def configuration_fixture(evidence: Path, expected_sha256: str) -> LocalConfiguration:
    return LocalConfiguration(
        inputs=(
            EvidenceInput(
                input_id="synthetic_evidence",
                kind="SYNTHETIC",
                path=evidence,
                expected_sha256=expected_sha256,
            ),
        ),
        output_path=Path(__file__).resolve().parents[1] / "local" / "generated" / "ledger.json",
    )


def test_canonical_local_config_loads_hash_locked_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workstream_root = tmp_path / "release_master_ledger"
    local_root = workstream_root / "local"
    evidence = local_root / "evidence.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"fixture":"minimal"}', encoding="utf-8")
    expected_sha256 = hashlib.sha256(evidence.read_bytes()).hexdigest().upper()
    config_path = local_root / "config.json"
    config_path.write_text(json.dumps({
        "inputs": [{
            "input_id": "synthetic_evidence",
            "kind": "SYNTHETIC",
            "path": "evidence.json",
            "expected_sha256": expected_sha256,
        }],
        "output_path": "generated/ledger.json",
        "exclusion_events_dir": "exclusion_events",
    }), encoding="utf-8")
    monkeypatch.setattr(configuration, "WORKSTREAM_ROOT", workstream_root)

    config = load_local_configuration()

    assert config.inputs[0].path == evidence
    assert config.output_path == local_root / "generated" / "ledger.json"
    assert config.exclusion_events_dir == local_root / "exclusion_events"


def test_hash_mismatch_fails_before_adapter_reads_json(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("not json", encoding="utf-8")
    config = configuration_fixture(evidence, expected_sha256="0" * 64)

    with pytest.raises(EvidenceIntegrityError, match="EVIDENCE_HASH_MISMATCH"):
        verify_evidence_inputs(config)


def test_missing_registered_input_is_rejected(tmp_path: Path):
    missing = tmp_path / "missing.json"
    config = configuration_fixture(missing, expected_sha256="0" * 64)

    with pytest.raises(EvidenceIntegrityError, match="EVIDENCE_INPUT_MISSING"):
        verify_evidence_inputs(config)


def test_generated_output_cannot_escape_local_generated(workstream_root: Path):
    with pytest.raises(ConfigurationError, match="OUTPUT_OUTSIDE_LOCAL_GENERATED"):
        validate_output_path(workstream_root.parent / "escaped.json", workstream_root)


def test_verified_input_records_hash_and_byte_count(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b'{"fixture":"minimal"}')
    expected_sha256 = hashlib.sha256(evidence.read_bytes()).hexdigest().upper()
    config = configuration_fixture(evidence, expected_sha256=expected_sha256)

    verified = verify_evidence_inputs(config)

    assert verified[0].input_id == "synthetic_evidence"
    assert verified[0].kind == "SYNTHETIC"
    assert verified[0].path == evidence
    assert verified[0].bytes == evidence.stat().st_size
    assert verified[0].expected_sha256 == expected_sha256
    assert verified[0].actual_sha256 == expected_sha256


@pytest.fixture
def workstream_root() -> Path:
    return Path(__file__).resolve().parents[1]
