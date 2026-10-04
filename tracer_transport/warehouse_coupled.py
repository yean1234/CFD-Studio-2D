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
from .warehouse_symmetry import symmetry_domain, patch_names, clipped_blocks, apply_field_boundaries
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
    if c.get('time_mode', 'adaptive') not in ('adaptive', 'fixed'):
        raise ValueError('Unknown time mode')
    if c.get('advection_scheme', 'upwind') not in ('upwind', 'bounded_high_order'):
        raise ValueError('Unknown advection scheme')
    if type(c.get('processes',1)) is not int or not 1 <= c.get('processes',1) <= 8:
        raise ValueError('Use 1..8 solver processes')
    if 'porous_mesh' in spec:
        from .porous_warehouse_mesh import layout
        *_, count = layout(spec)
        geometry.update(cells=count, mesher='grain_boundary_aligned', mesh_only=False, transport_ready=True)
    domain = symmetry_domain(spec)
    if domain:
        geometry['volume_m3'] *= domain['volume_fraction']
        geometry['computational_domain'] = domain
    return geometry


def uniform(out, name, value, dims, boundary, vector=False, patches=PATCHES):
    cls = 'volVectorField' if vector else 'volScalarField'
    patches = '\n'.join(f'{p} {{ {boundary} }}' for p in patches)
    (out/'0'/name).write_text(header(name, cls)+f'dimensions [{dims}];\ninternalField uniform {value};\nboundaryField {{\n{patches}\n}}\n')


