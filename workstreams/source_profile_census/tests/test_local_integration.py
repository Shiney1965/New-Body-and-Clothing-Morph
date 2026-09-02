"""Explicit opt-in checks of independently generated exact-source output pairs.

Set CLOTHMORPH_CENSUS_RUN_A and CLOTHMORPH_CENSUS_RUN_B to existing output
directories. Tests never discover or operate installed/live sources; retained
source evidence and output-pair fixtures remain read-only. The omission
regression generates one fresh test-owned output under the approved
local/generated root and removes only that temporary output in finally.
Portable runs skip only this local evidence fixture.
"""

from collections import Counter
from dataclasses import replace
import filecmp
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest


@pytest.fixture(scope="module")
def runs():
    values = [os.environ.get(name) for name in ("CLOTHMORPH_CENSUS_RUN_A", "CLOTHMORPH_CENSUS_RUN_B")]
    if not all(values):
        pytest.skip("Explicit exact-source census output pair not configured")
    paths = tuple(Path(v) for v in values)
    assert all(p.is_absolute() and p.is_dir() for p in paths)
    assert paths[0] != paths[1]
    return paths


def read(root, name):
    return json.loads((root / name).read_bytes())


def test_exact_output_bytes_match_between_independent_runs(runs):
    a, b = runs
    assert {p.name for p in a.iterdir()} == {p.name for p in b.iterdir()}
    for path in a.iterdir():
        assert filecmp.cmp(path, b / path.name, shallow=False), path.name
    manifest = read(a, "OUTPUT_MANIFEST.json")
    assert {r["path"] for r in manifest["artifacts"]} == {p.name for p in a.iterdir()} - {"OUTPUT_MANIFEST.json"}
    for row in manifest["artifacts"]:
        data = (a / row["path"]).read_bytes()
        assert len(data) == row["bytes"]
        assert sha256(data).hexdigest().upper() == row["sha256"]


def test_all_configured_frozen_files_are_accounted_for(runs):
    audit = read(runs[0], "CENSUS_AUDIT.json")
    snapshots = read(runs[0], "SOURCE_SNAPSHOTS.json")
    raw = read(runs[0], "RAW_FILES.json")
    expected = Counter(f"file:{s['profile_id']}:{f['relative_path']}" for s in snapshots for f in s["files"])
    assert expected == Counter(r["row_id"] for r in raw)
    assert len(raw) == 2970
    assert audit["configured_source_count"] == len(snapshots) == 10
    assert audit["raw_coverage"]["complete"]
    assert all(not value for key, value in audit["raw_coverage"].items() if key != "complete")
    assert all(p["counts"]["unconverted_binary_paths"] == [] for p in audit["profiles"])


def test_etheirys_exact_source_regression_controls(runs):
    audit = read(runs[0], "CENSUS_AUDIT.json")
    profile, = [p for p in audit["profiles"] if p["module"]["uuid"] == "5c259070-7f97-e136-eeab-83c058ad152e"]
    assert profile["package"]["sha256"] == "29C81F71982B4FF651CFDE0E3C13E267C0E6AC3224CB024BE21FCAD2DDFB4733"
    counts = profile["counts"]
    assert counts["binary_bank_file_count"] == counts["verified_conversion_count"] == 164
    assert counts["definitions_by_kind"] == {"CharacterCreationAccessorySet": 61, "CharacterCreationSharedVisual": 70,
        "VisualBank": 70, "MaterialBank": 33, "TextureBank": 67}
    assert counts["shared_visual_resolved_join_count"] == 70
    assert counts["distinct_gr2_name_count"] == 42
    assert counts["unreferenced_mesh_names"] == ["PRC_Luminiari_Historia_Dyeable_L.GR2", "PRC_Luminiari_Zormor_L_Tintable.GR2"]
    raw = read(runs[0], "RAW_CREATION_PATHS.json")
    source_ids = {d["observation_id"] for d in read(runs[0], "RAW_DEFINITIONS.json")
                  if d["source"]["profile_id"] == profile["discovery_profile_id"]}
    creation = [r for r in raw if r["source_observation_id"] in source_ids]
    assert Counter(r["kind"] for r in creation) == {"CHARACTER_CREATION_ACCESSORY_SET": 61, "CHARACTER_CREATION_SHARED_VISUAL": 70}
    assert all(r["scope"] == "NON_GARMENT_PIERCING" for r in creation)
    shared = [r for r in creation if r["kind"] == "CHARACTER_CREATION_SHARED_VISUAL"]
    assert all(len(r["routes"]) == 1 and len(r["routes"][0]["components"]) == 1
               and r["routes"][0]["components"][0]["mesh"] is not None for r in shared)


