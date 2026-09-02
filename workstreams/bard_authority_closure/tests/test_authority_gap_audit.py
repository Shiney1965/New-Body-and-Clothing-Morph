import hashlib
import copy
import json
from pathlib import Path
import struct
from dataclasses import replace

import pytest

from workstreams.bard_authority_closure import authority_gap_audit as audit


def _tiny_glb(path: Path, *, bad_index=False, bad_joint=False):
    positions = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack('<3H', 0, 1, 5 if bad_index else 2)
    joints = bytes([2 if bad_joint else 0, 0, 0, 0] * 3)
    weights = struct.pack('<12f', *([1, 0, 0, 0] * 3))
    matrices = struct.pack('<16f', 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    parts = (positions, indices, joints, weights, matrices)
    binary = b''
    views = []
    for part in parts:
        binary += b'\0' * (-len(binary) % 4)
        views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(part)})
        binary += part
    document = {
        'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(binary)}],
        'bufferViews': views,
        'accessors': [
            {'bufferView': 0, 'count': 3, 'componentType': 5126, 'type': 'VEC3'},
            {'bufferView': 1, 'count': 3, 'componentType': 5123, 'type': 'SCALAR'},
            {'bufferView': 2, 'count': 3, 'componentType': 5121, 'type': 'VEC4'},
            {'bufferView': 3, 'count': 3, 'componentType': 5126, 'type': 'VEC4'},
            {'bufferView': 4, 'count': 1, 'componentType': 5126, 'type': 'MAT4'},
        ],
        'meshes': [{'name': 'Garment', 'primitives': [{'attributes': {'POSITION': 0, 'JOINTS_0': 2, 'WEIGHTS_0': 3}, 'indices': 1, 'material': 0}]}],
        'nodes': [{'name': 'Root'}, {'name': 'GarmentNode', 'mesh': 0, 'skin': 0}],
        'skins': [{'joints': [0], 'inverseBindMatrices': 4}],
        'materials': [{'name': 'Cloth'}],
    }
    encoded = json.dumps(document).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += b'\0' * (-len(binary) % 4)
    raw = struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary))
    raw += struct.pack('<I4s', len(encoded), b'JSON') + encoded
    raw += struct.pack('<I4s', len(binary), b'BIN\0') + binary
    path.write_bytes(raw)
    return indices


def test_inspection_binds_actual_topology_attributes_skin_and_materials(tmp_path):
    source = tmp_path / 'tiny.glb'
    indices = _tiny_glb(source)
    assert hasattr(audit, 'inspect_glb_semantics'), 'semantic inspector missing'
    result = audit.inspect_glb_semantics(source)
    mesh = result['meshes'][0]
    assert mesh['name'] == 'Garment'
    primitive = mesh['primitives'][0]
    assert primitive['vertices'] == 3
    assert primitive['triangles'] == 1
    assert primitive['indices_sha256'] == hashlib.sha256(indices).hexdigest().upper()
    assert primitive['zero_area_triangles'] == 0
    assert set(primitive['attributes']) == {'POSITION', 'JOINTS_0', 'WEIGHTS_0'}
    assert result['skins'][0]['joint_names'] == ['Root']
    assert result['materials'] == [{'name': 'Cloth'}]
    assert result['geometry_method_tested'] is False
    assert result['defect_region'] is None


@pytest.mark.parametrize('fault, expected', [('bad_index', 'INDEX_OUT_OF_RANGE'), ('bad_joint', 'JOINT_OUT_OF_RANGE')])
def test_malformed_semantics_cannot_be_called_complete(tmp_path, fault, expected):
    source = tmp_path / 'invalid.glb'
    _tiny_glb(source, **{fault: True})
    assert hasattr(audit, 'inspect_glb_semantics'), 'semantic inspector missing'
    with pytest.raises(ValueError, match=expected):
        audit.inspect_glb_semantics(source)


def test_listing_audit_accounts_for_all_entries_and_rejects_extra_files(tmp_path):
    (tmp_path / 'a.txt').write_bytes(b'one')
    (tmp_path / 'b.txt').write_bytes(b'two')
    assert hasattr(audit, 'inventory_against_listing'), 'complete inventory verifier missing'
    result = audit.inventory_against_listing(tmp_path, 'a.txt\t3\t0\nb.txt\t3\t0\n')
    assert [record['path'] for record in result] == ['a.txt', 'b.txt']
    (tmp_path / 'extra.txt').write_bytes(b'x')
    with pytest.raises(ValueError, match='LISTING_INVENTORY_MISMATCH'):
        audit.inventory_against_listing(tmp_path, 'a.txt\t3\t0\nb.txt\t3\t0\n')


