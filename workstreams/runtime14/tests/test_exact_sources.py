"""Explicit opt-in integration; missing configured inputs fail, never skip."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from uuid import uuid4

import pytest

from workstreams.runtime14.provenance import verify_lineage_inputs, compose_runtime_stage

ROOT=Path(__file__).resolve().parents[1]
CONFIG=os.environ.get('CLOTHMORPH_RUNTIME14_INPUTS')
pytestmark=pytest.mark.skipif(not CONFIG,reason='Exact source integration is opt-in; set CLOTHMORPH_RUNTIME14_INPUTS')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


@pytest.fixture(scope='module')
def config():
    return json.loads(Path(CONFIG).read_text())


@pytest.fixture(scope='module')
def verified(config):
    authority=json.loads((ROOT/'contracts/lineage.json').read_text())
    assert digest(config['r0_freeze_manifest'])==authority['evidence']['r0FreezeManifestSha256']
    assert digest(config['r1_copy_manifest'])==authority['evidence']['r1CopyManifestSha256']
    return verify_lineage_inputs(config['inputs'])


def test_actual_frozen_source_composition_and_real_lua(config,verified):
    assert verified.lineage=='R0_CURRENT_BASELINE_PLUS_PURE_R1_REFERENCE'
    assert len(verified.r0)==739
    assert len(verified.r1)==12
    output=Path(config['stage_output']+'-'+uuid4().hex)
    stage=compose_runtime_stage(verified,output)
    r0={row.path:row for row in verified.r0}
    overlay={row.path:row for row in verified.r1}
    assert {row.path:row for row in stage.files}==r0|overlay
    lua=os.environ.get('CLOTHMORPH_LUA') or shutil.which('lua')
    assert lua,'Exact-source verification requires a Lua executable'
    runs=[]
    for script,marker in [('run_task2a.lua','TASK2A_LUA_PASS 13/13'),
                          ('test_bootstrap_wiring.lua','TASK2A_BOOTSTRAP_RED_GREEN 26/26'),
                          ('test_task2b_bootstrap.lua','TASK2B_BOOTSTRAP_RED_GREEN 15/15')]:
        proc=subprocess.run([lua,str(ROOT/'tests/lua'/script),str(output)],capture_output=True,text=True,timeout=60)
        assert proc.returncode==0,proc.stdout+proc.stderr
        assert proc.stderr==''
        assert marker in proc.stdout
        runs.append({'script':script,'stdout':proc.stdout})
    # Evidence is outside the composed package root and created exclusively.
    with output.with_suffix('.manifest.json').open('x') as stream:
        json.dump({'stage':asdict(stage),'harnesses':runs,'gameplay':'NOT_RUN',
                   'fullR1Qualification':'INCOMPLETE_TASK_2'},stream,indent=2)


def test_exact_provider_bootstrap_and_physical_dependency(config,verified):
    contract=json.loads((ROOT/'contracts/accepted_tiefling.json').read_text())
    provider=Path(config['provider_root'])
    assert digest(config['provider_package'])==contract['packageSha256']
    expected={row['path']:row for row in contract['files']}
    actual={p.relative_to(provider).as_posix():p for p in provider.rglob('*') if p.is_file()}
    assert set(actual)==set(expected)
    for name,path in actual.items():
        assert path.stat().st_size==expected[name]['bytes']
        assert digest(path)==expected[name]['sha256']
    assert digest(config['visualbank_readback'])==contract['visualBankReadbackSha256']
    tree=ET.parse(config['visualbank_readback'])
    matched=[]
    for node in tree.iter('node'):
        attributes={item.get('id'):item.get('value') for item in node.findall('attribute')}
        if attributes.get('ID')==contract['bcbVisualUuid']:
            matched.append(attributes['SourceFile'])
    assert matched==[contract['bcbSourceFile']]
    assert matched[0] not in actual
    assert matched[0] not in {row.path for row in verified.r0}
    # Definition ownership is not physical closure, without inferring active load order.
    assert contract['bcbSourceFile'].startswith('Generated/Public/BCBPak/')
    lua=os.environ.get('CLOTHMORPH_LUA') or shutil.which('lua')
    assert lua
    proc=subprocess.run([lua,str(ROOT/'tests/lua/accepted_provider_controls.lua'),
                         str(provider/contract['bootstrapPath'])],capture_output=True,text=True,timeout=60)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert 'ACCEPTED_PROVIDER_API_GUARD_REPRODUCED' in proc.stdout
    assert digest(config['provider_package'])==contract['packageSha256']
