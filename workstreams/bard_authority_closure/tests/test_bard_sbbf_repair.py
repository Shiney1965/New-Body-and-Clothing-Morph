from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import numpy as np
import pytest

from workstreams.bard_authority_closure.bard_sbbf_repair import (
    BASE_STREAMS,
    PASS_REPAIRED,
    PASS_UNCHANGED,
    CompletePairResult,
    SBBFPairContract,
    SBBFPairRevalidationContext,
    StreamIdentity,
    build_stream_revalidation_context,
    complete_sbbf_pair,
    failing_face_neighborhood,
    index_topology_digest,
    solve_local_area_constrained_positions,
    topology_metrics,
    verify_outside_region_exact,
    write_offline_result,
)
from workstreams.bard_authority_closure.configuration import (
    ConfigurationError,
    load_local_configuration,
    verify_evidence_inputs,
)


LEGACY_INPUT_IDS = {
    "legacy_bard_contracts_py",
    "legacy_glb_contract_py",
    "legacy_reconstruct_positions_py",
    "body_bcb_glb",
    "body_sbbf_glb",
    "base_source_glb",
    "thong_source_glb",
    "legacy_offline_search_report",
}
SLEEVE_STREAM = "HUM_F_ARM_Bard_Sleeves_Mesh"
THONG_STREAM = "HUM_F_ARM_Gortash_Body_Jacket_Mesh"


def _synthetic_low_area_mesh() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
            [2.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [11.0, 0.0, 0.0],
            [10.0, 1.0, 0.0],
        ],
        dtype="<f4",
    )
    candidate = source.copy()
    candidate[2] = [0.0, 0.1, 0.0]
    faces = np.asarray(
        [
            [0, 1, 2],
            [1, 3, 2],
            [1, 4, 3],
            [5, 6, 7],
        ],
        dtype="<u4",
    )
    return source, candidate, faces


def _synthetic_identity(
    stream_id: str,
    *,
    component: str,
    position_shape: tuple[int, int] = (3, 3),
    faces: np.ndarray | None = None,
) -> StreamIdentity:
    if faces is None:
        faces = np.asarray([[0, 1, 2]], dtype="<u4")
    source_path = str(Path(f"C:/synthetic/{component}_source.glb"))
    return StreamIdentity(
        stream_id=stream_id,
        verified_source_path=source_path,
        verified_source_sha256=("A" if component == "base" else "B") * 64,
        position_shape=position_shape,
        index_topology_sha256=index_topology_digest(faces),
        non_position_semantic_sha256=hashlib.sha256(
            f"{stream_id}:non-position".encode()
        ).hexdigest().upper(),
    )


def _passing_result(stream_id: str, offset: float = 0.0, *, component: str = "base"):
    source = np.asarray(
        [[offset, 0.0, 0.0], [offset + 1.0, 0.0, 0.0], [offset, 1.0, 0.0]],
        dtype="<f4",
    )
    return solve_local_area_constrained_positions(
        source,
        source.copy(),
        np.asarray([[0, 1, 2]], dtype="<u4"),
        stream_identity=_synthetic_identity(stream_id, component=component),
    )


def _passing_pair() -> tuple[
    dict[str, object],
    object,
    SBBFPairContract,
    SBBFPairRevalidationContext,
]:
    base = {
        name: _passing_result(name, float(index) * 10.0)
        for index, name in enumerate(BASE_STREAMS)
    }
    thong = _passing_result(THONG_STREAM, 100.0, component="thong")
    contract = SBBFPairContract(
        base_identities=tuple(base[name].stream_identity for name in BASE_STREAMS),
        thong_identity=thong.stream_identity,
    )
    faces = np.asarray([[0, 1, 2]], dtype="<u4")
    context = SBBFPairRevalidationContext(
        pair_contract=contract,
        base_streams=tuple(
            build_stream_revalidation_context(
                base[name].positions,
                base[name].positions,
                faces,
                base[name].stream_identity,
            )
            for name in BASE_STREAMS
        ),
        thong_stream=build_stream_revalidation_context(
            thong.positions,
            thong.positions,
            faces,
            thong.stream_identity,
        ),
    )
    return base, thong, contract, context


