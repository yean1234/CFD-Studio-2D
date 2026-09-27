"""Read-only structural audit of existing Studio scalar Viewer projects."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np


def audit_project(project):
    cfg = json.loads((project/'case_config.json').read_text(encoding='utf-8'))['tracer']
    meta = json.loads((project/'meta.json').read_text(encoding='utf-8'))
    manifest = json.loads((project/'tracer_frames.json').read_text(encoding='utf-8'))
    rows = manifest['frames']
    expected_config_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if meta.get('tracer_config_sha256') != expected_config_hash:
        raise ValueError('case configuration hash mismatch')
    if manifest.get('schema') != 1 or manifest.get('integrity_schema') not in (None, 1):
        raise ValueError('unsupported result manifest schema')
    if (not rows or rows[0]['t'] != 0
            or any(not isinstance(row['t'], (int, float)) or not math.isfinite(row['t']) for row in rows)
            or any(rows[i]['t'] <= rows[i-1]['t'] for i in range(1, len(rows)))):
        raise ValueError('invalid timeline')
    if meta.get('end') != rows[-1]['t'] or meta.get('tmax') != rows[-1]['t']:
        raise ValueError('completion time differs from the result timeline')
    scalars = hashed_frames = 0
    seen = set()
    for row in rows:
        hashes = row.get('frame_sha256')
        if manifest.get('integrity_schema') == 1 and (not isinstance(hashes, dict) or set(hashes) != {'concentration', 'sorbed'}):
            raise ValueError('incomplete frame hash manifest')
        for kind, magic in [('concentration', b'CON1'), ('sorbed', b'SOR1')]:
            name = row[kind]
            if (not isinstance(name, str) or Path(name).name != name or '\\' in name
                    or name in seen or (project/name).is_symlink()):
                raise ValueError('invalid frame filename')
            seen.add(name)
            data = (project/name).read_bytes()
            if hashes is not None:
                if not isinstance(hashes, dict) or hashes.get(kind) != hashlib.sha256(data).hexdigest():
                    raise ValueError(f'frame hash mismatch: {name}')
                hashed_frames += 1
            if len(data) < 40 or data[:4] != magic:
                raise ValueError(f'invalid header: {name}')
            shape = struct.unpack('<3I', data[4:16])
            bounds = struct.unpack('<6f', data[16:40])
            if list(shape) != cfg['shape_xyz'] or len(data) != 40 + 4*math.prod(shape):
                raise ValueError(f'invalid frame size or shape: {name}')
            if (any(not math.isfinite(x) for x in bounds)
                    or any(abs(bounds[i]) > 1e-7 for i in range(3))
                    or any(abs(bounds[i+3]-cfg['lengths_m'][i]) >
                           1e-6*max(1, cfg['lengths_m'][i]) for i in range(3))):
                raise ValueError(f'invalid bounds: {name}')
            values = np.frombuffer(data, dtype='<f4', offset=40)
            if not np.isfinite(values).all():
                raise ValueError(f'nonfinite values: {name}')
            scalars += len(values)
    return len(rows), scalars, hashed_frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_root', type=Path)
    args = parser.parse_args()
    projects = sorted(p.parent for p in args.project_root.glob('*/tracer_frames.json'))
    issues = [] if projects else [{'project': str(args.project_root), 'error': 'no result projects found'}]
    frames = scalars = hashed_frames = 0
    for project in projects:
        try:
            count, values, protected = audit_project(project)
            frames += count
            scalars += values
            hashed_frames += protected
        except (OSError, ValueError, KeyError, TypeError, struct.error, OverflowError) as exc:
            issues.append({'project': str(project), 'error': str(exc)})
    print(json.dumps({'projects': len(projects), 'frames': frames,
                      'scalar_values': scalars, 'hash_verified_files': hashed_frames,
                      'issues': issues}, ensure_ascii=False))
    raise SystemExit(bool(issues))


if __name__ == '__main__':
    main()
