"""Run a sealed, buoyant U/T/C warehouse scenario with explicit assumptions.

A new output directory is mandatory. No existing results or solvers are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np

from .warehouse_scenario import PATCHES, validate as validate_base
from .warehouse_case import write_scalar, DIFFUSIVITY_SOURCE
from .warehouse_geometry import build, checked_mesh_quality
from .mesh_centres import cell_centres
from .run import header, read_field, run_command


PARAMETERS = ('initial_temperature_C', 'nu_m2_s', 'rho_kg_m3', 'cp_J_kg_K',
              'Pr', 'Prt', 'Sct', 'permeability_m2', 'solid_rhoCp_J_m3_K',
              'bulk_conductivity_W_m_K', 'envelope_h_W_m2_K',
              'initial_k_m2_s2', 'initial_epsilon_m2_s3', 'max_dt_s', 'max_Co')


def validate(spec):
    # The reference temperature series may extend beyond the pilot duration.
    base = dict(spec, numerics=dict(spec['numerics'], end_s=spec['temperature']['times_s'][-1]))
    geometry = validate_base(base)
    c = spec['coupled']
    for name in PARAMETERS:
        value = c[name]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')
    n = spec['numerics']
    if not 5 <= c['initial_temperature_C'] <= 40 or not 0 < n['end_s'] <= spec['temperature']['times_s'][-1]:
        raise ValueError('Invalid pilot duration or temperature')
    if not c.get('basis') or c.get('turbulence') != 'kEpsilon' or c['max_Co'] > .5:
        raise ValueError('Explicit parameter basis, kEpsilon and max Co <= 0.5 required')
    if any(not np.isfinite(n[k]) or n[k] <= 0 for k in ('dt_s', 'end_s', 'write_interval_s')):
        raise ValueError('Invalid time controls')
    if not np.isclose(n['end_s']/n['write_interval_s'], round(n['end_s']/n['write_interval_s'])):
        raise ValueError('Pilot end must align with output interval')
    return geometry


def uniform(out, name, value, dims, boundary, vector=False):
    cls = 'volVectorField' if vector else 'volScalarField'
    patches = '\n'.join(f'{p} {{ {boundary} }}' for p in PATCHES)
    (out/'0'/name).write_text(header(name, cls)+f'dimensions [{dims}];\ninternalField uniform {value};\nboundaryField {{\n{patches}\n}}\n')


def generate(spec, out):
    geometry = validate(spec)
    out = Path(out)
    build(spec['geometry_spec'], out, check=False)
    (out/'0').mkdir()
    (out/'state.json').write_text('{"status":"preparing"}')
    for command in ('blockMesh', 'checkMesh'):
        run_command(out, command)
    quality = checked_mesh_quality((out/'log.checkMesh').read_text(), geometry['cells'], geometry['volume_m3'])
    (out/'mesh_quality.json').write_text(json.dumps(quality, indent=2))
    centres = cell_centres(out/'constant/polyMesh', geometry['cells'])
    loaded = np.zeros(len(centres), bool)
    block_counts = []
    for block in spec['loading']['blocks']:
        mask = np.all((centres >= block['min_m']) & (centres < block['max_m']), axis=1)
        if not mask.any():
            raise ValueError('Mesh does not resolve a loading block')
        loaded |= mask
        block_counts.append({'id': block['id'], 'cells': int(mask.sum())})
    c, n = spec['coupled'], spec['numerics']
    eps = np.where(loaded, spec['loading']['porosity'], 1.)
    rho_cp = c['rho_kg_m3']*c['cp_J_kg_K']
    initial = spec['initial']
    concentration = (initial['background_mg_m3'] + initial['gaussian_peak_mg_m3'] *
        np.exp(-.5*np.sum(((centres-initial['centre_m'])/initial['sigma_m'])**2, axis=1)))*1e-6
    alpha_air = c['nu_m2_s']/c['Pr']
    fields = [
        ('C', concentration, '1 -3 0 0 0 0 0'),
        ('eps', eps, '0 0 0 0 0 0 0'),
        ('drag', np.where(loaded, c['nu_m2_s']/c['permeability_m2'], 0), '0 0 -1 0 0 0 0'),
        ('heatCapacityRatio', eps+(1-eps)*c['solid_rhoCp_J_m3_K']/rho_cp, '0 0 0 0 0 0 0'),
        ('alphaBulk', np.where(loaded, c['bulk_conductivity_W_m_K']/rho_cp, alpha_air), '0 2 -1 0 0 0 0'),
        ('diffusionFactor', np.where(loaded, eps/spec['loading']['tortuosity'], 1.), '0 0 0 0 0 0 0'),
        ('freeGas', (~loaded).astype(float), '0 0 0 0 0 0 0')]
    for name, values, dims in fields:
        write_scalar(out/'0', name, values, dims, PATCHES)
    temp = c['initial_temperature_C']+273.15
    table = ' '.join(f'({t:g} {v+273.15:.12g})' for t, v in zip(spec['temperature']['times_s'], spec['temperature']['values_C']))
    boundaries = []
    for p in PATCHES:
        # The annex interface and floor are insulated scenario boundaries.
        if p in ('floor', 'annexInterface'):
            bc = 'type zeroGradient;'
        else:
            bc = f'''type externalWallHeatFluxTemperature; mode coefficient;
                Ta table ({table}); h uniform {c['envelope_h_W_m2_K']};
                kappaMethod lookup; kappa kappa; value uniform {temp};'''
        boundaries.append(f'{p} {{ {bc} }}')
    (out/'0/T').write_text(header('T', 'volScalarField') +
        f'dimensions [0 0 0 1 0 0 0];\ninternalField uniform {temp};\nboundaryField {{'+ '\n'.join(boundaries)+'}\n')
    uniform(out, 'U', '(0 0 0)', '0 1 -1 0 0 0 0', 'type fixedValue; value uniform (0 0 0);', True)
    uniform(out, 'p_rgh', 0, '0 2 -2 0 0 0 0', 'type fixedFluxPressure; value uniform 0;')
    uniform(out, 'k', c['initial_k_m2_s2'], '0 2 -2 0 0 0 0', f"type kqRWallFunction; value uniform {c['initial_k_m2_s2']};")
    uniform(out, 'epsilon', c['initial_epsilon_m2_s3'], '0 2 -3 0 0 0 0', f"type epsilonWallFunction; value uniform {c['initial_epsilon_m2_s3']};")
    uniform(out, 'nut', 0, '0 2 -1 0 0 0 0', 'type nutkWallFunction; value uniform 0;')
    uniform(out, 'alphat', 0, '0 2 -1 0 0 0 0', f"type alphatJayatillekeWallFunction; Prt {c['Prt']}; value uniform 0;")
    (out/'constant/transportProperties').write_text(header('transportProperties')+f'''
transportModel Newtonian; nu {c['nu_m2_s']}; beta {1/temp}; TRef {temp};
Pr {c['Pr']}; Prt {c['Prt']};
''')
    (out/'constant/couplingProperties').write_text(header('couplingProperties')+f'airRhoCp {rho_cp}; Sct {c["Sct"]};\n')
    (out/'constant/turbulenceProperties').write_text(header('turbulenceProperties')+'simulationType RAS; RAS { RASModel kEpsilon; turbulence on; printCoeffs on; }\n')
    (out/'constant/g').write_text(header('g', 'uniformDimensionedVectorField')+'dimensions [0 1 -2 0 0 0 0]; value (0 0 -9.81);\n')
    (out/'system/controlDict').write_text(header('controlDict')+f'''
application warehouseBuoyantFoam;
startFrom startTime; startTime 0; stopAt endTime; endTime {n['end_s']};
deltaT {n['dt_s']}; adjustTimeStep yes; maxCo {c['max_Co']}; maxDeltaT {c['max_dt_s']};
writeControl adjustableRunTime; writeInterval {n['write_interval_s']};
writeFormat ascii; writePrecision 16; timeFormat general; timePrecision 12;
runTimeModifiable false; libs ("libthermoTools.so");
''')
    (out/'system/fvSchemes').write_text(header('fvSchemes')+'''
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes {
 default none; div(phi,U) Gauss upwind; div(phi,T) Gauss upwind;
 div(phi,C) Gauss upwind; div(phi,k) Gauss upwind; div(phi,epsilon) Gauss upwind;
 div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
fluxRequired { default no; T; p_rgh; }
''')
    (out/'system/fvSolution').write_text(header('fvSolution')+'''
solvers {
 p_rgh { solver GAMG; tolerance 1e-9; relTol 0.01; smoother GaussSeidel; }
 p_rghFinal { $p_rgh; relTol 0; }
 "(U|T|k|epsilon)" { solver PBiCGStab; preconditioner DILU; tolerance 1e-9; relTol 0; }
 "(U|T|k|epsilon)Final" { $U; }
 C { solver PBiCGStab; preconditioner DILU; tolerance 1e-14; relTol 0; }
}
PIMPLE { momentumPredictor yes; nOuterCorrectors 2; nCorrectors 2; nNonOrthogonalCorrectors 1; pRefCell 0; pRefValue 0; }
relaxationFactors { equations { ".*" 1; } }
''')
    model = dict(kind='clo2_coupled_scenario', initial_unit='kg/m3', field_dimensions='1 -3 0 0 0 0 0',
        geometry=geometry, model_validation='assumed_scenario_not_experimentally_validated',
        velocity_representation='solved_boussinesq_rans_brinkman_superficial',
        temperature_representation='solved_lte_energy_spatial_field',
        diffusivity_source=DIFFUSIVITY_SOURCE, loading=spec['loading'], assumptions=spec['assumptions'],
        numerical_validation_scope='execution_mass_energy_balance_only_no_refinement_study',
        solver='warehouseBuoyantFoam', field_units={'C':'kg/m3', 'U':'m/s', 'T':'K'},
        coupling='T -> buoyancy -> U,phi -> T,C; T -> D; dilute C has no feedback on flow')
    model['coordinate_representation'] = 'arithmetic_mean_of_six_face_centres; approximate_hexahedral_representative_point'
    source = Path(__file__).parent/'coupled_solver'
    model['solver_sources_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.suffix in ('.C','.H')}
    (out/'model_contract.json').write_text(json.dumps(model, ensure_ascii=False, indent=2))
    (out/'transport_input.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    (out/'loading_report.json').write_text(json.dumps({'blocks':block_counts, 'loaded_cells':int(loaded.sum()), 'representation':'cell-centre masks; pallet gap and exact block interfaces not resolved'}, indent=2))
    files = [p for folder in ('0','constant','system') for p in (out/folder).rglob('*') if p.is_file()]
    files += [out/'model_contract.json', out/'transport_input.json']
    (out/'input_hashes.json').write_text(json.dumps({str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=2))
    return model


def read_vector(path, cells):
    source = path.read_text()
    uniform_match = re.search(r'internalField\s+uniform\s*\(([^)]+)\)\s*;', source)
    if uniform_match:
        values = np.tile(np.fromstring(uniform_match[1], sep=' '), (cells, 1))
    else:
        match = re.search(r'internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;', source, re.S)
        if not match or int(match[1]) != cells:
            raise ValueError(f'Invalid vector field: {path}')
        values = np.fromstring(match[2].replace('(', ' ').replace(')', ' '), sep=' ').reshape((-1,3))
    if values.shape != (cells,3) or not np.isfinite(values).all():
        raise ValueError(f'Invalid vector values: {path}')
    return values


def analyse(out, elapsed=None):
    out = Path(out)
    model = json.loads((out/'model_contract.json').read_text())
    spec = json.loads((out/'transport_input.json').read_text())
    cells = model['geometry']['cells']
    times = np.array(sorted(float(p.name) for p in out.iterdir() if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?', p.name)))
    C = np.array([read_field(out/f'{t:g}'/'C', cells) for t in times])
    T = np.array([read_field(out/f'{t:g}'/'T', cells) for t in times])
    U = np.array([read_vector(out/f'{t:g}'/'U', cells) for t in times])
    rows = np.array([[float(x) for x in line.split()[1:]] for line in (out/'log.warehouseBuoyantFoam').read_text().splitlines() if line.startswith('COUPLED ')])
    if len(rows) < 2:
        raise ValueError('Missing solver diagnostics')
    expected = np.arange(round(spec['numerics']['end_s']/spec['numerics']['write_interval_s'])+1)*spec['numerics']['write_interval_s']
    complete = times.shape == expected.shape and np.allclose(times, expected, rtol=0, atol=1e-8) and rows[-1,0] == times[-1]
    balance = float(np.max(abs(rows[:,1]-rows[0,1]))/max(abs(rows[0,1]),1e-30))
    heat_balance = float(abs(rows[-1,2]-rows[-1,3])/max(abs(rows[-1,3]),1.))
    passed = bool(complete and np.isfinite(rows).all() and C.min() >= -1e-14 and balance < 1e-6 and heat_balance < .01 and rows[:,9].max() < 1e-5)
    checks = dict(represented_model=model['kind'], cells=cells, frames=len(times), timeline_complete=bool(complete),
        geometry_basis=spec['geometry_spec']['geometry']['coordinate_basis'], relative_balance_error=balance,
        relative_energy_balance_error=heat_balance, energy_change_J=float(rows[-1,2]*spec['coupled']['rho_kg_m3']*spec['coupled']['cp_J_kg_K']),
        numerical_pass=False, execution_checks_pass=passed, experimental_validation=False,
        simulated_seconds=float(times[-1]), wall_seconds=elapsed, steps=len(rows)-1,
        maximum_speed_m_s=float(rows[:,4].max()), maximum_saved_speed_m_s=float(np.linalg.norm(U,axis=2).max()), temperature_range_C=[float(T.min()-273.15),float(T.max()-273.15)],
        final_temperature_range_C=[float(T[-1].min()-273.15),float(T[-1].max()-273.15)],
        minimum_concentration_kg_m3=float(C.min()), max_divergence_s_inv=float(rows[:,9].max()),
        numerical_validation_scope='execution_mass_energy_balance_only; grid/time/turbulence validation incomplete',
        raw_npz_fields=['C','T','U'], raw_npz_max_difference=0.)
    np.savez_compressed(out/'concentration.npz', times_s=times, concentration=C, concentration_unit='kg/m3',
        temperature_K=T, velocity_m_s=U, cell_centres_m=cell_centres(out/'constant/polyMesh', cells),
        loaded_region=1-read_field(out/'0/freeGas',cells),
        integrated_concentration=np.sum((C[:-1]+C[1:])*.5*np.diff(times)[:,None],axis=0)*1e6,
        integrated_concentration_unit='mg*s/m3')
    # Round-trip check of every exported value against the raw fields just read.
    with np.load(out/'concentration.npz',allow_pickle=False) as saved:
        for name, values in [('concentration',C),('temperature_K',T),('velocity_m_s',U)]:
            if not np.array_equal(saved[name],values):
                raise ValueError('Exported fields differ from original solver fields')
    np.savetxt(out/'coupled_diagnostics.csv',rows,delimiter=',',header='time_s,mass_kg,heat_change_normalized,boundary_heat_normalized,max_speed_m_s,min_T_K,max_T_K,min_C_kg_m3,max_C_kg_m3,max_divergence_s_inv',comments='')
    (out/'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    (out/'state.json').write_text(json.dumps({'status':'complete' if passed else 'failed'}))
    return checks


def execute(spec, out):
    out = Path(out)
    started = time.perf_counter()
    generate(spec, out)
    (out/'state.json').write_text('{"status":"running"}')
    try:
        run_command(out, 'warehouseBuoyantFoam')
        return analyse(out, time.perf_counter()-started)
    except BaseException as error:
        (out/'state.json').write_text(json.dumps({'status':'failed','error':str(error)}))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(json.loads(args.config.read_text()),args.output),indent=2))