def test_failing_face_neighborhood_is_only_the_seed_face_one_ring():
    source, candidate, faces = _synthetic_low_area_mesh()

    region = failing_face_neighborhood(source, candidate, faces)

    assert region.failing_face_indices == (0,)
    assert region.seed_vertex_indices == (0, 1, 2)
    assert region.one_ring_face_indices == (0, 1, 2)
    assert region.movable_vertex_indices == (0, 1, 2, 3, 4)
    assert region.affected_face_indices == (0, 1, 2)


def test_solver_repairs_the_full_mesh_without_moving_any_outside_float32_row():
    source, candidate, faces = _synthetic_low_area_mesh()

    result = solve_local_area_constrained_positions(
        source,
        candidate,
        faces,
        stream_identity=_synthetic_identity(
            "synthetic_low_area",
            component="base",
            position_shape=(8, 3),
            faces=faces,
        ),
    )

    assert result.status == PASS_REPAIRED
    assert result.positions is not None
    assert result.positions.dtype == np.dtype("<f4")
    assert result.pre_metrics.below_area_floor == 1
    assert result.post_metrics is not None
    assert result.post_metrics.flipped_faces == 0
    assert result.post_metrics.new_zero_area_faces == 0
    assert result.post_metrics.below_area_floor == 0
    assert result.post_metrics.minimum_area_ratio >= 0.25
    assert result.outside_gate is not None
    assert result.outside_gate.passed
    np.testing.assert_array_equal(result.positions[5:], candidate[5:])


def test_solver_search_is_exactly_4096_and_cannot_be_overridden():
    source, candidate, faces = _synthetic_low_area_mesh()

    with pytest.raises(TypeError):
        solve_local_area_constrained_positions(
            source,
            candidate,
            faces,
            stream_identity=_synthetic_identity(
                "synthetic_low_area",
                component="base",
                position_shape=(8, 3),
                faces=faces,
            ),
            blend_steps=8,
        )

    result = solve_local_area_constrained_positions(
        source,
        candidate,
        faces,
        stream_identity=_synthetic_identity(
            "synthetic_low_area",
            component="base",
            position_shape=(8, 3),
            faces=faces,
        ),
    )
    assert result.blend_steps == 4096


def test_solver_cannot_pass_below_half_retained_completion():
    source = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype="<f4",
    )
    candidate = source.copy()
    candidate[2, 1] = -1.0
    faces = np.asarray([[0, 1, 2]], dtype="<u4")

    result = solve_local_area_constrained_positions(
        source,
        candidate,
        faces,
        stream_identity=_synthetic_identity("completion_floor", component="base"),
    )

    assert result.status == "METHOD_SPECIFIC_EXHAUSTION"
    assert result.positions is None
    assert result.exhaustion_reason == "ONE_RING_COMPLETION_FLOOR_EXHAUSTED"


def test_outside_region_gate_rejects_one_changed_float32_row():
    source, candidate, faces = _synthetic_low_area_mesh()
    region = failing_face_neighborhood(source, candidate, faces)
    escaped = candidate.copy()
    escaped[7, 2] = np.float32(0.5)

    report = verify_outside_region_exact(candidate, escaped, region.movable_vertex_indices)

    assert not report.passed
    assert report.changed_outside_rows == (7,)


def test_outside_region_gate_compares_float32_bytes_not_numeric_values():
    before_bits = np.asarray(
        [
            [0x00000000, 0x7FC00001, 0x3F800000],
            [0x40000000, 0x40400000, 0x40800000],
        ],
        dtype="<u4",
    )
    before = before_bits.view("<f4")
    same_bytes = before.copy()
    signed_zero_change = before.copy()
    signed_zero_change.view("<u4")[0, 0] = 0x80000000

    assert verify_outside_region_exact(before, same_bytes, ()).passed
    report = verify_outside_region_exact(before, signed_zero_change, ())
    assert not report.passed
    assert report.changed_outside_rows == (0,)


