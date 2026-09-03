"""Qualification composition adversarial tests using explicit synthetic authority."""
import copy
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path

import pytest

from workstreams.runtime14.tests.test_provenance import api, fixture, sha


@pytest.fixture
def qualification():
    try:
        return importlib.import_module('workstreams.runtime14.qualification')
    except ModuleNotFoundError:
        pytest.fail('Separate R1 qualification composer is missing')


@pytest.fixture
def qualified_case(api, fixture, qualification, monkeypatch):
    verified = api.verify_lineage_inputs(fixture.config)
    stage = api.compose_runtime_stage(verified, fixture.output)
    delta = fixture.output.parent.parent/'delta'
    name = 'Mods/ClothMorphRuntime/ScriptExtender/Lua/BootstrapServer.lua'
    path = delta/name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'qualified')
    contract = {'schema': 1, 'revision': 'SYNTHETIC_TEST', 'files': [
        {'path': name, 'bytes': 9, 'sha256': sha(b'qualified')}], 'allowedPaths': [name]}
    monkeypatch.setattr(qualification, '_load_contract', lambda: copy.deepcopy(contract))
    monkeypatch.setattr(qualification, '_DELTA_ROOT', delta)
    monkeypatch.setattr(qualification, '_OUTPUT_ROOT', fixture.output.parent/'qualified')
    return verified, stage, delta, contract, fixture.output.parent/'qualified'/'one'


def test_qualification_preserves_verified_base_and_uses_only_new_delta(qualification, qualified_case):
    verified, stage, delta, contract, output = qualified_case
    result = qualification.compose_qualified_stage(verified, stage, output)
    assert (output/'Public/protected.lsf').read_bytes() == b'protected'
    assert (output/contract['allowedPaths'][0]).read_bytes() == b'qualified'
    assert (Path(stage.output)/contract['allowedPaths'][0]).read_bytes() == b'new'
    assert result.revision == 'SYNTHETIC_TEST'
    assert result.base_manifest == stage


@pytest.mark.parametrize('drift', ['base-bytes','base-receipt','base-label','delta-bytes','unknown-path','forged-receipt'])
def test_qualification_rejects_drift_before_destination_creation(qualification, qualified_case, drift):
    verified, stage, delta, contract, output = qualified_case
    if drift == 'base-bytes': (Path(stage.output)/'Public/protected.lsf').write_bytes(b'bad')
    if drift == 'base-receipt': stage = replace(stage, files=())
    if drift == 'base-label': stage = replace(stage, lineage='R1_TRUST_ME')
    if drift == 'delta-bytes': (delta/contract['allowedPaths'][0]).write_bytes(b'bad')
    if drift == 'unknown-path': (delta/'Cleanup.lua').write_bytes(b'no')
    if drift == 'forged-receipt': verified = replace(verified, lineage='TRUST_ME')
    with pytest.raises(ValueError): qualification.compose_qualified_stage(verified,stage,output)
    assert not output.exists()


@pytest.mark.parametrize('target', ['existing','outside','input'])
def test_qualification_refuses_unsafe_or_nonexclusive_output(qualification, qualified_case, target):
    verified, stage, delta, contract, output = qualified_case
    if target == 'existing': output.mkdir(parents=True)
    if target == 'outside': output = output.parent.parent.parent/'outside'
    if target == 'input': output = Path(stage.output)
    with pytest.raises(ValueError): qualification.compose_qualified_stage(verified, stage, output)


def test_unknown_override_cannot_be_self_authorized_in_contract(qualification, qualified_case):
    verified, stage, delta, contract, output = qualified_case
    name = 'Public/protected.lsf'
    path = delta/name
    path.parent.mkdir(parents=True)
    path.write_bytes(b'danger')
    contract['allowedPaths'].append(name)
    contract['files'].append({'path':name,'bytes':6,'sha256':sha(b'danger')})
    with pytest.raises(ValueError): qualification.compose_qualified_stage(verified,stage,output)
    assert not output.exists()


def test_read_only_hardlinked_input_is_verified_not_treated_as_unique_ownership(api, fixture):
    source=fixture.roots['r0']/'Public/protected.lsf'
    alias=fixture.output.parent.parent/'linked-original'
    os.link(source,alias)
    receipt=api.verify_lineage_inputs(fixture.config)
    assert receipt.lineage=='SYNTHETIC_TEST'
    alias.write_bytes(b'changed through another hard link')
    with pytest.raises(ValueError): api.compose_runtime_stage(receipt,fixture.output)
    assert not fixture.output.exists()


def test_adapted_harness_manifest_binds_current_bytes_separately_from_historical_pins():
    root=Path(__file__).resolve().parents[1]
    manifest=root/'contracts/adapted_harnesses.json'
    assert manifest.exists(),'Current adapted-harness manifest is missing'
    contract=json.loads(manifest.read_text())
    assert contract['kind']=='CURRENT_ADAPTED_HARNESSES_NOT_HISTORICAL_SOURCE'
    assert {row['path'] for row in contract['files']}=={
        'tests/lua/bootstrap_fixture.lua','tests/lua/run_task2a.lua',
        'tests/lua/test_bootstrap_wiring.lua','tests/lua/test_support.lua',
        'tests/lua/test_task2b_bootstrap.lua'}
    for row in contract['files']:
        data=(root/row['path']).read_bytes()
        assert len(data)==row['bytes']
        assert sha(data)==row['sha256']


@pytest.mark.parametrize('change_protected',[False,True])
def test_allowed_lua_override_cannot_reauthorize_embedded_protected_maps(api,fixture,qualification,monkeypatch,change_protected):
    name='Mods/ClothMorphRuntime/ScriptExtender/Lua/EquipRace.lua'
    data=b'M.MINTED = {\n    key = "minted"\n}\nM.KNOWN_ORIG = {\n    key = "original"\n}\nlocal PARENT = {\n    key = "parent"\n}\nM.REFIT_BY_VR = {\n    protected = "target"\n}\n'
    fixture.base[name]=data
    (fixture.roots['r0']/name).write_bytes(data)
    fixture.contract['r0'].append({'path':name,'bytes':len(data),'sha256':sha(data)})
    verified=api.verify_lineage_inputs(fixture.config)
    stage=api.compose_runtime_stage(verified,fixture.output)
    delta=fixture.output.parent.parent/'protected-delta'
    target=delta/name;target.parent.mkdir(parents=True)
    candidate=b'local qualified_control = true\n'+data
    if change_protected: candidate=candidate.replace(b'protected = "target"',b'protected = "different"')
    target.write_bytes(candidate)
    contract={'schema':1,'revision':'SYNTHETIC_TEST','allowedPaths':[name],
              'files':[{'path':name,'bytes':len(candidate),'sha256':sha(candidate)}]}
    monkeypatch.setattr(qualification,'_load_contract',lambda:contract)
    monkeypatch.setattr(qualification,'_DELTA_ROOT',delta)
    monkeypatch.setattr(qualification,'_OUTPUT_ROOT',fixture.output.parent/'qualified')
    output=fixture.output.parent/'qualified'/'protected-check'
    if change_protected:
        with pytest.raises(ValueError,match='[Ee]mbedded'): qualification.compose_qualified_stage(verified,stage,output)
        assert not output.exists()
    else:
        assert qualification.compose_qualified_stage(verified,stage,output).revision=='SYNTHETIC_TEST'
