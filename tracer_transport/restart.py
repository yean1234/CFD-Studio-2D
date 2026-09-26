"""Restart into a new case directory; preserve every source checkpoint and failed log."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import numpy as np
from .protocol import fingerprint
from .run import analyse, read_field, run_command


def restart(source, target):
    source=Path(source).resolve(); target=Path(target).resolve()
    if target.exists() or source in target.parents:
        raise ValueError('Restart destination must be a new folder outside the source')
    cfg=json.loads((source/'config.json').read_text())
    if (source/'checks.json').exists() and json.loads((source/'checks.json').read_text()).get('steady_reached'):
        raise ValueError('Case already reached steady state; use a new project for changed conditions')
    if cfg.get('schema')!=2:
        raise ValueError('This solver requires schema 2 with Q state; old results are preserved, not migrated implicitly')
    if fingerprint(cfg)!=(source/'config.sha256').read_text().strip():
        raise ValueError('Configuration changed; restart refused')
    manifest=json.loads((source/'inputs.sha256.json').read_text())
    for name,digest in manifest.items():
        path=(source/name).resolve()
        if source not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Changed immutable input: {name}')
    n=int(np.prod(cfg['shape_xyz']))
    candidates=[]; skipped=[]
    for folder in source.iterdir():
        if folder.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?',folder.name):
            try:
                t=float(folder.name)
                values=read_field(folder/'C',n)
                qvalues=read_field(folder/'Q',n)
                if not np.isfinite(qvalues).all() or np.min(qvalues)<-1e-10:
                    raise ValueError('Invalid sorbed state')
                if not np.isfinite(values).all() or np.min(values)<-1e-10:
                    raise ValueError('Invalid concentrations')
                if not np.isclose(t/cfg['write_interval_s'],round(t/cfg['write_interval_s'])):
                    raise ValueError('Checkpoint is not an output time')
                if t>cfg['end_s']:
                    raise ValueError('Checkpoint beyond configured end')
                candidates.append((t,folder))
            except (OSError,ValueError):
                skipped.append(folder.name)
    if not candidates:
        raise ValueError('No readable checkpoint; source retained')
    anchor=max(t for t,_ in candidates)
    if anchor>=cfg['end_s']:
        raise ValueError('Case already reached configured end time')
    # Only original generated structured cases are admitted, never arbitrary production cases.
    target.mkdir(parents=True)
    for directory in ['0','constant','system']:
        shutil.copytree(source/directory,target/directory)
    for name in ['config.json','config.sha256','inputs.sha256.json','criteria.json','conditions.json','CONDITIONS.md','region_id.npy']:
        shutil.copy2(source/name,target/name)
    for t,folder in candidates:
        if t>0:
            shutil.copytree(folder,target/folder.name)
    control=target/'system/controlDict'
    content=control.read_text()
    content=re.sub(r'startFrom\s+[^;]+;','startFrom startTime;',content)
    for key,value in [('startTime',anchor),('endTime',cfg['end_s']),('deltaT',cfg['dt_s']),('writeInterval',cfg['write_interval_s'])]:
        content=re.sub(r'\b'+key+r'\s+[^;]+;',f'{key} {value:.16g};',content)
    control.write_text(content)
    record={'anchor_s':anchor,'skipped_incomplete':skipped,'status':'running','config_sha256':fingerprint(cfg)}
    (target/'restart.json').write_text(json.dumps(record,indent=2))
    started=time.perf_counter()
    try:
        # Rebuild from the hashed mesh specification rather than trust a changed mesh.
        run_command(target,'blockMesh')
        run_command(target,'checkMesh')
        run_command(target,'porousTracerFoam','log.restart')
        prefix=(source/'log.porousTracerFoam').read_text() if (source/'log.porousTracerFoam').exists() else ''
        # Failed runs may contain mass diagnostics after the last usable checkpoint.
        lines=[line for line in prefix.splitlines() if not line.startswith(('MASS ','SORBED ','PROGRESS ')) or float(line.split()[1])<=anchor]
        (target/'log.porousTracerFoam').write_text('\n'.join(lines)+'\n'+(target/'log.restart').read_text())
        result=analyse(target,started)
        record['status']='complete' if result['pass'] else 'failed'
        (target/'restart.json').write_text(json.dumps(record,indent=2))
        if not result['pass']:
            raise RuntimeError('Restart numerical checks failed')
        return result
    except BaseException as exc:
        record.update(status='failed',error=str(exc))
        (target/'restart.json').write_text(json.dumps(record,indent=2))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('target',type=Path)
    args=parser.parse_args()
    print(json.dumps(restart(args.source,args.target),indent=2))
