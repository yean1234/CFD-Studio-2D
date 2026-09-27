"""Export structured tracer snapshots to the existing Studio project/3D timeline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tempfile
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
    labels = [f'{t:.10g}' for t in times]
    if len(set(labels)) != len(labels):
        raise ValueError('Frame times collide after filename formatting')
    float32_max = np.finfo(np.float32).max
    for values in arrays.values():
        if (values.shape != (len(times),int(np.prod(shape))) or not np.isfinite(values).all()
                or np.any(values > float32_max) or np.any(values < -float32_max)):
            raise ValueError('Invalid scalar frames')
    if project.exists() and (not project.is_dir() or (any(project.iterdir()) and not (project/'meta.json').is_file())):
        raise ValueError('Existing destination is not a published project')
    old = json.loads((project/'meta.json').read_text()) if (project/'meta.json').is_file() else None
    if old and old.get('tracer_config_sha256') != digest:
        raise ValueError('Different physical settings require a new project')
    manifest = []
    frames = []
    for i,t in enumerate(times):
        entry = {'t':float(t), 'frame_sha256':{}}
        for key,magic in [('concentration',b'CON1'),('sorbed',b'SOR1')]:
            name = f'{key}_{labels[i]}.bin'
            dest = project/name
            payload = magic + struct.pack('<3I6f', *shape, 0,0,0,*lengths) + arrays[key][i].astype('<f4').tobytes()
            if dest.exists():
                if dest.read_bytes() != payload:
                    raise ValueError(f'Existing frame changed: {name}; publish a new project')
            else:
                frames.append((i,key,magic,name))
            entry[key] = name
            entry['frame_sha256'][key] = hashlib.sha256(payload).hexdigest()
        manifest.append(entry)
    previous_manifest = project/'tracer_frames.json'
    if previous_manifest.exists():
        previous_rows = json.loads(previous_manifest.read_text(encoding='utf-8')).get('frames')
        if (not isinstance(previous_rows, list) or len(previous_rows) > len(manifest)
                or any(not isinstance(row, dict)
                       or any(row.get(key) != current[key] for key in ('t', 'concentration', 'sorbed'))
                       or ('frame_sha256' in row and row['frame_sha256'] != current['frame_sha256'])
                       for row, current in zip(previous_rows, manifest))):
            raise ValueError('Existing result timeline would be truncated or changed; publish a new project')
    ranges = {key:[0., max(float(values.max()),1e-12)] for key,values in arrays.items()}
    studio_cfg = {'_해석유형':'gas_transport', 'tracer':cfg,
                  'openfoam_mapping':{'solver':'porousTracerFoam'},
                  'run':{'end_time_s':float(times[-1]),'write_interval_s':cfg['write_interval_s'],
                         'output_fields':['concentration','sorbed']},
                  'scalar_ranges':ranges, 'performance':checks}
    metadata = {'run_id':old['run_id'] if old else 'tracer-'+uuid.uuid4().hex[:12],
                          'name':project.name,'external':True,'completed':True,'heal2':True,
                          'completion_reason':'converged' if checks.get('steady_reached') else 'time_limit',
                          'end':float(times[-1]),'tmax':float(times[-1]),
                          'settings':studio_cfg['run'],'tracer_config_sha256':digest}
    documents = [('case_config.json',studio_cfg),
                 ('tracer_frames.json',{'schema':1,'integrity_schema':1,'frames':manifest}),('meta.json',metadata)]
    project.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.'+project.name+'-export-', dir=project.parent) as temporary:
        staged = Path(temporary)
        for i,key,magic,name in frames:
            payload = magic + struct.pack('<3I6f', *shape, 0,0,0,*lengths) + arrays[key][i].astype('<f4').tobytes()
            (staged/name).write_bytes(payload)
        for name,value in documents:
            (staged/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        if not project.exists():
            staged.rename(project)
        else:
            # Publish frames first, then the index, then the completion metadata.
            for _,_,_,name in frames:
                (staged/name).replace(project/name)
            for name,_ in documents:
                (staged/name).replace(project/name)
    return {'project':str(project),'frames':len(times),'physical_duration_s':float(times[-1]),'ranges':ranges}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('case',type=Path)
    parser.add_argument('project',type=Path)
    args = parser.parse_args()
    print(json.dumps(export_case(args.case,args.project),ensure_ascii=False,indent=2))
