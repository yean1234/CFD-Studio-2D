"""Gabled storage-building transport cases with explicit model provenance.

The ClO2 path is a parameterized gas-in-air model, not a calibrated rice stack
or a field-validated fumigation prediction. It has no gas generation controls.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from .run import header, read_field, run_command
from .mesh_centres import cell_centres
from .warehouse_geometry import build, checked_mesh_quality, validate as validate_geometry


# Lee et al., Journal of Food Engineering 2015, DOI 10.1016/j.jfoodeng.2014.07.008.
# Values in the author abstract are 0.129, 0.145, 0.173 cm2/s at 5, 23, 40 C.
AIR_DIFFUSIVITY_M2_S = {5: 1.29e-5, 23: 1.45e-5, 40: 1.73e-5}
DIFFUSIVITY_SOURCE = 'https://doi.org/10.1016/j.jfoodeng.2014.07.008'


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite')
    if value <= 0 if positive else value < 0:
        raise ValueError(f'{name} must be {"positive" if positive else "nonnegative"}')
    return float(value)


def rate(value, name):
    if not isinstance(value, dict) or set(value) != {'value_s_inv', 'basis', 'source'}:
        raise ValueError(f'{name} requires value_s_inv, basis and source')
    coefficient = number(value['value_s_inv'], name)
    if value['basis'] not in ('measured', 'literature', 'scenario_assumption'):
        raise ValueError(f'{name} has an unknown evidence basis')
    if not isinstance(value['source'], str) or not value['source'].strip():
        raise ValueError(f'{name} requires a source or explicit assumption')
    return coefficient


def validate(config):
    if not isinstance(config, dict) or set(config) != {'schema', 'geometry_spec', 'transport', 'numerics'} or config['schema'] != 1:
        raise ValueError('Unknown warehouse transport schema')
    geometry = validate_geometry(config['geometry_spec'])
    t, n = config['transport'], config['numerics']
    if not isinstance(t, dict) or not isinstance(n, dict):
        raise ValueError('Transport and numerics must be objects')
    if set(n) != {'dt_s', 'end_s', 'write_interval_s'}:
        raise ValueError('Unknown time controls')
    dt, end, interval = [number(n[key], key, True) for key in ('dt_s', 'end_s', 'write_interval_s')]
    for ratio in (end/dt, interval/dt, end/interval):
        if not math.isclose(ratio, round(ratio), abs_tol=1e-8, rel_tol=0):
            raise ValueError('Time controls must align exactly')
    if t.get('kind') == 'normalized_gable_verification':
        if set(t) != {'kind', 'initial_mean', 'initial_cosine_amplitude', 'diffusivity_m2_s', 'evidence'}:
            raise ValueError('Unknown normalized benchmark fields')
        mean = number(t['initial_mean'], 'initial_mean')
        amplitude = t['initial_cosine_amplitude']
        if isinstance(amplitude, bool) or not isinstance(amplitude, (int, float)) or not math.isfinite(amplitude):
            raise ValueError('initial_cosine_amplitude must be finite')
        diffusivity = number(t['diffusivity_m2_s'], 'diffusivity_m2_s', True)
        if mean < abs(amplitude) or t['evidence'] != 'numerical_test_assumption':
            raise ValueError('Normalized case requires nonnegative initial field and numerical-test provenance')
        return {'kind': t['kind'], 'diffusivity_m2_s': diffusivity, 'initial_unit': 'C/C_ref',
                'field_dimensions': '0 0 0 0 0 0 0', 'geometry': geometry, 'model_validation': 'numerical_only'}
    if t.get('kind') == 'clo2_gas_in_air':
        if set(t) != {'kind', 'temperature_C', 'initial_mg_m3', 'initial_evidence', 'reaction', 'exchange'}:
            raise ValueError('Unknown ClO2 model fields')
        temp = t['temperature_C']
        if isinstance(temp, bool) or temp not in AIR_DIFFUSIVITY_M2_S:
            raise ValueError('Literature diffusivity is available only at 5, 23 or 40 C; no extrapolation')
        initial = number(t['initial_mg_m3'], 'initial_mg_m3', True)
        if not isinstance(t['initial_evidence'], str) or not t['initial_evidence'].strip():
            raise ValueError('Initial concentration evidence is required')
        decay = rate(t['reaction'], 'reaction')
        exchange = rate(t['exchange'], 'exchange')
        if exchange and t['exchange']['basis'] == 'literature':
            raise ValueError('Building-specific exchange cannot be inferred from literature alone')
        return {'kind': t['kind'], 'diffusivity_m2_s': AIR_DIFFUSIVITY_M2_S[temp],
                'diffusivity_source': DIFFUSIVITY_SOURCE, 'initial_kg_m3': initial*1e-6,
                'reaction_s_inv': decay, 'exchange_s_inv': exchange,
                'initial_unit': 'kg/m3', 'field_dimensions': '1 -3 0 0 0 0 0',
                'geometry': geometry, 'model_validation': 'unvalidated_for_rice_warehouse'}
    raise ValueError('Unknown represented model')


def write_scalar(folder, name, values, dimensions, patches):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError(f'Invalid {name} field')
    body = f'internalField nonuniform List<scalar>\n{len(values)}\n(\n' + '\n'.join(f'{v:.16g}' for v in values) + '\n);'
    boundaries = '\n'.join(f'    {patch} {{ type zeroGradient; }}' for patch in patches)
    (folder/name).write_text(header(name, 'volScalarField') + f'dimensions [{dimensions}];\n{body}\nboundaryField {{\n{boundaries}\n}}\n')


def generate(config, destination):
    model = validate(config)
    model['solver_source_sha256'] = hashlib.sha256(
        (Path(__file__).parent/'solver/porousTracerFoam.C').read_bytes()).hexdigest()
    model['generator_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    destination = Path(destination)
    build(config['geometry_spec'], destination, check=False)
    (destination/'0').mkdir()
    cells = model['geometry']['cells']
    nx = config['geometry_spec']['mesh']['nx']
    length = config['geometry_spec']['geometry']['length_m']
    x = np.tile((np.arange(nx)+0.5)*length/nx, cells//nx)
    t = config['transport']
    if model['kind'] == 'normalized_gable_verification':
        initial = t['initial_mean'] + t['initial_cosine_amplitude']*np.cos(np.pi*x/length)
    else:
        initial = np.full(cells, model['initial_kg_m3'])
    zero = np.zeros(cells)
    one = np.ones(cells)
    patches = ('floor', 'roof', 'sideWalls', 'endWall', 'annexInterface')
    for name, values, dimensions in (
        ('C', initial, model['field_dimensions']), ('Q', zero, model['field_dimensions']),
        ('eps', one, '0 0 0 0 0 0 0'), ('K', np.full(cells, model['diffusivity_m2_s']), '0 2 -1 0 0 0 0'),
        ('kAds', zero, '0 0 -1 0 0 0 0'), ('kDes', zero, '0 0 -1 0 0 0 0'),
        ('decayRate', np.full(cells, model.get('reaction_s_inv', 0)), '0 0 -1 0 0 0 0'),
        ('exchangeRate', np.full(cells, model.get('exchange_s_inv', 0)), '0 0 -1 0 0 0 0'),
        ('sourceRate', zero, '1 -3 -1 0 0 0 0' if model['kind'] == 'clo2_gas_in_air' else '0 0 -1 0 0 0 0')):
        write_scalar(destination/'0', name, values, dimensions, patches)
    boundaries = '\n'.join(f'    {patch} {{ type fixedValue; value uniform (0 0 0); }}' for patch in patches)
    (destination/'0/U').write_text(header('U', 'volVectorField') +
        'dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\n'
        f'boundaryField {{\n{boundaries}\n}}\n')
    (destination/'constant/transportControl').write_text(header('transportControl') +
        'sourceEnd 0; steadyEnabled false;\n')
    n = config['numerics']
    (destination/'system/controlDict').write_text(header('controlDict') + f'''
application porousTracerFoam;
startFrom startTime; startTime 0; stopAt endTime; endTime {n['end_s']};
deltaT {n['dt_s']}; writeControl runTime; writeInterval {n['write_interval_s']};
writeFormat ascii; writePrecision 16; timeFormat general; timePrecision 10;
runTimeModifiable false;
''')
    (destination/'system/fvSchemes').write_text(header('fvSchemes') + '''
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,C) Gauss upwind; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
''')
    (destination/'system/fvSolution').write_text(header('fvSolution') + '''
solvers { C { solver PBiCGStab; preconditioner DILU; tolerance 1e-16; relTol 0; maxIter 2000; } }
''')
    (destination/'transport_input.json').write_text(json.dumps(config, ensure_ascii=False, indent=2))
    (destination/'model_contract.json').write_text(json.dumps(model, ensure_ascii=False, indent=2))
    hashes = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob('*') if p.is_file()}
    (destination/'input_hashes.json').write_text(json.dumps(hashes, indent=2))
    return model


def analyse(destination):
    destination = Path(destination)
    config = json.loads((destination/'transport_input.json').read_text())
    model = json.loads((destination/'model_contract.json').read_text())
    cells = model['geometry']['cells']
    times = sorted(float(p.name) for p in destination.iterdir()
                   if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?', p.name))
    fields = np.array([read_field(destination/f'{time:g}'/'C', cells) for time in times])
    log = (destination/'log.porousTracerFoam').read_text()
    mass = np.array([[float(x) for x in line.split()[1:]] for line in log.splitlines() if line.startswith('MASS ')])
    removed = np.array([[float(x) for x in line.split()[1:]] for line in log.splitlines() if line.startswith('REMOVED ')])
    if len(times) < 2 or len(mass) < 2 or len(removed) != len(mass) - 1:
        raise RuntimeError('Incomplete solver outputs')
    n = config['numerics']
    expected = np.arange(round(n['end_s']/n['write_interval_s'])+1)*n['write_interval_s']
    complete = len(times) == len(expected) and np.allclose(times, expected, atol=1e-9, rtol=0)
    initial_mass = mass[0, 1]
    final_balance = mass[-1, 1] + removed[-1, 1] + removed[-1, 2] - initial_mass
    relative_balance = abs(final_balance)/max(abs(initial_mass), 1e-30)
    result = {'represented_model': model['kind'], 'model_validation': model['model_validation'],
              'geometry_basis': config['geometry_spec']['geometry']['coordinate_basis'],
              'cells': cells, 'frames': len(times), 'timeline_complete': bool(complete),
              'initial_inventory': initial_mass, 'final_inventory': mass[-1, 1],
              'reaction_removed': removed[-1, 1], 'exchange_removed': removed[-1, 2],
              'relative_balance_error': relative_balance,
              'minimum_concentration': float(fields.min()), 'concentration_unit': model['initial_unit']}
    if model['kind'] == 'normalized_gable_verification':
        x = cell_centres(destination/'constant/polyMesh', cells)[:, 0]
        t = config['transport']
        exact = t['initial_mean'] + t['initial_cosine_amplitude']*np.cos(np.pi*x/config['geometry_spec']['geometry']['length_m'])*np.exp(-t['diffusivity_m2_s']*(np.pi/config['geometry_spec']['geometry']['length_m'])**2*times[-1])
        result['analytic_rmse'] = float(np.sqrt(np.mean((fields[-1]-exact)**2)))
    else:
        total_rate = model['reaction_s_inv'] + model['exchange_s_inv']
        exact = model['initial_kg_m3']*np.exp(-total_rate*times[-1])
        result['uniform_decay_rmse_kg_m3'] = float(np.sqrt(np.mean((fields[-1]-exact)**2)))
    analytic_ok = (result['analytic_rmse'] < 2e-3 if model['kind'] == 'normalized_gable_verification'
                   else result['uniform_decay_rmse_kg_m3']/model['initial_kg_m3'] < 2e-3)
    result['numerical_pass'] = bool(complete and relative_balance < 1e-8 and fields.min() >= -1e-12
                                    and analytic_ok)
    integral = np.sum((fields[:-1] + fields[1:])*0.5*np.diff(times)[:, None], axis=0)
    if model['kind'] == 'clo2_gas_in_air':
        integral *= 1e6
        integral_unit = 'mg*s/m3'
    else:
        integral_unit = '(C/C_ref)*s'
    result['integrated_concentration_unit'] = integral_unit
    result['integrated_concentration_min'] = float(integral.min())
    result['integrated_concentration_max'] = float(integral.max())
    centres = cell_centres(destination/'constant/polyMesh', cells)
    np.savez_compressed(destination/'concentration.npz', times_s=times, concentration=fields,
                        concentration_unit=model['initial_unit'], cell_centres_m=centres,
                        integrated_concentration=integral, integrated_concentration_unit=integral_unit)
    (destination/'checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def execute(config, destination):
    model = generate(config, destination)
    destination = Path(destination)
    (destination/'state.json').write_text(json.dumps({'status': 'running'}))
    try:
        for command in ('blockMesh', 'checkMesh', 'porousTracerFoam'):
            run_command(destination, command)
            if command == 'checkMesh':
                quality = checked_mesh_quality((destination/'log.checkMesh').read_text(),
                                               model['geometry']['cells'], model['geometry']['volume_m3'])
                (destination/'mesh_quality.json').write_text(json.dumps(quality, indent=2))
        result = analyse(destination)
        (destination/'state.json').write_text(json.dumps({'status': 'complete' if result['numerical_pass'] else 'failed'}))
        return result
    except BaseException as error:
        (destination/'state.json').write_text(json.dumps({'status': 'failed', 'error': str(error)}))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generate-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    result = generate(config, args.output) if args.generate_only else execute(config, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
