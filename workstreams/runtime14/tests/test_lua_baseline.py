"""Real R1 source with explicitly documented synthetic engine/R0 boundaries."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
LUA = os.environ.get('CLOTHMORPH_LUA') or shutil.which('lua')


def test_checked_in_overlay_is_the_exact_pure_r1_reference():
    contract=json.loads((ROOT/'contracts/lineage.json').read_text())
    overlay=ROOT/'runtime/r1_foundation'
    expected={r['path']:r for r in contract['r1']}
    actual={p.relative_to(overlay).as_posix():p for p in overlay.rglob('*') if p.is_file()}
    assert set(actual)==set(expected)
    for name,path in actual.items():
        data=path.read_bytes()
        assert len(data)==expected[name]['bytes']
        assert hashlib.sha256(data).hexdigest().upper()==expected[name]['sha256']


@pytest.mark.parametrize('script,marker', [
    ('run_task2a.lua','TASK2A_LUA_PASS 13/13'),
    ('test_bootstrap_wiring.lua','TASK2A_BOOTSTRAP_RED_GREEN 26/26'),
    ('test_task2b_bootstrap.lua','TASK2B_BOOTSTRAP_RED_GREEN 15/15'),
])
def test_actual_r1_lua_harness(script,marker):
    if not LUA: pytest.skip('Set CLOTHMORPH_LUA to a Lua 5.4 executable')
    test_checked_in_overlay_is_the_exact_pure_r1_reference()
    result=subprocess.run([LUA,str(ROOT/'tests/lua'/script),str(ROOT/'runtime/r1_foundation')],
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stderr==''
    assert marker in result.stdout
    test_checked_in_overlay_is_the_exact_pure_r1_reference()


def test_missing_explicit_source_root_refuses_harness():
    if not LUA: pytest.skip('Set CLOTHMORPH_LUA')
    result=subprocess.run([LUA,str(ROOT/'tests/lua/run_task2a.lua')],capture_output=True,text=True)
    assert result.returncode!=0
    assert 'explicit Runtime source root required' in result.stderr


def test_genuine_accepted_bootstrap_api_controls():
    contract=json.loads((ROOT/'contracts/accepted_tiefling.json').read_text())
    bootstrap=ROOT/'runtime/r0_reference/accepted_tiefling_bootstrap.lua'
    assert hashlib.sha256(bootstrap.read_bytes()).hexdigest().upper()==contract['bootstrapSha256']
    if not LUA: pytest.skip('Set CLOTHMORPH_LUA')
    result=subprocess.run([LUA,str(ROOT/'tests/lua/accepted_provider_controls.lua'),str(bootstrap)],
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stderr==''
    assert 'api=1 calls=3 sequence=body,refits,reapply warnings=0' in result.stdout
    assert 'api=2 calls=0 sequence= warnings=1' in result.stdout


def test_decoded_provider_definition_does_not_supply_external_mesh():
    # Portable metadata evidence, not synthetic mesh availability or gameplay.
    contract=json.loads((ROOT/'contracts/accepted_tiefling.json').read_text())
    assert contract['bcbSourceFile']=='Generated/Public/BCBPak/Assets/Characters/_Models/Tieflings/_Female/Resources/TIF_F_NKD_Body_A.GR2'
    assert contract['bcbVisualUuid']=='eab8e30e-0207-58d8-8764-e3b4477133fa'
    assert contract['bcbSourceFile'] not in {row['path'] for row in contract['files']}
    base=json.loads((ROOT/'contracts/lineage.json').read_text())
    assert contract['bcbSourceFile'] not in {row['path'] for row in base['r0']}
