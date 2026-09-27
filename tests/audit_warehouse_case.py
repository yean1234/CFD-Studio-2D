"""Independently compare saved OpenFOAM scalar fields with the warehouse NPZ.

This checks storage and conversion fidelity. It does not validate the physics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np


def raw_field(path, cells):
    content = path.read_text(encoding='ascii')
    match = re.search(r'\binternalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;',
                      content, re.DOTALL)
    if not match or int(match.group(1)) != cells:
        raise ValueError(f'Unexpected OpenFOAM scalar field: {path}')
    values = np.fromstring(match.group(2), sep=' ')
    if values.shape != (cells,) or not np.isfinite(values).all():
        raise ValueError(f'Invalid scalar data: {path}')
    dimensions = re.search(r'\bdimensions\s*\[([^]]+)\]', content)
    if not dimensions:
        raise ValueError(f'Missing field dimensions: {path}')
    return values, dimensions.group(1).strip()


def audit(case):
    case = Path(case)
    model = json.loads((case/'model_contract.json').read_text(encoding='utf-8'))
    cells = model['geometry']['cells']
    expected_dimensions = model['field_dimensions']
    with np.load(case/'concentration.npz', allow_pickle=False) as archive:
        times = archive['times_s'].copy()
        saved = archive['concentration'].copy()
        integrated = archive['integrated_concentration'].copy()
        centres = archive['cell_centres_m'].copy()
        unit = str(archive['concentration_unit'])
        integrated_unit = str(archive['integrated_concentration_unit'])
    if (times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all()
            or times[0] != 0 or not np.all(np.diff(times) > 0)
            or saved.shape != (len(times), cells) or not np.isfinite(saved).all()
            or centres.shape != (cells, 3) or not np.isfinite(centres).all()
            or integrated.shape != (cells,) or not np.isfinite(integrated).all()):
        raise ValueError('Invalid saved warehouse arrays or timeline')
    expected_integrated_unit = 'mg*s/m3' if unit == 'kg/m3' else '(C/C_ref)*s'
    if unit != model['initial_unit'] or integrated_unit != expected_integrated_unit:
        raise ValueError('Saved warehouse field units differ from the model contract')
    raw_times = sorted(float(p.name) for p in case.iterdir()
                       if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?', p.name))
    if len(raw_times) != len(times) or not np.array_equal(raw_times, times):
        raise ValueError('OpenFOAM and NPZ timelines differ')
    max_difference = 0.0
    hashes = {}
    for index, time in enumerate(times):
        path = case/f'{time:g}'/'C'
        values, dimensions = raw_field(path, cells)
        if dimensions != expected_dimensions:
            raise ValueError(f'Field dimensions differ at {time:g} s')
        max_difference = max(max_difference, float(np.max(np.abs(values-saved[index]))))
        hashes[f'{time:g}/C'] = hashlib.sha256(path.read_bytes()).hexdigest()
    scale = 1e6 if unit == 'kg/m3' and integrated_unit == 'mg*s/m3' else 1
    calculated = np.sum((saved[:-1]+saved[1:])*0.5*np.diff(times)[:, None], axis=0)*scale
    integral_difference = float(np.max(np.abs(calculated-integrated)))
    tolerance = 1e-12*max(1, float(np.max(np.abs(integrated))))
    if max_difference > 0 or integral_difference > tolerance:
        raise ValueError('Saved concentration or time integral differs from original fields')
    return {'case': str(case), 'frames': len(times), 'cells': cells, 'scalar_values': saved.size,
            'concentration_unit': unit, 'integrated_unit': integrated_unit,
            'max_raw_npz_difference': max_difference,
            'max_integral_difference': integral_difference, 'raw_field_sha256': hashes,
            'storage_audit_pass': True, 'physical_validation': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.case), ensure_ascii=False, indent=2))
