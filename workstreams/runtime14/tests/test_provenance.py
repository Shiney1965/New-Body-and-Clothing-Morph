"""Portable synthetic fixtures exercise verification, never attest the real R0."""
import copy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


@pytest.fixture
def api():
    try:
        module = importlib.import_module('workstreams.runtime14.provenance')
    except ModuleNotFoundError:
        pytest.fail('Task 1 lineage verifier is not implemented')
    return module


@pytest.fixture
def fixture(tmp_path, monkeypatch, api):
    base = {'Public/protected.lsf': b'protected',
            'Mods/ClothMorphRuntime/ScriptExtender/Lua/BootstrapServer.lua': b'old'}
    overlay = {'Mods/ClothMorphRuntime/ScriptExtender/Lua/BootstrapServer.lua': b'new',
               'Mods/ClothMorphRuntime/ScriptExtender/Lua/MasterState.lua': b'foundation'}
    roots = {key: tmp_path / key for key in ('r0', 'r1')}
    for key, files in [('r0', base), ('r1', overlay)]:
        for name, data in files.items():
            path = roots[key] / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    pak = tmp_path / 'synthetic.pak'
    pak.write_bytes(b'SYNTHETIC_PACKAGE_NOT_BG3')
    tool = tmp_path / 'synthetic-list-tool'
    tool.write_bytes(b'SYNTHETIC_TOOL_NOT_EXECUTED')
    contract = {'lineage': 'SYNTHETIC_TEST', 'package': {'bytes': pak.stat().st_size,
        'sha256': sha(pak.read_bytes())}, 'divineSha256': sha(tool.read_bytes()),
        'r0': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n,b in base.items()],
        'r1': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n,b in overlay.items()]}
    monkeypatch.setattr(api, '_load_contract', lambda: copy.deepcopy(contract))
    monkeypatch.setattr(api, '_list_package', lambda *_: [(n,len(b)) for n,b in base.items()])
    monkeypatch.setattr(api, '_STAGE_ROOT', tmp_path / 'stages')
    config = {'r0_package': str(pak), 'r0_root': str(roots['r0']),
              'r1_root': str(roots['r1']), 'divine': str(tool)}
    return SimpleNamespace(config=config, base=base, overlay=overlay, contract=contract,
                           roots=roots, output=tmp_path/'stages'/'test')


def test_verified_composition_preserves_protected_bytes_and_exact_overlay(api, fixture):
    verified = api.verify_lineage_inputs(fixture.config)
    stage = api.compose_runtime_stage(verified, fixture.output)
    assert stage.lineage == 'SYNTHETIC_TEST'
    assert (fixture.output/'Public/protected.lsf').read_bytes() == b'protected'
    assert (fixture.output/'Mods/ClothMorphRuntime/ScriptExtender/Lua/BootstrapServer.lua').read_bytes() == b'new'
    assert len(stage.files) == 3
    assert {x.path for x in stage.files} == set(fixture.base) | set(fixture.overlay)


@pytest.mark.parametrize('field', ['r0_package', 'divine'])
def test_wrong_package_or_tool_bytes_rejected(api, fixture, field):
    Path(fixture.config[field]).write_bytes(b'wrong')
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


@pytest.mark.parametrize('key,path,data', [
    ('r0','Public/protected.lsf',b'changed protected'),
    ('r1','Mods/ClothMorphRuntime/ScriptExtender/Lua/BootstrapServer.lua',b'CleanupApiVersion=1'),
    ('r1','Mods/ClothMorphRuntime/ScriptExtender/Lua/Cleanup.lua',b'cleanup'),
    ('r0','Public/extra.lsf',b'extra'),
])
def test_altered_protected_overlay_or_extra_file_rejected(api, fixture, key,path,data):
    (fixture.roots[key]/path).write_bytes(data)
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


def test_missing_overlay_rejected(api, fixture):
    (fixture.roots['r1']/next(iter(fixture.overlay))).unlink()
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


@pytest.mark.parametrize('path',['../escape','/absolute','C:/absolute','a\\b','a/../b',
    'Public/CON.txt','Public/file:stream','Public/trailing.','Public//empty'])
def test_unsafe_listing_rejected(api, fixture, monkeypatch,path):
    monkeypatch.setattr(api, '_list_package', lambda *_:[(path,1)])
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


