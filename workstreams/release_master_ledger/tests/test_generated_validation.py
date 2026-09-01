import json

from workstreams.release_master_ledger.configuration import EvidenceInput, LocalConfiguration
from workstreams.release_master_ledger.generate import generate
from workstreams.release_master_ledger.validation import validate_generated_ledger


def test_generated_envelope_requires_numeric_schema_version_and_all_records_valid():
    errors = validate_generated_ledger({
        "schema_version": "1",
        "summary": {"record_count": 2},
        "blockers": [],
        "records": [{}, {}],
    })

    assert "INVALID:schema_version" in errors
    assert any(error.startswith("RECORD[0]:") for error in errors)
    assert any(error.startswith("RECORD[1]:") for error in errors)


def test_schema_contract_uses_numeric_version_one():
    schema = json.loads((__import__("pathlib").Path(__file__).parents[1] / "schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["schema_version"]["const"] == 1


def test_full_synthetic_generated_document_passes_validation(tmp_path):
    evidence = tmp_path / "coverage.json"
    content = b'[{"observation_id":"row-1","root_template_uuid":"root-1","disposition":"BLOCKED WITH CAUSE"}]\n'
    evidence.write_bytes(content)
    digest = __import__("hashlib").sha256(content).hexdigest().upper()
    config = LocalConfiguration(
        inputs=(EvidenceInput("coverage", "COVERAGE", evidence, digest),),
        output_path=tmp_path / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )

    result = generate(config)
    document = json.loads(result.ledger_path.read_text(encoding="utf-8"))

    assert validate_generated_ledger(document) == []
