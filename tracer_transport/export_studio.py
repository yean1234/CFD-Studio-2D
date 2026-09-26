"""Export structured tracer snapshots to the existing Studio project/3D timeline."""
import argparse
import json
from pathlib import Path
import struct
import uuid
import numpy as np
from .protocol import fingerprint


def export_case(case, project):
    case, project = Path(case).resolve(), Path(project).resolve()
    cfg = json.loads((case/'config.json').read_text())
    digest = fingerprint(cfg)
    checks = json.loads((case/'checks.json').read_text())
    if not checks.get('pass'):
        raise ValueError('Numerical checks must pass before publishing results')
    with np.load(case/'concentration.npz', allow_pickle=False) as data:
        times = data['times'].copy()
        shape = data['shape_xyz'].copy()
        lengths = data['lengths_m'].copy()
        arrays = {key:data[name].copy() for key,name in
                  [('concentration','concentration'),('sorbed','sorbed_bulk')]}
    if (len(times) < 2 or times[0] != 0 or not np.isfinite(times).all()
            or not np.all(np.diff(times)>0) or list(shape) != cfg['shape_xyz']
            or not np.array_equal(lengths, cfg['lengths_m'])):
        raise ValueError('Invalid grid or physical timeline; t=0 is required')
    for values in arrays.values():
        if values.shape != (len(times),int(np.prod(shape))) or not np.isfinite(values).all():
            raise ValueError('Invalid scalar frames')
    old = json.loads((project/'meta.json').read_text()) if project.exists() else None
    if old and old.get('tracer_config_sha256') != digest:
        raise ValueError('Different physical settings require a new project')
    project.mkdir(parents=True, exist_ok=True)
    def write_json(name, value):
        tmp = project/(name+'.tmp')
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(project/name)
    manifest = []
    for i,t in enumerate(times):
        entry = {'t':float(t)}
        for key,magic in [('concentration',b'CON1'),('sorbed',b'SOR1')]:
            name = f'{key}_{t:.10g}.bin'
            payload = magic + struct.pack('<3I6f', *shape, 0,0,0,*lengths) + arrays[key][i].astype('<f4').tobytes()
            dest = project/name
            if dest.exists():
                if dest.read_bytes() != payload:
                    raise ValueError(f'Existing frame changed: {name}; publish a new project')
            else:
                tmp = project/(name+'.tmp')
                tmp.write_bytes(payload)
                tmp.replace(dest)
            entry[key] = name
        manifest.append(entry)
    ranges = {key:[0., max(float(values.max()),1e-12)] for key,values in arrays.items()}
    studio_cfg = {'_해석유형':'gas_transport', 'tracer':cfg,
                  'openfoam_mapping':{'solver':'porousTracerFoam'},
                  'run':{'end_time_s':float(times[-1]),'write_interval_s':cfg['write_interval_s'],
                         'output_fields':['concentration','sorbed']},
                  'scalar_ranges':ranges, 'performance':checks}
    write_json('case_config.json',studio_cfg)
    write_json('tracer_frames.json',{'schema':1,'frames':manifest})
    write_json('meta.json',{'run_id':old['run_id'] if old else 'tracer-'+uuid.uuid4().hex[:12],
                          'name':project.name,'external':True,'completed':True,'heal2':True,
                          'completion_reason':'converged' if checks.get('steady_reached') else 'time_limit',
                          'end':float(times[-1]),'tmax':float(times[-1]),
                          'settings':studio_cfg['run'],'tracer_config_sha256':digest})
    return {'project':str(project),'frames':len(times),'physical_duration_s':float(times[-1]),'ranges':ranges}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('case',type=Path)
    parser.add_argument('project',type=Path)
    args = parser.parse_args()
    print(json.dumps(export_case(args.case,args.project),ensure_ascii=False,indent=2))