def test_casefold_duplicate_listing_rejected(api, fixture, monkeypatch):
    monkeypatch.setattr(api,'_list_package',lambda *_:[('Public/x',1),('PUBLIC/X',1)])
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


@pytest.mark.parametrize('extra', [{'package_sha256':'anything'}, {'verified': True},
                                   {'lineage':'R0_CURRENT_BASELINE'}])
def test_caller_cannot_relabel_or_override_authority(api,fixture,extra):
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config|extra)


def test_listing_missing_or_size_mismatch_rejected(api,fixture,monkeypatch):
    monkeypatch.setattr(api,'_list_package',lambda *_:[('Public/protected.lsf',8)])
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


def test_changed_after_verification_fails_before_destination_create(api,fixture):
    verified=api.verify_lineage_inputs(fixture.config)
    (fixture.roots['r0']/'Public/protected.lsf').write_bytes(b'drift')
    with pytest.raises(api.LineageError): api.compose_runtime_stage(verified,fixture.output)
    assert not fixture.output.exists()


@pytest.mark.parametrize('existing', [False,True])
def test_existing_destination_never_reused(api,fixture,existing):
    fixture.output.mkdir(parents=True)
    if existing: (fixture.output/'keep').write_bytes(b'keep')
    verified=api.verify_lineage_inputs(fixture.config)
    with pytest.raises(api.LineageError): api.compose_runtime_stage(verified,fixture.output)
    assert sorted(x.name for x in fixture.output.iterdir()) == (['keep'] if existing else [])


def test_destination_must_be_under_isolated_stage_root(api,fixture):
    verified=api.verify_lineage_inputs(fixture.config)
    with pytest.raises(api.LineageError): api.compose_runtime_stage(verified,fixture.output.parent.parent/'elsewhere')


def test_forged_verified_value_is_not_a_capability(api,fixture):
    with pytest.raises(api.LineageError): api.compose_runtime_stage(SimpleNamespace(config=fixture.config),fixture.output)


def test_symlink_input_rejected_even_if_hash_matches(api,fixture):
    path=fixture.roots['r0']/'Public/protected.lsf'
    real=path.with_name('actual')
    real.write_bytes(path.read_bytes())
    path.unlink()
    try: path.symlink_to(real)
    except OSError: pytest.skip('symlink creation unavailable on this host')
    with pytest.raises(api.LineageError): api.verify_lineage_inputs(fixture.config)


def test_divine_listing_parses_exact_three_column_output(api,monkeypatch):
    monkeypatch.setattr(api.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stderr='',stdout='Public/one.lsf\t17\t0\nMods/test.lua\t2\t0\n'))
    assert api._list_package(Path('tool'),Path('pak'))==[('Public/one.lsf',17),('Mods/test.lua',2)]


@pytest.mark.parametrize('stdout,stderr,code', [
    ('Public/x\t1\t0','warning',0),('Public/x\t1\t0','',1),
    ('Public/x\t1\t0\nunrecognized output','',0),('Public/x\t1\t1','',0),
])
def test_untrusted_divine_listing_failure_refused(api,monkeypatch,stdout,stderr,code):
    monkeypatch.setattr(api.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=code,stderr=stderr,stdout=stdout))
    with pytest.raises(api.LineageError): api._list_package(Path('tool'),Path('pak'))


def test_forged_typed_receipt_cannot_relabel_synthetic_as_actual(api,fixture):
    receipt=api.verify_lineage_inputs(fixture.config)
    forged=replace(receipt,lineage='R0_CURRENT_BASELINE_PLUS_PURE_R1_REFERENCE')
    with pytest.raises(api.LineageError): api.compose_runtime_stage(forged,fixture.output)
    assert not fixture.output.exists()


def test_unreadable_subdirectory_fails_closed(api,fixture,monkeypatch):
    walk=api.os.walk
    def unreadable(*args,**kwargs):
        yield from walk(*args,**kwargs)
        if 'onerror' in kwargs: kwargs['onerror'](PermissionError('denied directory'))
    monkeypatch.setattr(api.os,'walk',unreadable)
    with pytest.raises(api.LineageError,match='Cannot inventory'):
        api.verify_lineage_inputs(fixture.config)


def test_public_import_performs_no_local_file_reads(api,monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Unexpected import-time local read')
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    monkeypatch.setattr(Path,'read_text',forbidden)
    importlib.reload(api)