def test_complete_pair_fails_closed_for_partial_or_contract_changed_output(tmp_path: Path):
    base, thong, contract, context = _passing_pair()
    missing = dict(base)
    missing.pop(BASE_STREAMS[-1])

    partial = complete_sbbf_pair(missing, thong, contract, context)
    changed_identity = replace(
        base[BASE_STREAMS[0]],
        stream_identity=replace(
            base[BASE_STREAMS[0]].stream_identity,
            non_position_semantic_sha256="F" * 64,
        ),
    )
    changed = dict(base)
    changed[BASE_STREAMS[0]] = changed_identity
    semantic_change = complete_sbbf_pair(changed, thong, contract, context)

    for index, result in enumerate((partial, semantic_change), start=1):
        assert result.status == "METHOD_SPECIFIC_EXHAUSTION"
        assert result.replacement_routes == 0
        assert result.candidate_positions is None
        report_path, candidate_path = write_offline_result(tmp_path / f"exhausted-{index}", result)
        assert report_path.is_file()
        assert candidate_path is None
        assert not (tmp_path / f"exhausted-{index}" / "bard_sbbf_candidate_positions.npz").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("verified_source_path", str(Path("C:/synthetic/other.glb"))),
        ("verified_source_sha256", "C" * 64),
        ("position_shape", (4, 3)),
        ("index_topology_sha256", "D" * 64),
        ("non_position_semantic_sha256", "E" * 64),
    ),
)
def test_complete_pair_derives_and_compares_every_stream_identity_field(field: str, value):
    base, thong, contract, context = _passing_pair()
    first = BASE_STREAMS[0]
    changed = dict(base)
    changed[first] = replace(
        base[first],
        stream_identity=replace(base[first].stream_identity, **{field: value}),
    )

    result = complete_sbbf_pair(changed, thong, contract, context)

    assert result.status == "METHOD_SPECIFIC_EXHAUSTION"
    assert result.exhaustion_reason == f"SBBF_STREAM_IDENTITY_MISMATCH:{first}"
    assert result.candidate_positions is None


def test_complete_pair_rejects_mapping_relabel_thong_relabel_and_removed_default_gates():
    base, thong, contract, context = _passing_pair()
    relabeled = dict(base)
    relabeled[BASE_STREAMS[0]] = replace(
        base[BASE_STREAMS[0]],
        stream_identity=replace(
            base[BASE_STREAMS[0]].stream_identity,
            stream_id=BASE_STREAMS[1],
        ),
    )
    wrong_thong = replace(
        thong,
        stream_identity=replace(thong.stream_identity, stream_id=BASE_STREAMS[0]),
    )

    assert complete_sbbf_pair(relabeled, thong, contract, context).status == "METHOD_SPECIFIC_EXHAUSTION"
    assert complete_sbbf_pair(base, wrong_thong, contract, context).status == "METHOD_SPECIFIC_EXHAUSTION"
    with pytest.raises(TypeError):
        complete_sbbf_pair(base, thong, contract, context, semantic_contract_exact=False)


def test_complete_pair_rechecks_fixed_search_and_half_completion_floor():
    base, thong, contract, context = _passing_pair()
    first = BASE_STREAMS[0]
    wrong_search = dict(base)
    wrong_search[first] = replace(base[first], blend_steps=2048)
    below_floor = dict(base)
    below_floor[first] = replace(base[first], blend_step=2049)

    search_result = complete_sbbf_pair(wrong_search, thong, contract, context)
    floor_result = complete_sbbf_pair(below_floor, thong, contract, context)

    assert search_result.status == "METHOD_SPECIFIC_EXHAUSTION"
    assert search_result.exhaustion_reason == f"SBBF_SEARCH_INVARIANT_FAILURE:{first}"
    assert floor_result.status == "METHOD_SPECIFIC_EXHAUSTION"
    assert floor_result.exhaustion_reason == f"SBBF_COMPLETION_FLOOR_FAILURE:{first}"


@pytest.mark.parametrize(
    "mutation",
    ("zeros", "wrong_shape", "nonfinite", "position_hash", "status_blend"),
)
def test_complete_pair_recomputes_positions_instead_of_trusting_candidate_summaries(mutation: str):
    base, thong, contract, context = _passing_pair()
    first = BASE_STREAMS[0]
    original = base[first]
    if mutation == "zeros":
        forged = replace(original, positions=np.zeros_like(original.positions))
    elif mutation == "wrong_shape":
        forged = replace(original, positions=original.positions[:-1])
    elif mutation == "nonfinite":
        positions = original.positions.copy()
        positions[0, 0] = np.nan
        forged = replace(original, positions=positions)
    elif mutation == "position_hash":
        forged = replace(original, position_sha256="F" * 64)
    else:
        forged = replace(original, status=PASS_REPAIRED, blend_step=0)
    changed = dict(base)
    changed[first] = forged

    result = complete_sbbf_pair(changed, thong, contract, context)

    assert result.status == "METHOD_SPECIFIC_EXHAUSTION"
    assert result.exhaustion_reason == f"SBBF_STREAM_REVALIDATION_FAILURE:{first}"
    assert result.candidate_positions is None


