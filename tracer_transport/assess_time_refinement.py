"""Compare two fixed time steps on the same porous mesh and process count.

This is a time-step sensitivity check, not an observed-order or experimental
validation. Three time steps would be needed to estimate temporal order.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from .assess_porous_convergence import CRITERIA, load


def time_signature(spec):
    spec = copy.deepcopy(spec)
    spec['numerics'].pop('dt_s')
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def assess(coarse_case, fine_case):
    coarse, fine = load(coarse_case), load(fine_case)
    if time_signature(coarse['spec']) != time_signature(fine['spec']):
        raise ValueError('Settings differ beyond time step, including process count')
    dt = [v['spec']['numerics']['dt_s'] for v in (coarse, fine)]
    if not np.isclose(dt[0], 2 * dt[1], rtol=1e-12, atol=0):
        raise ValueError('Expected time-step reduction by two')
    if coarse['solver_sources'] != fine['solver_sources']:
        raise ValueError('Solver source versions differ')
    for name in ('fvSchemes', 'fvSolution'):
        if (coarse['case']/'system'/name).read_bytes() != (fine['case']/'system'/name).read_bytes():
            raise ValueError('Discretization or linear solver settings differ')
    for name in ('times_s', 'cell_volumes_m3', 'loaded_region'):
        if not np.array_equal(coarse[name], fine[name]):
            raise ValueError(f'Comparison {name} differs')
    for name in ('concentration', 'velocity_m_s', 'temperature_K'):
        if not np.array_equal(coarse[name][0], fine[name][0]):
            raise ValueError('Initial fields differ')
    volume = coarse['cell_volumes_m3']
    background = coarse['spec']['initial']['background_mg_m3'] * 1e-6
    rows = []
    for index, time in enumerate(coarse['times_s'][1:], start=1):
        c = coarse['concentration'][index]
        u = coarse['velocity_m_s'][index]
        dc = fine['concentration'][index] - c
        du = fine['velocity_m_s'][index] - u
        dtemp = fine['temperature_K'][index] - coarse['temperature_K'][index]
        rows.append({
            'time_s': float(time),
            'concentration_relative_L2': float(np.sqrt(np.sum(dc**2*volume) / max(np.sum((c-background)**2*volume), 1e-50))),
            'velocity_relative_L2': float(np.sqrt(np.sum(np.sum(du**2, axis=1)*volume) / max(np.sum(np.sum(u**2, axis=1)*volume), 1e-50))),
            'temperature_rmse_C': float(np.sqrt(np.sum(dtemp**2*volume)/volume.sum())),
        })
    criteria = {key: CRITERIA[key] for key in rows[0] if key != 'time_s'}
    worst = {key: max(row[key] for row in rows) for key in criteria}
    return {
        'cases': [str(coarse_case), str(fine_case)], 'dt_s': dt,
        'cells': len(volume), 'processes': coarse['spec']['coupled'].get('processes', 1),
        'frames': rows, 'criteria': criteria, 'worst': worst,
        'time_step_sensitivity_pass': all(worst[key] <= criteria[key] for key in criteria),
        'temporal_order_verified': False, 'experimental_validation': False,
        'scope': 'two time steps; same mesh, settings, initial fields and process count; only saved comparison times',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse_case', type=Path)
    parser.add_argument('fine_case', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = assess(args.coarse_case, args.fine_case)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