def generate(spec, out):
    geometry = validate(spec)
    patches = patch_names(spec, PATCHES)
    blocks = clipped_blocks(spec)
    out = Path(out)
    build(spec['geometry_spec'], out, check=False)
    mesh_data = None
    if 'porous_mesh' in spec:
        from .porous_warehouse_mesh import generate_mesh
        mesh_dictionary, mesh_data = generate_mesh(spec)
        (out/'system/blockMeshDict').write_text(mesh_dictionary)
        np.savez_compressed(out/'mesh_layout.npz', **mesh_data)
        (out/'geometry_report.json').write_text(json.dumps(geometry,indent=2))
    (out/'0').mkdir()
    (out/'state.json').write_text('{"status":"preparing"}')
    for command in ('blockMesh', 'checkMesh'):
        run_command(out, command)
    quality = checked_mesh_quality((out/'log.checkMesh').read_text(), geometry['cells'], geometry['volume_m3'],
                                   extra_patches=tuple(p for p in patches if p not in PATCHES))
    (out/'mesh_quality.json').write_text(json.dumps(quality, indent=2))
    centres = mesh_data['cell_centres_m'] if mesh_data is not None else cell_centres(out/'constant/polyMesh', geometry['cells'])
    loaded = np.zeros(len(centres), bool)
    block_counts = []
    for block in blocks:
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
    if mesh_data is not None:
        from .porous_warehouse_mesh import initial_average
        concentration = initial_average(spec,mesh_data)
        if not np.array_equal(loaded,mesh_data['loaded_region'].astype(bool)):
            raise ValueError('Grain regions disagree with aligned mesh')
        ideal_volume=sum(float(np.prod(np.asarray(b['max_m'])-b['min_m'])) for b in blocks)
        if not np.isclose(mesh_data['cell_volumes_m3'][loaded].sum(),ideal_volume,rtol=1e-12):
            raise ValueError('Grain volume differs from physical block envelopes')
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
        write_scalar(out/'0', name, values, dims, patches)
    temp = c['initial_temperature_C']+273.15
    table = ' '.join(f'({t:g} {v+273.15:.12g})' for t, v in zip(spec['temperature']['times_s'], spec['temperature']['values_C']))
    boundaries = []
    for p in patches:
        # The annex interface and floor are insulated scenario boundaries.
        if p in ('floor', 'annexInterface', 'symmetryPlane'):
            bc = 'type zeroGradient;'
        else:
            bc = f'''type externalWallHeatFluxTemperature; mode coefficient;
                Ta table ({table}); h uniform {c['envelope_h_W_m2_K']};
                kappaMethod lookup; kappa kappa; value uniform {temp};'''
        boundaries.append(f'{p} {{ {bc} }}')
    (out/'0/T').write_text(header('T', 'volScalarField') +
        f'dimensions [0 0 0 1 0 0 0];\ninternalField uniform {temp};\nboundaryField {{'+ '\n'.join(boundaries)+'}\n')
    uniform(out, 'U', '(0 0 0)', '0 1 -1 0 0 0 0', 'type fixedValue; value uniform (0 0 0);', True, patches=patches)
    uniform(out, 'p_rgh', 0, '0 2 -2 0 0 0 0', 'type fixedFluxPressure; value uniform 0;', patches=patches)
    uniform(out, 'k', c['initial_k_m2_s2'], '0 2 -2 0 0 0 0', f"type kqRWallFunction; value uniform {c['initial_k_m2_s2']};", patches=patches)
    uniform(out, 'epsilon', c['initial_epsilon_m2_s3'], '0 2 -3 0 0 0 0', f"type epsilonWallFunction; value uniform {c['initial_epsilon_m2_s3']};", patches=patches)
    uniform(out, 'nut', 0, '0 2 -1 0 0 0 0', 'type nutkWallFunction; value uniform 0;', patches=patches)
    uniform(out, 'alphat', 0, '0 2 -1 0 0 0 0', f"type alphatJayatillekeWallFunction; Prt {c['Prt']}; value uniform 0;", patches=patches)
    if symmetry_domain(spec):
        apply_field_boundaries(out/'0')
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
deltaT {n['dt_s']}; adjustTimeStep {'no' if c.get('time_mode') == 'fixed' else 'yes'}; maxCo {c['max_Co']}; maxDeltaT {c['max_dt_s']};
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
    if c.get('advection_scheme') == 'bounded_high_order':
        path=out/'system/fvSchemes'
        path.write_text(path.read_text().replace('div(phi,U) Gauss upwind','div(phi,U) Gauss linearUpwind grad(U)')
                        .replace('div(phi,T) Gauss upwind','div(phi,T) Gauss limitedLinear 1')
                        .replace('div(phi,C) Gauss upwind','div(phi,C) Gauss vanLeer'))
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
    if 'porous_mesh' in spec:
        from .porous_warehouse_mesh import mesh_plan
        model['mesh_plan'] = mesh_plan(spec)
    model['computational_domain'] = symmetry_domain(spec)
    model['loading'] = dict(spec['loading'], blocks=blocks)
    model['coordinate_representation'] = 'arithmetic_mean_of_six_face_centres; approximate_hexahedral_representative_point'
    model['leakage'] = 'excluded; sealed impermeable gas boundaries'
    model['porous_grain'] = 'homogenized grain-stack envelopes; effective porosity, Darcy resistance and LTE heat storage; individual bag membranes unresolved'
    if mesh_data is not None:
        model['coordinate_representation']='exact_volume_centres_checked_against_OpenFOAM'
        model['initial_field_representation']='finite_volume_average_of_same_gaussian'
    source = Path(__file__).parent/'coupled_solver'
    model['solver_sources_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.suffix in ('.C','.H')}
    (out/'model_contract.json').write_text(json.dumps(model, ensure_ascii=False, indent=2))
    (out/'transport_input.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    loading_report={'blocks':block_counts, 'loaded_cells':int(loaded.sum()), 'representation':'cell-centre masks; pallet gap and exact block interfaces not resolved'}
    if mesh_data is not None:
        loading_report.update(representation='mesh faces aligned to homogenized grain envelopes; pallet air gap resolved',
            grain_bulk_volume_m3=float(mesh_data['cell_volumes_m3'][loaded].sum()),
            grain_pore_volume_m3=float((mesh_data['cell_volumes_m3'][loaded]*eps[loaded]).sum()),
            initial_inventory_kg=float(np.sum(concentration*eps*mesh_data['cell_volumes_m3'])))
    (out/'loading_report.json').write_text(json.dumps(loading_report, indent=2))
    if c.get('processes',1)>1:
        (out/'system/decomposeParDict').write_text(header('decomposeParDict')+f'numberOfSubdomains {c["processes"]}; method scotch;\n')
    files = [p for folder in ('0','constant','system') for p in (out/folder).rglob('*') if p.is_file()]
    files += [out/'model_contract.json', out/'transport_input.json']
    if mesh_data is not None:files.append(out/'mesh_layout.npz')
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
    directories=sorted((p for p in out.iterdir() if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?',p.name)),key=lambda p:float(p.name))
    times=np.array([float(p.name) for p in directories])
    C = np.array([read_field(p/'C', cells) for p in directories])
    T = np.array([read_field(p/'T', cells) for p in directories])
    U = np.array([read_vector(p/'U', cells) for p in directories])
    rows = np.array([[float(x) for x in line.split()[1:]] for line in (out/'log.warehouseBuoyantFoam').read_text().splitlines() if line.startswith('COUPLED ')])
    if len(rows) < 2:
        raise ValueError('Missing solver diagnostics')
    expected = np.arange(round(spec['numerics']['end_s']/spec['numerics']['write_interval_s'])+1)*spec['numerics']['write_interval_s']
    complete = times.shape == expected.shape and np.allclose(times, expected, rtol=0, atol=1e-8) and np.isclose(rows[-1,0],times[-1],rtol=0,atol=1e-7)
    if complete:times=expected.astype(float)
    (out/'frame_sources.json').write_text(json.dumps([{'time_s':float(t),'directory':p.name} for t,p in zip(times,directories)],indent=2))
    balance = float(np.max(abs(rows[:,1]-rows[0,1]))/max(abs(rows[0,1]),1e-30))
    heat_balance = float(abs(rows[-1,2]-rows[-1,3])/max(abs(rows[-1,3]),1.))
    centres=cell_centres(out/'constant/polyMesh',cells)
    volumes=None
    if 'porous_mesh' in spec:
        centres=read_vector(out/'0/cellCentres',cells)
        volumes=read_field(out/'0/cellVolumes',cells)
        with np.load(out/'mesh_layout.npz',allow_pickle=False) as layout:
            if not np.allclose(centres,layout['cell_centres_m'],atol=1e-8,rtol=0) or not np.allclose(volumes,layout['cell_volumes_m3'],atol=1e-9,rtol=1e-9):
                raise ValueError('OpenFOAM geometry differs from analytical mesh layout')
    courants=[float(v) for v in re.findall(r'Courant Number mean: [\deE.+-]+ max: ([\deE.+-]+)',(out/'log.warehouseBuoyantFoam').read_text())]
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
    checks['maximum_observed_Courant']=max(courants) if courants else None
    clocks=re.findall(r'ClockTime = ([\deE.+-]+) s',(out/'log.warehouseBuoyantFoam').read_text())
    checks['solver_clock_seconds']=float(clocks[-1]) if clocks else None
    if spec['coupled'].get('time_mode')=='fixed' and (not courants or max(courants)>spec['coupled']['max_Co']*1.01):
        checks['execution_checks_pass']=False
        passed=False
    np.savez_compressed(out/'concentration.npz', times_s=times, concentration=C, concentration_unit='kg/m3',
        temperature_K=T, velocity_m_s=U, cell_centres_m=centres,
        loaded_region=1-read_field(out/'0/freeGas',cells),
        integrated_concentration=np.sum((C[:-1]+C[1:])*.5*np.diff(times)[:,None],axis=0)*1e6,
        integrated_concentration_unit='mg*s/m3', **({'cell_volumes_m3':volumes} if volumes is not None else {}))
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
        processes=spec['coupled'].get('processes',1)
        if processes==1:
            run_command(out, 'warehouseBuoyantFoam')
        else:
            run_command(out,'decomposePar')
            run_arguments(out,['mpirun','-np',str(processes),'warehouseBuoyantFoam','-parallel','-case',str(out.resolve())],'log.warehouseBuoyantFoam')
            run_arguments(out,['reconstructPar','-case',str(out.resolve()),'-noZero'],'log.reconstructPar')
            reconstruct_geometry(out,processes)
        return analyse(out, time.perf_counter()-started)
    except BaseException as error:
        (out/'state.json').write_text(json.dumps({'status':'failed','error':str(error)}))
        raise


def run_arguments(out, arguments, log_name):
    import subprocess
    import os
    import signal
    with (out/log_name).open('x') as log:
        process=subprocess.Popen(arguments,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=process.wait()
        except BaseException:
            os.killpg(process.pid,signal.SIGTERM)
            process.wait()
            raise
    if code:raise RuntimeError(f'{arguments[0]} failed; inspect {out/log_name}')


def reconstruct_geometry(out,processes):
    """Assemble solver cell geometry via OpenFOAM's exact cellProcAddressing.

    mesh.C() snapshots contain sliced patch fields, which reconstructPar cannot
    instantiate. Only internal cell geometry is required, so use its addressing.
    """
    from .mesh_centres import mesh_list
    out=Path(out)
    cells=json.loads((out/'model_contract.json').read_text())['geometry']['cells']
    centres=np.zeros((cells,3));volumes=np.zeros(cells);seen=np.zeros(cells,dtype=int)
    sources={}
    for rank in range(processes):
        proc=out/f'processor{rank}'
        addressing=proc/'constant/polyMesh/cellProcAddressing'
        n,body=mesh_list(addressing);indices=np.fromstring(body,sep=' ',dtype=int)
        if len(indices)!=n or np.any(indices<0) or np.any(indices>=cells):
            raise ValueError('Invalid OpenFOAM cell addressing')
        centres[indices]=read_vector(proc/'0/cellCentres',n)
        volumes[indices]=read_field(proc/'0/cellVolumes',n)
        np.add.at(seen,indices,1)
        for p in (addressing,proc/'0/cellCentres',proc/'0/cellVolumes'):
            sources[str(p.relative_to(out))]=hashlib.sha256(p.read_bytes()).hexdigest()
    if not np.all(seen==1) or not np.all(volumes>0):raise ValueError('Incomplete/duplicate cell geometry')
    spec = json.loads((out/'transport_input.json').read_text())
    patches = patch_names(spec, PATCHES)
    write_scalar(out/'0','cellVolumes',volumes,'0 3 0 0 0 0 0',patches)
    body='\n'.join('('+' '.join(f'{v:.16g}' for v in row)+')' for row in centres)
    bcs='\n'.join(p+' { type '+('symmetryPlane' if p=='symmetryPlane' else 'zeroGradient')+'; }' for p in patches)
    (out/'0/cellCentres').write_text(header('cellCentres','volVectorField')+f'dimensions [0 1 0 0 0 0 0];\ninternalField nonuniform List<vector> {cells} (\n{body}\n);\nboundaryField {{ {bcs} }}\n')
    if symmetry_domain(spec):
        apply_field_boundaries(out/'0')
    (out/'geometry_export_sources.json').write_text(json.dumps(sources,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--refinement', type=int, help='Override aligned-grain mesh refinement')
    parser.add_argument('--processes', type=int, help='Override CPU process count (1..8)')
    args = parser.parse_args()
    spec=json.loads(args.config.read_text())
    if args.processes is not None:spec['coupled']['processes']=args.processes
    if args.refinement is not None:
        if 'porous_mesh' not in spec:parser.error('--refinement requires an aligned porous mesh config')
        spec['porous_mesh']['refinement']=args.refinement
    print(json.dumps(execute(spec,args.output),indent=2))