@pytest.mark.parametrize("summary", ("topology", "outside"))
def test_complete_pair_rejects_stale_topology_and_outside_summaries(summary: str):
    base, thong, contract, context = _passing_pair()
    first = BASE_STREAMS[0]
    original = base[first]
    if summary == "topology":
        forged = replace(
            original,
            post_metrics=replace(
                original.post_metrics,
                minimum_area_ratio=original.post_metrics.minimum_area_ratio + 0.125,
            ),
        )
    else:
        forged = replace(
            original,
            outside_gate=replace(original.outside_gate, changed_outside_rows=(0,)),
        )
    changed = dict(base)
    changed[first] = forged

    result = complete_sbbf_pair(changed, thong, contract, context)

    assert result.status == "METHOD_SPECIFIC_EXHAUSTION"
    assert result.exhaustion_reason == f"SBBF_STREAM_REVALIDATION_FAILURE:{first}"


def _test_pair_digest(positions: dict[str, dict[str, np.ndarray]]) -> str:
    digest = hashlib.sha256()
    for component in ("base", "thong"):
        for stream in sorted(positions[component]):
            digest.update(component.encode("utf-8"))
            digest.update(stream.encode("utf-8"))
            digest.update(np.asarray(positions[component][stream], dtype="<f4").tobytes(order="C"))
    return digest.hexdigest().upper()


def test_writer_rejects_zeroed_positions_with_stale_summaries_before_creating_directory(
    tmp_path: Path,
):
    base, thong, contract, context = _passing_pair()
    valid = complete_sbbf_pair(base, thong, contract, context)
    first = BASE_STREAMS[0]
    zero_positions = np.zeros_like(base[first].positions)
    forged_stream = replace(base[first], positions=zero_positions)
    forged_base = dict(base)
    forged_base[first] = forged_stream
    forged_positions = {
        "base": dict(valid.candidate_positions["base"]),
        "thong": dict(valid.candidate_positions["thong"]),
    }
    forged_positions["base"][first] = zero_positions
    forged = replace(
        valid,
        base_results=forged_base,
        candidate_positions=forged_positions,
        position_digest=_test_pair_digest(forged_positions),
    )
    output = tmp_path / "must-not-exist"

    with pytest.raises(ValueError, match="OFFLINE_RESULT_NOT_EMITTABLE"):
        write_offline_result(output, forged)

    assert not output.exists()


def test_complete_pair_emits_only_all_four_base_streams_plus_passing_thong(tmp_path: Path):
    base, thong, contract, context = _passing_pair()

    result = complete_sbbf_pair(base, thong, contract, context)
    report_path, candidate_path = write_offline_result(tmp_path, result)

    assert result.status == "PASS_OFFLINE_SBBF_PAIR"
    assert result.replacement_routes == 2
    assert result.position_digest is not None
    assert candidate_path is not None and candidate_path.is_file()
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    first = BASE_STREAMS[0]
    assert report["base_streams"][first]["stream_identity"] == {
        "stream_id": first,
        "verified_source_path": base[first].stream_identity.verified_source_path,
        "verified_source_sha256": base[first].stream_identity.verified_source_sha256,
        "position_shape": [3, 3],
        "index_topology_sha256": base[first].stream_identity.index_topology_sha256,
        "non_position_semantic_sha256": base[first].stream_identity.non_position_semantic_sha256,
    }
    assert report["base_streams"][first]["retained_completion"] == {
        "numerator": 4096,
        "denominator": 4096,
    }
    with np.load(candidate_path, allow_pickle=False) as payload:
        assert set(payload.files) == {
            *(f"base::{name}" for name in BASE_STREAMS),
            f"thong::{THONG_STREAM}",
        }


