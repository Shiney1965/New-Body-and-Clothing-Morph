"""Opt-in real source qualification. No local files are opened at import time."""
from dataclasses import asdict
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
    verified=verify_lineage_inputs(config['inputs'])
    suffix=uuid4().hex
    base=compose_runtime_stage(verified,ROOT/'local/stages'/('qualification-base-'+suffix))
    qualified=compose_qualified_stage(verified,base,ROOT/'local/stages/qualified'/suffix)
    lua=os.environ.get('CLOTHMORPH_LUA') or shutil.which('lua')
    assert lua,'Explicit real-source tests require a Lua executable'
    results=[]
    for script in ('test_r1_production.lua','test_r1_schema.lua','test_r1_client.lua','test_r1_master_journals.lua','test_r1_debug.lua'):
        proc=subprocess.run([lua,str(ROOT/'tests/lua'/script),qualified.output],capture_output=True,text=True,timeout=60)
        results.append({'script':script,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    # Keep failed evidence as well; a report is not acceptance.
    report=Path(qualified.output).with_suffix('.evidence.json')
    with report.open('x') as stream:
        json.dump({'qualification':asdict(qualified),'results':results,
                   'task2':'IN_PROGRESS','gameplay':'NOT_RUN'},stream,indent=2)
    for result in results:
        assert result['exit_code']==0,result['stdout']+result['stderr']
        assert result['stderr']==''
    for row in qualified.files:
        if row.path.endswith('.lua'):
            expression='assert(loadfile('+json.dumps((Path(qualified.output)/row.path).as_posix())+'))'
            proc=subprocess.run([lua,'-e',expression],capture_output=True,text=True,timeout=60)
            assert proc.returncode==0,proc.stdout+proc.stderr


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
