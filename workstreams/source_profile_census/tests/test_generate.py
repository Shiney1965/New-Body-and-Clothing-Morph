"""Generation boundary tests: real files, literal omissions and no authority flags."""

from dataclasses import replace
from hashlib import sha256
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from workstreams.source_profile_census.tests.test_snapshot import fixture, write_json
from workstreams.source_profile_census.tests.test_creation_paths import census, visual
from workstreams.source_profile_census.creation_paths import resolve_creation_paths


def api():
    name = "workstreams.source_profile_census.generate"
    assert importlib.util.find_spec(name), "Exact-source generator is not implemented"
    return importlib.import_module(name)


def configuration(fixture, tmp_path, **kwargs):
    source, _ = fixture
    return api().CensusConfiguration(sources=(source,), output_directory=tmp_path / "out", **kwargs)


@pytest.mark.parametrize("missing", ["file:a", "definition:b", "creation:c"])
def test_every_dropped_raw_discovery_row_is_reported(missing):
    expected = ["file:a", "definition:b", "creation:c"]
    result = api().audit_coverage(expected, [v for v in expected if v != missing])
    assert result["missing_from_census"] == [missing]
    assert result["census_without_source"] == []


def test_added_output_path_is_not_source_evidence():
    result = api().audit_coverage(["file:a"], ["file:a", "file:invented"])
    assert result["census_without_source"] == ["file:invented"]
    assert not result["complete"]


def test_duplicate_output_is_not_hidden_by_set_comparison():
    result = api().audit_coverage(["file:a"], ["file:a", "file:a"])
    assert result["duplicate_census_rows"] == ["file:a"]
    assert not result["complete"]


def test_unconverted_dependency_permission_and_missing_authority_remain_blocking(fixture, tmp_path):
    result = api().generate_census(configuration(fixture, tmp_path))
    candidate, = result.candidates
    assert candidate["release_profile_complete"] is False
    assert candidate["admissible_contract"] is None
    assert candidate["contract"]["profile_id"] is None
    assert candidate["contract"]["permission"]["evidence_sha256"] is None
    assert candidate["contract"]["supported_body_tuples"] is None
    assert {"PERMISSION_EVIDENCE_MISSING", "CANONICAL_PROFILE_ID_UNRESOLVED", "BODY_MAP_AUTHORITY_UNRESOLVED",
            "PRECEDENCE_AUTHORITY_UNRESOLVED", "DEPENDENCY_MISSING", "BINARY_CONVERSION_INCOMPLETE"} <= set(candidate["blockers"])
    assert result.audit["raw_coverage"]["complete"] is True
    assert result.audit["release_complete"] is False


def test_generation_is_byte_identical_and_refuses_overwrite(fixture, tmp_path):
    config = configuration(fixture, tmp_path)
    first = api().generate_census(config)
    second = api().generate_census(replace(config, output_directory=tmp_path / "second"))
    assert first.artifact_hashes == second.artifact_hashes
    assert {p.name: p.read_bytes() for p in config.output_directory.iterdir()} == {
        p.name: p.read_bytes() for p in (tmp_path / "second").iterdir()}
    before = (config.output_directory / "CENSUS_AUDIT.json").read_bytes()
    with pytest.raises(FileExistsError):
        api().generate_census(config)
    assert (config.output_directory / "CENSUS_AUDIT.json").read_bytes() == before


def test_input_manifest_contains_every_source_conversion_and_code_input(fixture, tmp_path):
    result = api().generate_census(configuration(fixture, tmp_path))
    manifest = json.loads((result.output_directory / "INPUT_MANIFEST.json").read_bytes())
    assert {r["role"] for r in manifest["inputs"]} >= {"package", "content_manifest", "listing", "source_file", "code"}
    source_rows = [r for r in manifest["inputs"] if r["role"] == "source_file"]
    assert len(source_rows) == 2
    assert all(len(r["sha256"]) == 64 and r["bytes"] > 0 for r in manifest["inputs"])


def test_changed_input_aborts_without_success_artifacts(fixture, tmp_path):
    config = configuration(fixture, tmp_path)
    (fixture[0]["root"] / "source.pak").write_bytes(b"drift")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        api().generate_census(config)
    assert not config.output_directory.exists()


def test_duplicate_sources_are_rejected(fixture, tmp_path):
    config = configuration(fixture, tmp_path)
    with pytest.raises(ValueError, match="DUPLICATE"):
        api().generate_census(replace(config, sources=config.sources * 2))


def test_output_cannot_be_inside_frozen_input(fixture, tmp_path):
    config = configuration(fixture, tmp_path)
    with pytest.raises(ValueError, match="OUTPUT_INPUT_OVERLAP"):
        api().generate_census(replace(config, output_directory=tmp_path / "extracted" / "new"))


def test_supplied_completion_flags_never_confer_authority(fixture, tmp_path):
    contract = write_json(tmp_path, "claimed.json", {"schema": "clothmorph.source-profile", "schema_version": 1,
        "profile_id": "invented", "release_profile_complete": True, "permission": {"state": "release_cleared"}})
    config = configuration(fixture, tmp_path, profile_contracts={fixture[0]["profile_id"]: {"root": tmp_path, **contract}})
    candidate, = api().generate_census(config).candidates
    assert not candidate["release_profile_complete"]
    assert candidate["admissible_contract"] is None
    assert "SUPPLIED_CONTRACT_INCOMPLETE" in candidate["blockers"]
    assert "PROFILE_AUTHORITY_VALIDATOR_UNAVAILABLE" in candidate["blockers"]