@pytest.mark.parametrize(
    "mutation",
    (
        "status",
        "routes",
        "base_keys",
        "thong_keys",
        "position_digest",
        "pair_gate",
    ),
)
def test_writer_revalidates_complete_pair_instead_of_trusting_pass_label(
    tmp_path: Path,
    mutation: str,
):
    base, thong, contract, context = _passing_pair()
    result = complete_sbbf_pair(base, thong, contract, context)
    if mutation == "status":
        tampered = replace(result, status="METHOD_SPECIFIC_EXHAUSTION")
    elif mutation == "routes":
        tampered = replace(result, replacement_routes=1)
    elif mutation == "base_keys":
        positions = {
            "base": dict(result.candidate_positions["base"]),
            "thong": dict(result.candidate_positions["thong"]),
        }
        positions["base"].pop(BASE_STREAMS[0])
        tampered = replace(result, candidate_positions=positions)
    elif mutation == "thong_keys":
        positions = {
            "base": dict(result.candidate_positions["base"]),
            "thong": {BASE_STREAMS[0]: result.candidate_positions["thong"][THONG_STREAM]},
        }
        tampered = replace(result, candidate_positions=positions)
    elif mutation == "position_digest":
        tampered = replace(result, position_digest="F" * 64)
    else:
        changed = dict(result.base_results)
        changed[BASE_STREAMS[0]] = replace(changed[BASE_STREAMS[0]], blend_step=2049)
        tampered = replace(result, base_results=changed)

    with pytest.raises(ValueError, match="OFFLINE_RESULT_NOT_EMITTABLE"):
        write_offline_result(tmp_path / mutation, tampered)

    assert not (tmp_path / mutation / "bard_sbbf_candidate_positions.npz").exists()
    assert not (tmp_path / mutation / "bard_sbbf_repair_report.json").exists()