def test_source_audit_completion_never_implies_geometry_exhaustion_or_admission():
    assert hasattr(audit, 'source_audit_disposition'), 'source/geometry state separation missing'
    gaps = [{'gap_id': f'{number:02}', 'status': 'RESOLVED_SOURCE_EVIDENCE'} for number in range(1, 12)]
    result = audit.source_audit_disposition(gaps)
    assert result['status'] == 'SOURCE_AUDIT_COMPLETE_GEOMETRY_UNASSESSED'
    assert result['geometry_admitted'] is False
    assert result['geometry_methods_tested'] == []
    assert result['exclusion_event_input'] is None
    assert result['release_blocking'] is True
    assert audit.source_audit_disposition(gaps[:-1])['status'] == 'BLOCKED_SOURCE_AUDIT_INCOMPLETE'
    assert audit.source_audit_disposition(gaps + [gaps[0]])['status'] == 'BLOCKED_SOURCE_AUDIT_INCOMPLETE'


def test_direct_gr2_binding_readback_does_not_confuse_slots_with_meshes():
    assert hasattr(audit, 'inspect_gr2_bindings'), 'direct GR2 binding inspector missing'
    source = Path('C:/Claude Projects/BG3 Mods/New-Body-and-Clothing-Morph/.worktrees/clothmorph-everything-else-release/workstreams/release_master_ledger/local/source_pak_freeze_20260902/extracted/Scantily/Generated/Public/SCO/Assets/HFL_F_ARM_Authority_Robe.GR2')
    result = audit.inspect_gr2_bindings(source, '36FCF4E18ED7B85FA7759129DFA700E80B0138F73F26B0FE76AD99B69FA5CF42')
    assert result['mesh_count'] == 9
    assert result['models'][0]['mesh_binding_indices'] == list(range(9))
    assert result['material_count'] == 0
    assert result['meshes'][8]['name'] == 'HUM_M_ARM_Gortash_Stone_Mesh'
    assert len(result['skeletons'][0]['bones']) == 82
    assert result['source_sha256'] == '36FCF4E18ED7B85FA7759129DFA700E80B0138F73F26B0FE76AD99B69FA5CF42'


def test_direct_gr2_reader_refuses_unpinned_bytes(tmp_path):
    source = tmp_path / 'fake.gr2'
    source.write_bytes(b'not the source')
    assert hasattr(audit, 'inspect_gr2_bindings'), 'direct GR2 binding inspector missing'
    with pytest.raises(ValueError, match='GR2_SOURCE_HASH_MISMATCH'):
        audit.inspect_gr2_bindings(source, '0' * 64)


def test_current_eleven_gap_audit_resolves_sources_without_claiming_geometry():
    assert hasattr(audit, 'build_current_gap_audit'), 'eleven-gap evidence builder missing'
    result = audit.build_current_gap_audit()
    assert result['status'] == 'SOURCE_AUDIT_COMPLETE_GEOMETRY_UNASSESSED'
    assert result['geometry_admitted'] is False
    assert result['defect_region'] is None
    assert result['exclusion_event_input'] is None
    assert [gap['gap_id'] for gap in result['gaps']] == [f'{number:02}' for number in range(1, 12)]
    assert [result['packages'][name]['file_count'] for name in ('addon', 'separator', 'sbbf')] == [71, 630, 16]
    assert result['legacy']['inventory_source_count'] == 63
    assert result['legacy']['stats_byte_identical_to_frozen'] is True
    assert result['legacy']['visual_records_identical_to_packed'] is True
    assert result['legacy']['visual_record_count'] == 828
    assert {name: result['geometry'][name]['gr2']['mesh_count'] for name in (
        'HFL_F_ARM_Authority_Robe', 'HFL_F_ARM_Authority_Robe_Alt',
        'TIF_FS_ARM_Authority_Robe', 'TIF_FS_ARM_Authority_Robe_Alt')} == {
        'HFL_F_ARM_Authority_Robe': 9, 'HFL_F_ARM_Authority_Robe_Alt': 10,
        'TIF_FS_ARM_Authority_Robe': 9, 'TIF_FS_ARM_Authority_Robe_Alt': 10}
    assert result['geometry']['bcbscantily_main_gr2']['gr2']['mesh_count'] == 8
    assert result['geometry']['bcbscantily_main_gr2']['visual_object_slot_count'] == 9
    assert result['routes']['bcb_overlay_human']['normal'] != result['routes']['bcb_overlay_human']['alt']
    assert result['routes']['raw_sco_human']['alt'] != result['routes']['bcb_overlay_human']['alt']
    assert all(gap['evidence'] for gap in result['gaps'])


def test_gap_report_writer_refuses_overwrite_and_keeps_nonattachable_state(tmp_path):
    assert hasattr(audit, 'write_current_gap_audit'), 'bounded audit writer missing'
    first = audit.write_current_gap_audit(tmp_path / 'first')
    second = audit.write_current_gap_audit(tmp_path / 'second')
    assert first.read_bytes() == second.read_bytes()
    result = json.loads(first.read_bytes())
    assert result['ready_for_attachment'] is False
    assert result['release_blocking'] is True
    assert not {'event_id', 'record_id', 'source_profile_id', 'approved_by'} & result.keys()
    with pytest.raises(FileExistsError):
        audit.write_current_gap_audit(tmp_path / 'first')


