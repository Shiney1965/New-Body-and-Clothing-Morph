"""Opt-in real source qualification. No local files are opened at import time."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest

from workstreams.runtime14.provenance import verify_lineage_inputs, compose_runtime_stage
from workstreams.runtime14.qualification import compose_qualified_stage

ROOT=Path(__file__).resolve().parents[1]
CONFIG=os.environ.get('CLOTHMORPH_RUNTIME14_INPUTS')
pytestmark=pytest.mark.skipif(not CONFIG,reason='Qualified real-source tests require explicit CLOTHMORPH_RUNTIME14_INPUTS')


def test_actual_qualified_stage_executes_production_modules_and_schema():
    config=json.loads(Path(CONFIG).read_text())
    scripts=('test_r1_production.lua','test_r1_schema.lua','test_r1_client.lua',
             'test_r1_master_journals.lua','test_r1_debug.lua','test_r1_registration.lua',
             'test_r1_mutator_inventory.lua','test_r1_failure_matrix.lua','test_r1_event_matrix.lua',
             'test_r1_master_resume.lua','test_r1_diagnostics.lua','test_r1_managed_regression.lua',
             'test_r1_external_legacy.lua','test_r1_native_visual_timing.lua',
             'test_r1_pending_refresh.lua')
    # Freeze executable harness bytes before the slow complete source scan. A
    # concurrent editor cannot silently change the test while its stage builds.
    suffix=uuid4().hex
    harness_root=ROOT/'local/harnesses'/suffix
    source_files=[ROOT/'tests/lua'/name for name in ('production_engine.lua',*scripts)]
    source_files.append(ROOT/'runtime/r0_reference/accepted_tiefling_bootstrap.lua')
    source_files.extend(ROOT/'runtime/r0_reference/recluse'/name for name in ('BootstrapServer.lua','RefitMaps.lua'))
    receipts=[]
    for source in source_files:
        data=source.read_bytes()
        relative=source.relative_to(ROOT)
        target=harness_root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream: stream.write(data)
        receipts.append({'path':relative.as_posix(),'bytes':len(data),
                         'sha256':hashlib.sha256(data).hexdigest().upper()})
    runner_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper()
    verified=verify_lineage_inputs(config['inputs'])
    base=compose_runtime_stage(verified,ROOT/'local/stages'/('qualification-base-'+suffix))
    qualified=compose_qualified_stage(verified,base,ROOT/'local/stages/qualified'/suffix)
    lua=os.environ.get('CLOTHMORPH_LUA') or shutil.which('lua')
    assert lua,'Explicit real-source tests require a Lua executable'
    results=[]
    for script in scripts:
        proc=subprocess.run([lua,str(harness_root/'tests/lua'/script),qualified.output],capture_output=True,text=True,timeout=60)
        results.append({'script':script,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    syntax=[]
    for row in qualified.files:
        if row.path.endswith('.lua'):
            expression='assert(loadfile('+json.dumps((Path(qualified.output)/row.path).as_posix())+'))'
            proc=subprocess.run([lua,'-e',expression],capture_output=True,text=True,timeout=60)
            syntax.append({'path':row.path,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    drifted=[]
    for row in receipts:
        for check_root in (ROOT,harness_root):
            data=(check_root/row['path']).read_bytes()
            if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest().upper()!=row['sha256']:
                drifted.append(str(check_root/row['path']))
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper()!=runner_hash:
        drifted.append(str(Path(__file__)))
    # Keep failed evidence as well; a report is not acceptance.
    report=Path(qualified.output).with_suffix('.evidence.json')
    with report.open('x') as stream:
        json.dump({'qualification':asdict(qualified),'results':results,'syntax':syntax,'harnesses':receipts,
                   'runnerSha256':runner_hash,'harnessDrift':drifted,
                   'task2':'IN_PROGRESS','gameplay':'NOT_RUN'},stream,indent=2)
    assert not drifted,'Harness changed during verification: '+repr(drifted)
    for result in (*syntax,*results):
        assert result['exit_code']==0,result['stdout']+result['stderr']
        assert result['stderr']==''


def test_r0_embedded_refit_map_bytes_are_unchanged_in_qualification():
    config=json.loads(Path(CONFIG).read_text())
    verify_lineage_inputs(config['inputs'])
    name='Mods/ClothMorphRuntime/ScriptExtender/Lua/EquipRace.lua'
    original=(Path(config['inputs']['r0_root'])/name).read_bytes()
    qualified=(ROOT/'runtime/r1_qualified_delta'/name).read_bytes()
    start=b'M.REFIT_BY_VR = {'
    def section(data):
        begin=data.index(start)
        return data[begin:data.index(b'\n}',begin)+2]
    assert section(original)==section(qualified)