def test_writer_refuses_prior_artifacts_and_never_labels_a_stale_candidate_exhausted(tmp_path: Path):
    base, thong, contract, context = _passing_pair()
    passing = complete_sbbf_pair(base, thong, contract, context)
    exhausted = complete_sbbf_pair({key: value for key, value in base.items() if key != BASE_STREAMS[0]}, thong, contract, context)
    output = tmp_path / "fresh-only"

    write_offline_result(output, passing)
    with pytest.raises(FileExistsError, match="OFFLINE_OUTPUT_ALREADY_EXISTS"):
        write_offline_result(output, passing)
    with pytest.raises(FileExistsError, match="OFFLINE_OUTPUT_ALREADY_EXISTS"):
        write_offline_result(output, exhausted)

    report = json.loads((output / "bard_sbbf_repair_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS_OFFLINE_SBBF_PAIR"
    assert (output / "bard_sbbf_candidate_positions.npz").is_file()


@pytest.mark.parametrize(
    "prior_name",
    ("bard_sbbf_candidate_positions.npz", "bard_sbbf_repair_report.json"),
)
def test_writer_refuses_each_prior_artifact_independently(tmp_path: Path, prior_name: str):
    base, thong, contract, context = _passing_pair()
    passing = complete_sbbf_pair(base, thong, contract, context)
    output = tmp_path / prior_name.replace(".", "-")
    output.mkdir()
    (output / prior_name).write_bytes(b"retained prior artifact")

    with pytest.raises(FileExistsError, match="OFFLINE_OUTPUT_ALREADY_EXISTS"):
        write_offline_result(output, passing)


def _load_hash_locked_legacy_reconstruction():
    try:
        verified = verify_evidence_inputs(load_local_configuration())
    except ConfigurationError as error:
        pytest.skip(f"hash-locked local Bard evidence unavailable: {error}")
    by_id = {item.input_id: item for item in verified}
    missing = LEGACY_INPUT_IDS - set(by_id)
    if missing:
        pytest.fail(f"missing hash-locked input IDs: {sorted(missing)}")
    source_directory = by_id["legacy_bard_contracts_py"].path.parent
    package_digest = hashlib.sha256(
        "|".join(
            by_id[input_id].actual_sha256
            for input_id in (
                "legacy_bard_contracts_py",
                "legacy_glb_contract_py",
                "legacy_reconstruct_positions_py",
            )
        ).encode("ascii")
    ).hexdigest()[:16]
    package_name = f"_bard_legacy_{package_digest}"
    for module_name in (
        f"{package_name}.reconstruct_positions",
        f"{package_name}.glb_contract",
        f"{package_name}.bard_contracts",
        package_name,
    ):
        sys.modules.pop(module_name, None)
    package = types.ModuleType(package_name)
    package.__package__ = package_name
    package.__path__ = [str(source_directory)]
    sys.modules[package_name] = package

    def load_exact(module_basename: str, input_id: str):
        verified_input = by_id[input_id]
        path = verified_input.path.resolve()
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert actual_sha256 == verified_input.actual_sha256
        full_name = f"{package_name}.{module_basename}"
        specification = importlib.util.spec_from_file_location(full_name, path)
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        sys.modules[full_name] = module
        specification.loader.exec_module(module)
        assert Path(module.__file__).resolve() == path
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest().upper() == actual_sha256
        return module

    contracts = load_exact("bard_contracts", "legacy_bard_contracts_py")
    glb_contract = load_exact("glb_contract", "legacy_glb_contract_py")
    legacy = load_exact("reconstruct_positions", "legacy_reconstruct_positions_py")
    return legacy, contracts, glb_contract, {
        input_id: item.actual_sha256
        for input_id, item in sorted(by_id.items())
    }, by_id


def test_real_harness_uses_unique_exact_hash_verified_module_names():
    legacy, contracts, glb_contract, input_hashes, _ = _load_hash_locked_legacy_reconstruction()

    assert legacy.__name__.startswith("_bard_legacy_")
    assert contracts.__name__.startswith("_bard_legacy_")
    assert glb_contract.__name__.startswith("_bard_legacy_")
    assert not legacy.__name__.startswith("src.")
    assert not contracts.__name__.startswith("src.")
    assert not glb_contract.__name__.startswith("src.")
    assert Path(legacy.__file__).resolve() == Path(
        r"C:\Claude Projects\BG3 Mods\ChatGPT Work Files\Bard_Vanilla_SBBF_Reconstruction_20260826\src\reconstruct_positions.py"
    ).resolve()
    assert Path(contracts.__file__).resolve() == Path(
        r"C:\Claude Projects\BG3 Mods\ChatGPT Work Files\Bard_Vanilla_SBBF_Reconstruction_20260826\src\bard_contracts.py"
    ).resolve()
    assert hashlib.sha256(Path(legacy.__file__).read_bytes()).hexdigest().upper() == input_hashes[
        "legacy_reconstruct_positions_py"
    ]
    assert hashlib.sha256(Path(contracts.__file__).read_bytes()).hexdigest().upper() == input_hashes[
        "legacy_bard_contracts_py"
    ]


def _non_position_semantic_digest(fingerprint: dict[str, object], mesh_name: str) -> str:
    primitive = next(
        value
        for value in fingerprint["primitive_contracts"]
        if value["mesh"] == mesh_name
    )
    payload = {
        "mesh": primitive["mesh"],
        "mode": primitive["mode"],
        "material": primitive["material"],
        "attributes": primitive["attributes"],
        "mesh_order": fingerprint["mesh_order"],
        "skin_fingerprints": fingerprint["skin_fingerprints"],
        "material_order": fingerprint["material_order"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()


def _real_identity(
    stream: dict[str, object],
    verified_input,
    fingerprint: dict[str, object],
) -> StreamIdentity:
    return StreamIdentity(
        stream_id=stream["mesh"],
        verified_source_path=str(verified_input.path.resolve()),
        verified_source_sha256=verified_input.actual_sha256,
        position_shape=tuple(map(int, stream["positions"].shape)),
        index_topology_sha256=index_topology_digest(stream["triangles"]),
        non_position_semantic_sha256=_non_position_semantic_digest(
            fingerprint,
            stream["mesh"],
        ),
    )


def _real_sbbf_inputs():
    legacy, contracts, glb_contract, input_hashes, verified = _load_hash_locked_legacy_reconstruction()
    base_input = verified["base_source_glb"]
    thong_source_input = verified["thong_source_glb"]
    base_path = base_input.path
    thong_path = thong_source_input.path
    body_bcb_path = verified["body_bcb_glb"].path
    body_sbbf_path = verified["body_sbbf_glb"].path
    assert (contracts.BARD_GLB_ROOT / base_path.name).resolve() == base_path.resolve()
    assert (contracts.BARD_GLB_ROOT / thong_path.name).resolve() == thong_path.resolve()
    assert (contracts.BODY_ROOT / body_bcb_path.name).resolve() == body_bcb_path.resolve()
    assert (contracts.BODY_ROOT / body_sbbf_path.name).resolve() == body_sbbf_path.resolve()
    base_fingerprint = glb_contract.fingerprint_glb(base_path)
    thong_fingerprint = glb_contract.fingerprint_glb(thong_path)
    source_body = legacy.pose_body_to_rig(body_bcb_path, base_path)
    target_body = legacy.pose_body_to_rig(body_sbbf_path, base_path)
    base_inputs = {}
    for stream in legacy.mesh_streams(base_path):
        delta = legacy.smooth_delta_on_topology(
            legacy.cross_section_delta(source_body, target_body, stream["positions"]),
            stream["triangles"],
        )
        candidate = stream["positions"] + 0.5 * delta
        base_inputs[stream["mesh"]] = (
            stream["positions"],
            candidate,
            stream["triangles"],
            _real_identity(stream, base_input, base_fingerprint),
        )

    thong_source_body = legacy.pose_body_to_rig(body_bcb_path, thong_path)
    thong_target_body = legacy.pose_body_to_rig(body_sbbf_path, thong_path)
    thong_stream = legacy.mesh_streams(thong_path)[0]
    thong_delta = legacy.smooth_delta_on_topology(
        legacy.cross_section_delta(thong_source_body, thong_target_body, thong_stream["positions"]),
        thong_stream["triangles"],
    )
    thong_input = (
        thong_stream["positions"],
        thong_stream["positions"] + thong_delta,
        thong_stream["triangles"],
        _real_identity(thong_stream, thong_source_input, thong_fingerprint),
    )
    pair_contract = SBBFPairContract(
        base_identities=tuple(base_inputs[name][3] for name in BASE_STREAMS),
        thong_identity=thong_input[3],
    )
    revalidation_context = SBBFPairRevalidationContext(
        pair_contract=pair_contract,
        base_streams=tuple(
            build_stream_revalidation_context(*base_inputs[name])
            for name in BASE_STREAMS
        ),
        thong_stream=build_stream_revalidation_context(*thong_input),
    )
    return base_inputs, thong_input, pair_contract, revalidation_context, input_hashes


def _solve_real_input(stream_input):
    source, candidate, faces, identity = stream_input
    return solve_local_area_constrained_positions(
        source,
        candidate,
        faces,
        stream_identity=identity,
    )


def test_real_hash_locked_alpha_floor_is_repaired_deterministically(tmp_path: Path):
    base_inputs, thong_input, pair_contract, revalidation_context, input_hashes = _real_sbbf_inputs()
    sleeve_source, sleeve_candidate, sleeve_faces, sleeve_identity = base_inputs[SLEEVE_STREAM]
    retained = topology_metrics(sleeve_source, sleeve_candidate, sleeve_faces)

    assert retained.flipped_faces == 0
    assert retained.new_zero_area_faces == 0
    assert retained.below_area_floor == 1
    assert retained.minimum_area_ratio == 0.159049789992582

    run_results: list[CompletePairResult] = []
    for run_number in (1, 2):
        base_results = {
            name: _solve_real_input(base_inputs[name])
            for name in BASE_STREAMS
        }
        thong_result = _solve_real_input(thong_input)
        complete = complete_sbbf_pair(
            base_results,
            thong_result,
            pair_contract,
            revalidation_context,
        )
        run_results.append(complete)
        report_path, candidate_path = write_offline_result(
            tmp_path / f"run-{run_number}",
            complete,
            input_hashes=input_hashes,
        )
        assert report_path.is_file()
        assert candidate_path is not None and candidate_path.is_file()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["verified_input_sha256"] == input_hashes

    first, second = run_results
    assert first.status == second.status == "PASS_OFFLINE_SBBF_PAIR"
    assert first.position_digest == second.position_digest
    assert first.candidate_positions is not None
    assert second.candidate_positions is not None
    first_sleeve = first.candidate_positions["base"][SLEEVE_STREAM]
    second_sleeve = second.candidate_positions["base"][SLEEVE_STREAM]
    np.testing.assert_array_equal(first_sleeve, second_sleeve)
    sleeve_result = solve_local_area_constrained_positions(
        sleeve_source,
        sleeve_candidate,
        sleeve_faces,
        stream_identity=sleeve_identity,
    )
    assert sleeve_result.region.failing_face_indices == (10792,)
    assert sleeve_result.region.seed_vertex_indices == (6896, 6902, 6904)
    assert len(sleeve_result.region.movable_vertex_indices) == 11
    assert len(sleeve_result.region.affected_face_indices) == 21
    assert sleeve_result.post_metrics is not None
    assert sleeve_result.post_metrics.flipped_faces == 0
    assert sleeve_result.post_metrics.new_zero_area_faces == 0
    assert sleeve_result.post_metrics.below_area_floor == 0
    assert sleeve_result.outside_gate is not None and sleeve_result.outside_gate.passed