def test_sco_comparison_keeps_additions_duplicates_and_ordered_relationship_changes():
    old = [{"kind": "RootTemplate", "resource_id": "a", "relationships": [["VisualTemplate", "old"]]},
           {"kind": "VisualBank", "resource_id": "v", "relationships": [["SourceFile", "old.GR2"]]}]
    fresh = [{"kind": "RootTemplate", "resource_id": "a", "relationships": [["VisualTemplate", "new"]]},
             {"kind": "RootTemplate", "resource_id": "b", "relationships": []},
             {"kind": "RootTemplate", "resource_id": "b", "relationships": []}]
    comparison = api().compare_legacy_entries(old, fresh)
    assert comparison["added_ids"] == [["RootTemplate", "b"]]
    assert comparison["missing_fresh_ids"] == [["VisualBank", "v"]]
    assert comparison["changed_relationships"][0]["resource_id"] == "a"
    assert comparison["duplicate_fresh_ids"] == [["RootTemplate", "b"]]
    assert len(comparison["fresh_entries"]) == 3


def test_unreferenced_mesh_name_is_not_an_unreferenced_duplicate_path(tmp_path):
    source = census(tmp_path, visuals=visual("vr"), extras={"Other/robe.GR2": b"duplicate filename", "Other/unused.GR2": b"unused"})
    counts = api()._counts(source, resolve_creation_paths(source, ()))
    assert counts["unreferenced_mesh_paths"] == ["Other/robe.GR2", "Other/unused.GR2"]
    assert counts["unreferenced_mesh_names"] == ["unused.GR2"]


def test_legacy_structural_regrouping_is_reported_even_if_flat_values_match():
    old = [{"kind": "RootTemplate", "resource_id": "r", "relationships": [["Object", "v"]], "structure": ["one-map", "v"]}]
    fresh = [{"kind": "RootTemplate", "resource_id": "r", "relationships": [["Object", "v"]], "structure": ["other-map", "v"]}]
    assert len(api().compare_legacy_entries(old, fresh)["changed_relationships"]) == 1


def test_legacy_duplicate_occurrences_are_distinct_from_changed_semantic_relationships():
    row = {"kind": "RootTemplate", "resource_id": "r", "relationships": [["VisualTemplate", "v"]]}
    change, = api().compare_legacy_entries([row], [row, row])["changed_relationships"]
    assert change["change_kinds"] == ["ENTRY_MULTIPLICITY"]
    altered = {**row, "relationships": [["VisualTemplate", "new"]]}
    change, = api().compare_legacy_entries([row], [altered])["changed_relationships"]
    assert change["change_kinds"] == ["RELATIONSHIP_CONTENT"]


@pytest.mark.parametrize("invalid", ["schema_version", "profile_id", "module", "digest", "permission"])
def test_present_but_invalid_contract_fields_are_not_syntactically_complete(fixture, tmp_path, invalid):
    config = configuration(fixture, tmp_path)
    candidate, = api().generate_census(config).candidates
    claim = candidate["contract"]
    claim.update(profile_id="claimed-id", forbidden_modules=[], supported_body_tuples=[], route_partition_digest="A" * 64)
    claim["permission"] = {"state": "release_cleared", "evidence_sha256": "B" * 64, "credit_line": "Exact author", "distribution_limits": []}
    if invalid == "schema_version":
        claim["schema_version"] = True
    elif invalid == "profile_id":
        claim["profile_id"] = ""
    elif invalid == "module":
        del claim["module"]["uuid"]
    elif invalid == "digest":
        claim["route_partition_digest"] = "not a digest"
    else:
        claim["permission"]["state"] = "approved"
    proof = write_json(tmp_path, "claim.json", claim)
    config = replace(config, output_directory=tmp_path / "claim-out", profile_contracts={fixture[0]["profile_id"]: {"root": tmp_path, **proof}})
    emitted, = api().generate_census(config).candidates
    assert not emitted["supplied_contract_structurally_complete"]
    assert not emitted["release_profile_complete"]


def test_even_structurally_complete_self_consistent_contract_cannot_self_authorize(fixture, tmp_path):
    config = configuration(fixture, tmp_path)
    candidate, = api().generate_census(config).candidates
    claim = candidate["contract"]
    claim.update(profile_id="claimed-id", forbidden_modules=[], supported_body_tuples=[], route_partition_digest="A" * 64)
    claim["permission"] = {"state": "release_cleared", "evidence_sha256": "B" * 64, "credit_line": "Exact author", "distribution_limits": []}
    proof = write_json(tmp_path, "claim.json", claim)
    emitted, = api().generate_census(replace(config, output_directory=tmp_path / "claim-out",
        profile_contracts={fixture[0]["profile_id"]: {"root": tmp_path, **proof}})).candidates
    assert emitted["supplied_contract_structurally_complete"]
    assert emitted["admissible_contract"] is None
    assert not emitted["release_profile_complete"]
    assert "SUPPLIED_PERMISSION_SCOPE_UNVALIDATED" in emitted["blockers"]


def test_neutral_source_role_does_not_grant_or_remove_creation_eligibility(fixture, tmp_path):
    config = configuration(fixture, tmp_path)
    first = api().generate_census(config)
    neutral = {**config.sources[0], "role": "source"}
    second = api().generate_census(replace(config, sources=(neutral,), output_directory=tmp_path / "neutral"))
    assert first.audit["profiles"] == second.audit["profiles"]
    assert first.candidates[0]["blockers"] == second.candidates[0]["blockers"]
    assert second.candidates[0]["admissible_contract"] is None
    for name in ("RAW_FILES.json", "RAW_DEFINITIONS.json", "RAW_CREATION_PATHS.json"):
        assert (first.output_directory / name).read_bytes() == (second.output_directory / name).read_bytes()