def test_raw_definitions_match_file_discoveries_and_creation_owners(runs):
    raw_files = read(runs[0], "RAW_FILES.json")
    expected = Counter(identity for row in raw_files for identity in row["definition_ids"])
    del raw_files
    definitions = read(runs[0], "RAW_DEFINITIONS.json")
    observed = Counter(d["observation_id"] for d in definitions)
    assert expected == observed
    assert len(definitions) == 3062
    del definitions
    paths = read(runs[0], "RAW_CREATION_PATHS.json")
    assert len(paths) == 6681
    assert all(row["source_observation_id"] in observed for row in paths)
    assert len({row["row_id"] for row in paths}) == len(paths)
    inventory = read(runs[0], "CREATION_DISCOVERY.json")
    assert Counter(row["observation_id"] for row in inventory) == Counter(row["observation_id"] for row in paths)
    assert all(row["declarations"] for row in inventory)


def test_sco_old_registry_population_never_replaces_fresh_packed_population(runs):
    comparison, = read(runs[0], "LEGACY_COMPARISONS.json")
    assert comparison["legacy_authoritative"] is False
    assert Counter(r["kind"] for r in comparison["fresh_entries"]) == {"RootTemplate": 262, "VisualBank": 1452}
    assert comparison["added_ids"]
    assert comparison["changed_relationships"]
    assert comparison["duplicate_fresh_ids"]
    assert all("structure" in r for r in comparison["old_entries"] + comparison["fresh_entries"])


def test_every_actual_source_is_an_incomplete_candidate(runs):
    candidates = read(runs[0], "SOURCE_PROFILE_CANDIDATES.json")
    assert len(candidates) == 10
    etheirys, = [c for c in candidates if c["contract"]["module"]["uuid"] == "5c259070-7f97-e136-eeab-83c058ad152e"]
    assert etheirys["role"] == "source"
    for candidate in candidates:
        assert not candidate["release_profile_complete"]
        assert candidate["admissible_contract"] is None
        assert candidate["contract"]["profile_id"] is None
        assert candidate["contract"]["permission"]["evidence_sha256"] is None
        assert candidate["contract"]["route_partition_digest"] is None
        assert "PROFILE_AUTHORITY_VALIDATOR_UNAVAILABLE" in candidate["blockers"]
    audit = read(runs[0], "CENSUS_AUDIT.json")
    assert "BASE_GAME_SOURCE_PROFILE_UNRESOLVED" in audit["unresolved_inputs"]
    assert not audit["release_complete"]
    assert not audit["canonical_ledger_integrated"]


def test_all_input_hashes_still_match_frozen_evidence_and_code(runs):
    # Every locator is a previously explicit configured, hash-bound input, not a
    # recursively discovered live root. Duplicate manifest uses open only once.
    manifest = read(runs[0], "INPUT_MANIFEST.json")
    seen = set()
    for row in manifest["inputs"]:
        key = row["locator"], row["sha256"]
        if key in seen:
            continue
        seen.add(key)
        path = Path(row["locator"])
        assert path.stat().st_size == row["bytes"]
        hasher = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        assert hasher.hexdigest().upper() == row["sha256"], str(path)


def test_real_source_removed_creation_observation_is_reported_by_generator(runs, monkeypatch):
    from workstreams.source_profile_census import generate
    manifest = read(runs[0], "INPUT_MANIFEST.json")
    first = manifest["configuration"]["sources"][0]
    output = Path(generate.__file__).resolve().parent / "local/generated" / ("real-omission-test-" + uuid4().hex)
    original = generate.resolve_creation_paths
    removed = []
    def omit_one(*args):
        census = original(*args)
        removed.append("creation:" + census.observations[0].observation_id)
        return replace(census, observations=census.observations[1:])
    monkeypatch.setattr(generate, "resolve_creation_paths", omit_one)
    try:
        result = generate.generate_census(generate.CensusConfiguration(sources=(first,), output_directory=output))
        assert result.audit["raw_coverage"]["missing_from_census"] == removed
        assert not result.audit["raw_coverage"]["complete"]
        assert "CREATION_CENSUS_COVERAGE_MISMATCH" in result.candidates[0]["blockers"]
    finally:
        if output.exists():
            assert output.parent == Path(generate.__file__).resolve().parent / "local/generated"
            assert output.name.startswith("real-omission-test-")
            shutil.rmtree(output)
