"""Exact user-visible control contract, paired with actual Lua consumer tests."""
import json
from pathlib import Path


def test_mcm_control_schema_exposes_external_without_putting_it_in_managed_cycle():
    root=Path(__file__).resolve().parents[1]
    path=root/'runtime/r1_qualified_delta/Mods/ClothMorphRuntime/MCM_blueprint.json'
    assert path.exists(),'Qualified MCM user controls are missing'
    doc=json.loads(path.read_text())
    controls={setting['Id']:setting for tab in doc['Tabs'] for section in tab['Sections'] for setting in section['Settings']}
    assert controls['body_choice']['Options']['Choices']==['Vanilla','SBBF','BCB','External / Pass-through']
    assert controls['body_choice']['Default']=='Vanilla'
    assert controls['master_enabled']['Name']=='Enable ClothMorph mutations'
    assert controls['master_enabled']['Default'] is True
    assert controls['key_set_external']['Default']=={'Keyboard':{'Key':'NONE','ModifierKeys':[]}}
    assert controls['key_set_external']['Name']=='Set body ownership: External / Pass-through'
