"""Run separate grid and time-step checks for the normalized gabled benchmark.

These are numerical tests of the nominal building envelope, not field validation.
Each run writes to a new directory and leaves existing results untouched.
"""
import argparse
import copy
import json
from pathlib import Path

from .warehouse_case import execute, validate


def run_suite(config, output, max_cells=None):
    model = validate(config)
    if model['kind'] != 'normalized_gable_verification':
        raise ValueError('The convergence suite requires the normalized gable benchmark')
    grid = config['geometry_spec']['mesh']
    grid_levels = [(max(1, grid['nx']//2), max(1, grid['ny_per_half']//2), max(1, grid['nz']//2)),
                   (grid['nx'], grid['ny_per_half'], grid['nz']),
                   (grid['nx']*2, grid['ny_per_half']*2, grid['nz']*2)]
    required_cells = max(2*nx*ny*nz for nx, ny, nz in grid_levels)
    budget = grid['maximum_cells'] if max_cells is None else max_cells
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < required_cells:
        raise ValueError(f'Refinement requires an explicit cell budget of at least {required_cells}')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for index, (nx, ny, nz) in enumerate(grid_levels):
        variant = copy.deepcopy(config)
        variant['geometry_spec']['mesh'].update(nx=nx, ny_per_half=ny, nz=nz,
                                                maximum_cells=budget)
        variant['numerics'].update(dt_s=0.1, end_s=10, write_interval_s=2)
        cases.append((f'grid_{index}', 'grid', variant))
    for index, dt in enumerate((2, 1, 0.5)):
        variant = copy.deepcopy(config)
        variant['numerics'].update(dt_s=dt, end_s=10, write_interval_s=2)
        cases.append((f'time_{index}', 'time', variant))
    rows = []
    for name, axis, variant in cases:
        checks = execute(variant, output/name)
        rows.append({'case': name, 'axis': axis, 'cells': checks['cells'],
                     'dt_s': variant['numerics']['dt_s'], 'frames': checks['frames'],
                     'analytic_rmse': checks['analytic_rmse'],
                     'relative_balance_error': checks['relative_balance_error'],
                     'numerical_pass': checks['numerical_pass']})
    grid_errors = [row['analytic_rmse'] for row in rows if row['axis'] == 'grid']
    time_errors = [row['analytic_rmse'] for row in rows if row['axis'] == 'time']
    report = {'model': model['kind'], 'geometry_basis': model['geometry']['coordinate_basis'],
              'explicit_maximum_cells': budget,
              'grid_refinement': {'varying': 'nx, ny_per_half, nz', 'fixed_dt_s': 0.1,
                                  'rmse_coarse_to_fine': grid_errors,
                                  'decreasing': all(a > b for a, b in zip(grid_errors, grid_errors[1:]))},
              'time_refinement': {'fixed_mesh': grid_levels[1], 'dt_s': [2, 1, 0.5],
                                  'rmse_coarse_to_fine': time_errors,
                                  'decreasing': all(a > b for a, b in zip(time_errors, time_errors[1:]))},
              'runs': rows}
    report['pass'] = (all(row['numerical_pass'] for row in rows)
                      and report['grid_refinement']['decreasing']
                      and report['time_refinement']['decreasing'])
    (output/'convergence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-cells', type=int, help='Explicit budget for the refined meshes')
    args = parser.parse_args()
    report = run_suite(json.loads(args.config.read_text(encoding='utf-8')), args.output, args.max_cells)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
