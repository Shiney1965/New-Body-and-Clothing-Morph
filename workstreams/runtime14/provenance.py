"""Read-only pinned lineage verification and exclusive offline composition.

Only local paths are configurable. Trust roots and the complete package/overlay
inventories are repository-owned. Verified objects are receipts, not capabilities:
composition repeats verification and checks every copied byte before returning.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess


class LineageError(ValueError):
    pass


_STAGE_ROOT = Path(__file__).parent / 'local' / 'stages'
_CONTRACT_SHA256 = '48B6AA013666E00B720909B2139D66820AF6C739F640CAD8561F2E697FCE665F'
_CONFIG_KEYS = {'r0_package', 'r0_root', 'r1_root', 'divine'}


@dataclass(frozen=True)
class FileRecord:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class VerifiedLineage:
    config: tuple[tuple[str, str], ...]
    lineage: str
    contract_sha256: str
    r0: tuple[FileRecord, ...]
    r1: tuple[FileRecord, ...]
    package_sha256: str


@dataclass(frozen=True)
class StageManifest:
    lineage: str
    contract_sha256: str
    package_sha256: str
    output: str
    files: tuple[FileRecord, ...]


def _digest(data):
    return hashlib.sha256(data).hexdigest().upper()


def _hash_file(path):
    _no_links(path)
    if not path.is_file():
        raise LineageError(f'Not a regular file: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest().upper()


def _no_links(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0)
                                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024)):
            raise LineageError(f'Linked/reparse path is forbidden: {part}')


def _safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise LineageError('Invalid package path')
    for part in name.split('/'):
        if (not part or part in {'.', '..'} or part[-1] in ' .'
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',
                                part.split('.')[0], re.IGNORECASE)):
            raise LineageError(f'Unsafe package path: {name}')
    return name


def _records(rows):
    out, seen = [], set()
    for row in rows:
        if set(row) != {'path', 'bytes', 'sha256'}:
            raise LineageError('Invalid file record')
        name = _safe_name(row['path'])
        if name.casefold() in seen:
            raise LineageError('Casefold duplicate path')
        seen.add(name.casefold())
        if type(row['bytes']) is not int or row['bytes'] < 0 or not re.fullmatch('[0-9A-F]{64}',row['sha256']):
            raise LineageError('Invalid byte count or SHA256')
        out.append(FileRecord(name,row['bytes'],row['sha256']))
    return tuple(sorted(out,key=lambda r:r.path))


def _scan(root):
    _no_links(root)
    if not root.is_dir():
        raise LineageError(f'Missing source directory: {root}')
    out = []
    def failed_inventory(error):
        raise LineageError(f'Cannot inventory source directory: {error}') from error

    for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed_inventory):
        for name in dirs:
            _no_links(Path(parent)/name)
        for name in files:
            path = Path(parent)/name
            rel = _safe_name(path.relative_to(root).as_posix())
            out.append({'path':rel,'bytes':path.stat().st_size,'sha256':_hash_file(path)})
    return _records(out)


def _load_contract():
    path = Path(__file__).parent/'contracts'/'lineage.json'
    data = path.read_bytes()
    # Git may check text out as CRLF; pin the platform-independent text bytes.
    normalized = data.replace(b'\r\n', b'\n')
    if _digest(normalized) != _CONTRACT_SHA256:
        raise LineageError('Repository lineage authority changed')
    return json.loads(normalized)


def _list_package(tool, package):
    result = subprocess.run([str(tool),'-g','bg3','-a','list-package','-s',str(package)],
                            capture_output=True,text=True,timeout=60,check=False)
    if result.returncode or result.stderr:
        raise LineageError('Pinned Divine listing failed')
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([^\t]+)\t([0-9]+)\t0', line)
        if not match:
            raise LineageError(f'Unexpected listing line: {line}')
        rows.append((match[1],int(match[2])))
    return rows


def verify_lineage_inputs(config):
    if type(config) is not dict or set(config) != _CONFIG_KEYS:
        raise LineageError('Configuration accepts exact path fields only')
    paths = {}
    for key,value in config.items():
        if not isinstance(value, (str,Path)) or not Path(value).is_absolute():
            raise LineageError('Input paths must be explicit absolute paths')
        path = Path(value)
        if '..' in path.parts:
            raise LineageError('Input traversal forbidden')
        _no_links(path)
        paths[key] = path.resolve(strict=True)
    contract = _load_contract()
    contract_sha = _digest(json.dumps(contract,sort_keys=True,separators=(',',':')).encode())
    r0, r1 = _records(contract['r0']), _records(contract['r1'])
    # Only exact pinned files are allowed; no broad Lua directory authorization.
    for row in r1:
        if not (row.path.startswith('Mods/ClothMorphRuntime/ScriptExtender/Lua/')
                or row.path in {'Mods/ClothMorphRuntime/MCM_blueprint.json','Mods/ClothMorphRuntime/meta.lsx'}):
            raise LineageError('Overlay attempts to change protected payload')
    pak,tool = paths['r0_package'],paths['divine']
    before = _hash_file(pak)
    if before != contract['package']['sha256'] or pak.stat().st_size != contract['package']['bytes']:
        raise LineageError('Wrong R0 package')
    if _hash_file(tool) != contract['divineSha256']:
        raise LineageError('Wrong package-listing tool')
    listing,seen = [],set()
    for name,size in _list_package(tool,pak):
        _safe_name(name)
        if name.casefold() in seen or type(size) is not int or size < 0:
            raise LineageError('Invalid/duplicate package listing')
        seen.add(name.casefold())
        listing.append((name,size))
    if sorted(listing) != [(r.path,r.bytes) for r in r0]:
        raise LineageError('Package listing does not match complete R0 inventory')
    if _scan(paths['r0_root']) != r0:
        raise LineageError('R0 extracted bytes/path set drift')
    if _scan(paths['r1_root']) != r1:
        raise LineageError('R1 overlay bytes/path set drift')
    if _hash_file(pak) != before or _hash_file(tool) != contract['divineSha256']:
        raise LineageError('Package/tool changed during verification')
    return VerifiedLineage(tuple(sorted((k,str(v)) for k,v in paths.items())),
                           contract['lineage'],contract_sha,r0,r1,before)


def compose_runtime_stage(verified, output):
    if type(verified) is not VerifiedLineage:
        raise LineageError('A verified lineage receipt is required')
    fresh = verify_lineage_inputs(dict(verified.config))
    if fresh != verified:
        raise LineageError('Forged/stale verification receipt')
    output = Path(output)
    if not output.is_absolute() or '..' in output.parts:
        raise LineageError('Explicit non-traversing output path required')
    _no_links(output)
    root = _STAGE_ROOT.absolute()
    _no_links(root)
    resolved = output.resolve()
    if resolved == root or root not in resolved.parents:
        raise LineageError('Output is outside isolated stage root')
    inputs = dict(fresh.config)
    for source in map(Path,inputs.values()):
        if source == resolved or source in resolved.parents or resolved in source.parents:
            raise LineageError('Output overlaps lineage inputs')
    if output.exists():
        raise LineageError('Destination must not exist')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(exist_ok=False)
    chosen = {r.path:(r,Path(inputs['r0_root'])) for r in fresh.r0}
    chosen.update({r.path:(r,Path(inputs['r1_root'])) for r in fresh.r1})
    for name,(row,source_root) in sorted(chosen.items()):
        source = source_root/name
        _no_links(source)
        data = source.read_bytes()
        if len(data) != row.bytes or _digest(data) != row.sha256:
            raise LineageError('Source changed during composition; partial stage retained')
        destination = output/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        _no_links(destination)
        with destination.open('xb') as stream:
            stream.write(data)
    expected = tuple(row for _,(row,_) in sorted(chosen.items()))
    actual = _scan(output)
    if actual != expected or verify_lineage_inputs(inputs) != fresh:
        raise LineageError('Readback/input drift; partial stage retained, not accepted')
    return StageManifest(fresh.lineage,fresh.contract_sha256,fresh.package_sha256,str(output),actual)
