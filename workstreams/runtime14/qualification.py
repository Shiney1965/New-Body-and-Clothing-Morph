"""Exclusive qualified-stage composition; historical R0/R1 trust is immutable.

The revisioned delta is project-owned source, never a replacement trust root for
historical inputs. Both the supplied stage receipt and all actual inputs are
reverified before and after copying. No PAK or external state is written.
"""
from dataclasses import dataclass
import json
from pathlib import Path

from . import provenance as base

_ROOT = Path(__file__).parent
_DELTA_ROOT = _ROOT/'runtime/r1_qualified_delta'
_OUTPUT_ROOT = _ROOT/'local/stages/qualified'
_LUA_ROOT = 'Mods/ClothMorphRuntime/ScriptExtender/Lua/'
_ALLOWED = frozenset(_LUA_ROOT+name+'.lua' for name in (
    'BootstrapServer', 'BootstrapClient', 'Shared', 'StateSchema7',
    'MasterState', 'OwnershipLedger', 'R1Foundation', 'ProviderRegistry',
    'MCMIntegration', 'EquipRace', 'BodyFamilyRegistry', 'BodyFamilyEquipRace',
    'PassThroughState')) | {'Mods/ClothMorphRuntime/MCM_blueprint.json'}


@dataclass(frozen=True)
class QualifiedStage:
    revision: str
    qualification_contract_sha256: str
    base_manifest: base.StageManifest
    output: str
    files: tuple[base.FileRecord, ...]


def _load_contract():
    return json.loads((_ROOT/'contracts/r1_qualified_allowed_delta.json').read_bytes())


def _verified_delta():
    contract = _load_contract()
    if set(contract) != {'schema','revision','files','allowedPaths'} or contract['schema'] != 1:
        raise base.LineageError('Invalid qualification contract')
    if not isinstance(contract['revision'], str) or not contract['revision']:
        raise base.LineageError('Missing qualification revision')
    rows = base._records(contract['files'])
    names = [row.path for row in rows]
    if sorted(contract['allowedPaths']) != names or not set(names) <= _ALLOWED:
        raise base.LineageError('Unknown/protected qualification override')
    if base._scan(_DELTA_ROOT) != rows:
        raise base.LineageError('Qualification source bytes/path set drift')
    digest = base._digest(json.dumps(contract, sort_keys=True,separators=(',',':')).encode())
    return contract['revision'], digest, rows


def _verify_stage(verified, stage):
    if type(verified) is not base.VerifiedLineage or type(stage) is not base.StageManifest:
        raise base.LineageError('Exact lineage and stage receipts required')
    fresh = base.verify_lineage_inputs(dict(verified.config))
    if fresh != verified:
        raise base.LineageError('Forged/stale lineage receipt')
    chosen = {row.path:row for row in fresh.r0}
    chosen.update({row.path:row for row in fresh.r1})
    rows = tuple(chosen[name] for name in sorted(chosen))
    expected = base.StageManifest(fresh.lineage,fresh.contract_sha256,
                                 fresh.package_sha256,stage.output,rows)
    if stage != expected or base._scan(Path(stage.output)) != rows:
        raise base.LineageError('Modified base stage or receipt')
    stage_root = base._STAGE_ROOT.absolute().resolve()
    stage_path = Path(stage.output)
    if not stage_path.is_absolute() or '..' in stage_path.parts or stage_root not in stage_path.resolve().parents:
        raise base.LineageError('Base stage outside isolated stage root')
    return rows


def compose_qualified_stage(verified, stage, output):
    rows = _verify_stage(verified, stage)
    revision, contract_digest, delta = _verified_delta()
    output = Path(output)
    if not output.is_absolute() or '..' in output.parts:
        raise base.LineageError('Explicit non-traversing output required')
    base._no_links(output)
    base._no_links(_OUTPUT_ROOT)
    resolved, root = output.resolve(), _OUTPUT_ROOT.absolute().resolve()
    if root not in resolved.parents or output.exists():
        raise base.LineageError('New exclusive qualified destination required')
    for source in [Path(stage.output),_DELTA_ROOT.absolute(),
                   *(Path(value) for _,value in verified.config)]:
        source = source.resolve()
        if source == resolved or source in resolved.parents or resolved in source.parents:
            raise base.LineageError('Qualification output overlaps input')
    chosen = {row.path:(row,Path(stage.output)) for row in rows}
    chosen.update({row.path:(row,_DELTA_ROOT) for row in delta})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(exist_ok=False)
    for name,(row,source_root) in sorted(chosen.items()):
        source = source_root/name
        base._no_links(source)
        data = source.read_bytes()
        if len(data) != row.bytes or base._digest(data) != row.sha256:
            raise base.LineageError('Input changed; partial output retained unaccepted')
        target = output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        base._no_links(target)
        with target.open('xb') as stream:
            stream.write(data)
    expected = tuple(row for _,(row,_) in sorted(chosen.items()))
    if base._scan(output) != expected or _verify_stage(verified,stage) != rows or _verified_delta() != (revision,contract_digest,delta):
        raise base.LineageError('Readback/input drift; partial output retained unaccepted')
    return QualifiedStage(revision,contract_digest,stage,str(output),expected)
