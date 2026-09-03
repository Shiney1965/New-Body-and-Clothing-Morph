"""Exclusive verified-source per-defect RED/GREEN runner; not release acceptance."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
from .provenance import verify_lineage_inputs, compose_runtime_stage
from .qualification import compose_qualified_stage


def main():
    config_path=Path(sys.argv[1])
    selector=sys.argv[2]
    root=Path(__file__).parent.resolve()
    suffix='review-'+uuid4().hex
    frozen=root/'local/harnesses'/suffix
    receipts=[]
    for name in ('production_engine.lua','test_r1_review_round1.lua'):
        source=root/'tests/lua'/name
        data=source.read_bytes()
        frozen.mkdir(parents=True,exist_ok=True)
        with (frozen/name).open('xb') as stream: stream.write(data)
        receipts.append({'path':str(source),'sha256':hashlib.sha256(data).hexdigest().upper()})
    config=json.loads(config_path.read_bytes())
    verified=verify_lineage_inputs(config['inputs'])
    base=compose_runtime_stage(verified,root/'local/stages'/('base-'+suffix))
    stage=compose_qualified_stage(verified,base,root/'local/stages/qualified'/suffix)
    command=[shutil.which('lua'),str(frozen/'test_r1_review_round1.lua'),stage.output,selector]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    drift=[r['path'] for r in receipts if hashlib.sha256(Path(r['path']).read_bytes()).hexdigest().upper()!=r['sha256']]
    report={'stage':asdict(stage),'command':command,'selector':selector,'exit_code':result.returncode,
            'stdout':result.stdout,'stderr':result.stderr,'harnesses':receipts,'harnessDrift':drift,
            'Task2':'IN_PROGRESS','gameplay':'NOT_RUN'}
    evidence=Path(stage.output+'.focus.json')
    with evidence.open('x') as stream: json.dump(report,stream,indent=2)
    print(str(evidence));print(result.stdout,end='');print(result.stderr,end='')
    return result.returncode if not drift else 2


if __name__=='__main__': raise SystemExit(main())
