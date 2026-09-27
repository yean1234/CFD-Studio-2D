"""Plan-derived, explicitly assumed ClO2 diffusion scenario; no field validation."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

from .warehouse_case import generate, write_scalar, AIR_DIFFUSIVITY_M2_S, DIFFUSIVITY_SOURCE
from .warehouse_geometry import checked_mesh_quality, validate as validate_geometry
from .mesh_centres import cell_centres
from .run import run_command, read_field, header

PATCHES = ('floor', 'roof', 'sideWalls', 'endWall', 'annexInterface')


def validate(spec):
    if spec.get('schema') != 1:
        raise ValueError('Unknown scenario schema')
    geometry = validate_geometry(spec['geometry_spec'])
    times = np.asarray(spec['temperature']['times_s'], float)
    temperatures = np.asarray(spec['temperature']['values_C'], float)
    n = spec['numerics']
    if (times.ndim != 1 or len(times) < 2 or temperatures.shape != times.shape
            or not np.isfinite(times).all() or not np.isfinite(temperatures).all()
            or times[0] != 0 or not np.all(np.diff(times) > 0)
            or times[-1] != n['end_s'] or temperatures.min() < 5 or temperatures.max() > 40):
        raise ValueError('Temperature schedule must cover the run within literature interpolation range')
    for key in ('dt_s', 'end_s', 'write_interval_s'):
        if not np.isfinite(n[key]) or n[key] <= 0:
            raise ValueError('Invalid time controls')
    for ratio in (n['end_s']/n['dt_s'], n['write_interval_s']/n['dt_s'], n['end_s']/n['write_interval_s']):
        if not np.isclose(ratio, round(ratio), rtol=0, atol=1e-9):
            raise ValueError('Time controls must align')
    loading = spec['loading']
    if not 0 < loading['porosity'] <= 1 or not np.isfinite(loading['tortuosity']) or loading['tortuosity'] < 1:
        raise ValueError('Invalid assumed porous properties')
    g = spec['geometry_spec']['geometry']
    blocks = []
    for block in loading['blocks']:
        lower, upper = np.asarray(block['min_m'], float), np.asarray(block['max_m'], float)
        if (lower.shape != (3,) or upper.shape != (3,) or not np.isfinite([lower, upper]).all()
                or np.any(lower >= upper) or np.any(lower < 0)
                or upper[0] > g['length_m'] or upper[1] > g['width_m'] or upper[2] > 3):
            raise ValueError('Invalid loading block')
        if lower[0] < 1 or lower[1] < 1 or upper[0] > g['length_m']-1 or upper[1] > g['width_m']-1:
            raise ValueError('Loading must keep one-metre wall clearance')
        for old_lower, old_upper in blocks:
            if np.all(lower < old_upper) and np.all(upper > old_lower):
                raise ValueError('Loading blocks overlap')
        blocks.append((lower, upper))
    initial = spec['initial']
    for key in ('background_mg_m3', 'gaussian_peak_mg_m3'):
        if not np.isfinite(initial[key]) or initial[key] < 0:
            raise ValueError('Invalid initial concentration')
    if (np.asarray(initial['sigma_m']).shape != (3,) or np.any(np.asarray(initial['sigma_m']) <= 0)
            or not np.isfinite(initial['sigma_m']).all() or not np.isfinite(initial['centre_m']).all()):
        raise ValueError('Invalid initial field shape')
    if not all(spec[key].get('basis') for key in ('loading', 'initial')) or not spec['provenance'].get('temperature_basis'):
        raise ValueError('Scenario evidence and assumptions are required')
    return geometry


def execute(spec, output):
    geometry = validate(spec)
    out = Path(output)
    zero = {'value_s_inv': 0, 'basis': 'scenario_assumption', 'source': 'First transport-only scenario; reaction and exchange omitted'}
    base = {'schema': 1, 'geometry_spec': spec['geometry_spec'], 'numerics': spec['numerics'],
            'transport': {'kind': 'clo2_gas_in_air', 'temperature_C': 23, 'initial_mg_m3': 1,
                          'initial_evidence': spec['initial']['basis'], 'reaction': zero, 'exchange': zero}}
    model = generate(base, out)
    (out/'state.json').write_text('{"status":"running"}')
    try:
        run_command(out, 'blockMesh')
        run_command(out, 'checkMesh')
        quality = checked_mesh_quality((out/'log.checkMesh').read_text(), geometry['cells'], geometry['volume_m3'])
        (out/'mesh_quality.json').write_text(json.dumps(quality, indent=2))
        centres = cell_centres(out/'constant/polyMesh', geometry['cells'])
        loaded = np.zeros(len(centres), bool)
        counts = []
        for block in spec['loading']['blocks']:
            mask = np.all((centres >= block['min_m']) & (centres < block['max_m']), axis=1)
            if not mask.any():
                raise ValueError('A loading block contains no cells; refine mesh')
            loaded |= mask
            counts.append({'id': block['id'], 'cells': int(mask.sum())})
        eps = np.where(loaded, spec['loading']['porosity'], 1.)
        schedule_t = np.asarray(spec['temperature']['times_s'])
        schedule_T = np.asarray(spec['temperature']['values_C'])
        diffusion = np.interp(schedule_T, list(AIR_DIFFUSIVITY_M2_S), list(AIR_DIFFUSIVITY_M2_S.values()))
        K = diffusion[0]*np.where(loaded, eps/spec['loading']['tortuosity'], 1.)
        initial = spec['initial']
        C = (initial['background_mg_m3'] + initial['gaussian_peak_mg_m3']*
             np.exp(-.5*np.sum(((centres-initial['centre_m'])/initial['sigma_m'])**2, axis=1)))*1e-6
        for name, values, dimensions in [('C', C, '1 -3 0 0 0 0 0'), ('eps', eps, '0 0 0 0 0 0 0'),
                                         ('K', K, '0 2 -1 0 0 0 0')]:
            write_scalar(out/'0', name, values, dimensions, PATCHES)
        (out/'constant/transportControl').write_text(header('transportControl')+
            'sourceEnd 0; steadyEnabled false;\ndiffusionTimes ('+' '.join(map(str, schedule_t))+');\n'+
            'diffusionScales ('+' '.join(f'{x:.16g}' for x in diffusion/diffusion[0])+');\n')
        model.update(kind='clo2_plan_scenario', model_validation='assumed_scenario_not_experimentally_validated',
                     diffusivity_m2_s=float(diffusion[0]), diffusivity_source=DIFFUSIVITY_SOURCE,
                     temperature_representation='prescribed_spatially_uniform_time_series',
                     temperature_source=spec['provenance']['temperature_paper'],
                     velocity_representation='prescribed_zero_no_momentum_solve', loading=spec['loading'],
                     assumptions=spec['assumptions'], numerical_validation_scope='execution_mass_balance_positivity_only')
        (out/'model_contract.json').write_text(json.dumps(model, ensure_ascii=False, indent=2))
        (out/'transport_input.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2))
        (out/'loading_report.json').write_text(json.dumps({'blocks': counts, 'loaded_cells': int(loaded.sum()),
            'representation': 'cell-centre block mask; faces approximate ideal block boundaries'}, indent=2))
        hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for folder in ('0', 'constant', 'system') for p in (out/folder).rglob('*') if p.is_file()}
        for name in ('model_contract.json', 'transport_input.json'):
            hashes[name] = hashlib.sha256((out/name).read_bytes()).hexdigest()
        (out/'input_hashes.json').write_text(json.dumps(hashes, indent=2))
        run_command(out, 'porousTracerFoam')
        n = spec['numerics']
        times = np.arange(round(n['end_s']/n['write_interval_s'])+1)*n['write_interval_s']
        fields = np.array([read_field(out/f'{time:g}'/'C', len(centres)) for time in times])
        temperatures = np.interp(times, schedule_t, schedule_T)
        mass = np.array([[float(v) for v in line.split()[1:]] for line in (out/'log.porousTracerFoam').read_text().splitlines() if line.startswith('MASS ')])
        balance = float(abs(mass[-1, 1]-mass[0, 1])/max(abs(mass[0, 1]), 1e-30))
        integral = np.sum((fields[:-1]+fields[1:])*.5*np.diff(times)[:, None], axis=0)*1e6
        for time, temp in zip(times, temperatures):
            write_scalar(out/f'{time:g}', 'T', np.full(len(centres), temp+273.15), '0 0 0 1 0 0 0', PATCHES)
        np.savez_compressed(out/'concentration.npz', times_s=times.astype(float), concentration=fields,
                            concentration_unit='kg/m3', cell_centres_m=centres,
                            integrated_concentration=integral, integrated_concentration_unit='mg*s/m3',
                            temperature_C=temperatures, loaded_region=loaded.astype(float))
        passed = bool(np.isfinite(fields).all() and fields.min() >= -1e-10 and balance < 1e-7 and mass[-1, 0] == n['end_s'])
        checks = {'represented_model': model['kind'], 'model_validation': model['model_validation'],
                  'geometry_basis': spec['geometry_spec']['geometry']['coordinate_basis'], 'cells': len(centres),
                  'frames': len(times), 'relative_balance_error': balance, 'initial_inventory': float(mass[0, 1]),
                  'final_inventory': float(mass[-1, 1]), 'concentration_unit': 'kg/m3',
                  'minimum_concentration': float(fields.min()), 'maximum_concentration': float(fields.max()),
                  'execution_checks_pass': passed, 'numerical_pass': False,
                  'numerical_validation_scope': 'mass_balance_and_positivity_only_no_refinement_study',
                  'experimental_validation': False, 'temperature_range_C': [float(temperatures.min()), float(temperatures.max())]}
        (out/'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
        (out/'state.json').write_text(json.dumps({'status': 'complete' if passed else 'failed'}))
        return checks
    except BaseException as error:
        (out/'state.json').write_text(json.dumps({'status': 'failed', 'error': str(error)}))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(json.loads(args.config.read_text()), args.output), ensure_ascii=False, indent=2))
