import hashlib
import json
from pathlib import Path
import time

from workstreams.release_master_ledger.configuration import EvidenceInput, LocalConfiguration, VerifiedInput
from workstreams.release_master_ledger.generate import _stable_evidence_references, generate


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest().upper()


def synthetic_config(root: Path, *, record_count: int = 1) -> LocalConfiguration:
    evidence = root / "evidence" / "coverage.json"
    records = [
        {
            "observation_id": f"synthetic-{index}",
            "disposition": "BLOCKED WITH CAUSE",
            "root_template_uuid": f"root-{index}",
        }
        for index in range(record_count)
    ]
    digest = _write_json(evidence, {"records": records})
    return LocalConfiguration(
        inputs=(EvidenceInput("synthetic_coverage", "COVERAGE", evidence, digest),),
        output_path=root / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )


def test_generation_is_byte_deterministic_across_output_roots(tmp_path):
    first = generate(synthetic_config(tmp_path / "first"))
    second = generate(synthetic_config(tmp_path / "second"))

    assert first.ledger_sha256 == second.ledger_sha256
    assert first.audit_sha256 == second.audit_sha256
    assert first.markdown_sha256 == second.markdown_sha256


def test_summary_is_recomputed_from_records(tmp_path):
    result = generate(synthetic_config(tmp_path, record_count=2))
    payload = json.loads(result.ledger_path.read_text(encoding="utf-8"))

    assert payload["summary"]["record_count"] == len(payload["records"]) == 2
    assert payload["summary"]["observation_count"] == 2
    assert "**Ledger records:** 2" in result.markdown_path.read_text(encoding="utf-8")


def test_json_outputs_use_canonical_pretty_encoding_and_one_trailing_newline(tmp_path):
    result = generate(synthetic_config(tmp_path))

    for path in (result.ledger_path, result.audit_path, result.manifest_path):
        content = path.read_bytes()
        assert content.endswith(b"\n")
        assert not content.endswith(b"\n\n")
        payload = json.loads(content.decode("utf-8"))
        assert content == (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def test_manifest_pins_each_verified_input_identity(tmp_path):
    config = synthetic_config(tmp_path)

    result = generate(config)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["inputs"] == [
        {
            "actual_sha256": config.inputs[0].expected_sha256,
            "bytes": config.inputs[0].path.stat().st_size,
            "expected_sha256": config.inputs[0].expected_sha256,
            "input_id": "synthetic_coverage",
            "kind": "COVERAGE",
            "path": str(config.inputs[0].path.resolve()),
        }
    ]


def test_hash_verification_does_not_infer_source_profile_completeness(tmp_path):
    result = generate(synthetic_config(tmp_path))

    audit = json.loads(result.audit_path.read_text(encoding="utf-8"))
    assert audit["required_source_profiles_complete"] is False
    assert audit["source_complete"] is False


def test_generation_namespaces_same_observation_id_from_distinct_inputs(tmp_path):
    inputs = []
    for input_id, root_uuid in (("first_source", "root-a"), ("second_source", "root-b")):
        evidence = tmp_path / "evidence" / f"{input_id}.json"
        digest = _write_json(evidence, {"records": [{
            "observation_id": "shared-item-id",
            "root_template_uuid": root_uuid,
            "disposition": "BLOCKED WITH CAUSE",
        }]})
        inputs.append(EvidenceInput(input_id, "COVERAGE", evidence, digest))
    config = LocalConfiguration(
        inputs=tuple(inputs),
        output_path=tmp_path / "generated" / "REMAINING_TARGET_MASTER_LEDGER.json",
    )

    result = generate(config)

    payload = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    assert payload["summary"]["observation_count"] == 2
    assert payload["summary"]["record_count"] == 2


def test_evidence_reference_normalization_precomputes_paths_once(tmp_path):
    inputs = [
        VerifiedInput(str(index), "KIND", tmp_path / str(index), 1, "A" * 64, "A" * 64)
        for index in range(16)
    ]
    payload = {
        "records": [
            {"evidence_paths": [str(inputs[0].path)], "value": index}
            for index in range(100)
        ]
    }

    started = time.perf_counter()
    normalized = _stable_evidence_references(payload, inputs)
    elapsed = time.perf_counter() - started

    assert normalized["records"][0]["evidence_paths"] == ["input:0"]
    assert elapsed < 1.0