def test_gap_scope_cannot_replace_a_retained_file_with_an_unreviewed_file(tmp_path):
    from workstreams.bard_authority_closure.authority_contracts import load_current_authority_snapshot
    snapshot = load_current_authority_snapshot(include_gap_audit=False)
    unrelated = tmp_path / 'unreviewed.txt'
    unrelated.write_text('not a reviewed retained source', encoding='utf-8')
    changed = (*snapshot.unresolved_retained_evidence_files[:-1], str(unrelated))
    with pytest.raises(ValueError, match='GAP_ORIGINAL_SET_CHANGED'):
        audit.build_current_gap_audit(replace(snapshot, unresolved_retained_evidence_files=changed))


def test_resolver_rejects_numbered_fake_gaps_pointing_to_one_unrelated_code_file():
    from workstreams.bard_authority_closure import authority_contracts as contracts
    base = contracts.load_current_authority_snapshot(include_gap_audit=False)
    unrelated = Path(contracts.__file__).resolve()
    forged = {
        'status': 'SOURCE_AUDIT_COMPLETE_GEOMETRY_UNASSESSED',
        'source_audit_complete': False, 'defect_region': {'invented': True},
        'geometry_admitted': False, 'geometry_methods_tested': [], 'exclusion_event_input': None,
        'gaps': [{'gap_id': f'{number:02}', 'status': 'RESOLVED_SOURCE_EVIDENCE',
                  'path': str(unrelated), 'evidence': {'source_sha256': audit.sha256_file(unrelated)}}
                 for number in range(1, 12)],
    }
    with pytest.raises(contracts.ContractAdmissionError, match='AUTHORITY_GAP_AUDIT_'):
        contracts.resolve_authority_contract(replace(base, unresolved_retained_evidence_files=(), source_gap_audit=forged))


@pytest.fixture(scope='module')
def genuine_gap_snapshot():
    from workstreams.bard_authority_closure.authority_contracts import load_current_authority_snapshot
    return load_current_authority_snapshot(include_gap_audit=True)


@pytest.mark.parametrize('mutation', (
    'duplicate_unrelated_paths', 'missing_geometry', 'missing_conversions',
    'altered_manifest', 'altered_semantics', 'altered_source_binding',
    'contradictory_status', 'false_complete', 'invented_defect', 'altered_frozen_source',
))
def test_resolver_reconstructs_full_production_audit_not_just_gap_hashes(genuine_gap_snapshot, mutation):
    from workstreams.bard_authority_closure import authority_contracts as contracts
    forged = copy.deepcopy(genuine_gap_snapshot.source_gap_audit)
    if mutation == 'duplicate_unrelated_paths':
        unrelated = Path(contracts.__file__).resolve()
        for gap in forged['gaps']:
            gap['path'] = str(unrelated)
            gap['evidence']['source_sha256'] = audit.sha256_file(unrelated)
    elif mutation == 'missing_geometry':
        del forged['geometry']
    elif mutation == 'missing_conversions':
        del forged['conversions']
    elif mutation == 'altered_manifest':
        forged['packages']['addon']['manifest'][0]['sha256'] = '0' * 64
    elif mutation == 'altered_semantics':
        forged['geometry']['HFL_F_ARM_Authority_Robe']['gr2']['mesh_count'] = 999
    elif mutation == 'altered_source_binding':
        forged['routes']['raw_sco_human']['alt'] = ['invented-source-visual']
    elif mutation == 'contradictory_status':
        forged['status'] = 'BLOCKED_SOURCE_AUDIT_INCOMPLETE'
    elif mutation == 'false_complete':
        forged['source_audit_complete'] = False
    elif mutation == 'invented_defect':
        forged['defect_region'] = {'invented': True}
    elif mutation == 'altered_frozen_source':
        forged['fresh_source_pak_sha256'] = '0' * 64
    with pytest.raises(contracts.ContractAdmissionError, match='AUTHORITY_GAP_AUDIT_'):
        contracts.resolve_authority_contract(replace(genuine_gap_snapshot, source_gap_audit=forged))


def test_resolver_still_accepts_genuine_reconstructed_source_audit(genuine_gap_snapshot):
    from workstreams.bard_authority_closure.authority_contracts import resolve_authority_contract
    result = resolve_authority_contract(genuine_gap_snapshot)
    assert result.status == 'SOURCE_AUDIT_COMPLETE_GEOMETRY_UNASSESSED'
    assert result.geometry_admitted is False
    assert result.exclusion_event_input is None
