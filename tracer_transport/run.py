"""Generate and execute isolated OpenFOAM verification cases, never production cases."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import numpy as np
from .protocol import CRITERIA, contract, fingerprint, sorption_parameters, source_parameters, termination_parameters


def header(name, cls="dictionary"):
    return f'FoamFile {{ version 2.0; format ascii; class {cls}; object {name}; }}\n'


def field(case, name, values, dimensions, vector=False):
    cls = 'volVectorField' if vector else 'volScalarField'
    body = 'internalField uniform (0 0 0);' if vector else (
        f'internalField nonuniform List<scalar>\n{len(values)}\n(\n' +
        '\n'.join(f'{v:.16g}' for v in values) + '\n);')
    (case/'0'/name).write_text(header(name, cls) + f'dimensions [{dimensions}];\n' + body +
                             '\nboundaryField { walls { type zeroGradient; } }\n')


def generate(case, nx, dt, kind, parameters=None):
    parameters = parameters or json.loads(Path(__file__).with_name('benchmark.json').read_text())
    spec = contract(parameters,kind,dt)
    lengths = parameters['lengths_m']
    ny, nz = parameters['transverse_cells']
    lower, upper = parameters['porous_x_fraction']
    if kind not in ('uniform','diffusion','porous'):
        raise ValueError('Unknown case type')
    if any(isinstance(v,bool) or not isinstance(v,int) for v in [nx,ny,nz]):
        raise ValueError('Cell counts must be integers')
    if not all(np.isfinite(parameters[key]) for key in
               ['porosity','D_air_m2_s','K_porous_m2_s','initial_mean',
                'initial_cosine_amplitude','end_s','write_interval_s']):
        raise ValueError('Non-finite benchmark parameters')
    if (len(lengths) != 3 or not all(np.isfinite(v) and v>0 for v in lengths)
            or not 0<parameters['porosity']<=1 or not 0<=lower<upper<=1
            or parameters['D_air_m2_s']<=0 or parameters['K_porous_m2_s']<=0
            or parameters['initial_mean']<abs(parameters['initial_cosine_amplitude'])
            or nx<2 or ny<1 or nz<1 or dt<=0 or parameters['end_s']<=0
            or parameters['write_interval_s']<=0):
        raise ValueError('Invalid benchmark parameters')
    for ratio in [parameters['end_s']/dt, parameters['write_interval_s']/dt,
                  parameters['end_s']/parameters['write_interval_s']]:
        if not np.isclose(ratio, round(ratio), rtol=0, atol=1e-8):
            raise ValueError('End time and output interval must align with each tested dt')
    shape = [nx, ny, nz]
    zz, yy, xxx = np.meshgrid((np.arange(nz)+.5)*lengths[2]/nz,
                             (np.arange(ny)+.5)*lengths[1]/ny,
                             (np.arange(nx)+.5)*lengths[0]/nx,indexing='ij')
    centres=np.column_stack([xxx.ravel(),yy.ravel(),zz.ravel()])
    regions=np.zeros(nx*ny*nz,dtype=int)
    boxes=parameters.get('porous_boxes_m')
    if boxes is None:
        boxes=[{'min':[lower*lengths[0],0,0], 'max':[upper*lengths[0],lengths[1],lengths[2]]}]
    for box in boxes:
        lo=np.asarray(box['min'],dtype=float); hi=np.asarray(box['max'],dtype=float)
        if (lo.shape!=(3,) or hi.shape!=(3,) or not np.isfinite([lo,hi]).all()
                or np.any(lo<0) or np.any(hi>lengths) or np.any(hi<=lo)):
            raise ValueError('Invalid porous box bounds')
        # Interfaces must coincide with cell faces, not silently move with resolution.
        for point in [lo,hi]:
            scaled=point/lengths*shape
            if not np.allclose(scaled,np.round(scaled),rtol=0,atol=1e-8):
                raise ValueError('Porous interfaces must align with mesh faces')
        mask=np.all((centres>=lo)&(centres<hi),axis=1)
        if np.any(regions[mask]):
            raise ValueError('Overlapping porous boxes')
        regions[mask]=1
    if kind=='porous' and not np.any(regions):
        raise ValueError('Porous case needs a resolved porous region')
    source = source_parameters(parameters)
    termination = termination_parameters(parameters)
    source_rate = np.zeros(len(regions))
    if source:
        box = source['box_m']
        lo, hi = np.asarray(box['min'], dtype=float), np.asarray(box['max'], dtype=float)
        if (lo.shape != (3,) or hi.shape != (3,) or not np.isfinite([lo,hi]).all()
                or np.any(lo < 0) or np.any(hi > lengths) or np.any(hi <= lo)):
            raise ValueError('Invalid supply box')
        for point in [lo, hi]:
            if not np.allclose(point/lengths*shape, np.round(point/lengths*shape), rtol=0, atol=1e-8):
                raise ValueError('Supply box must align with cell faces')
        source_mask = np.all((centres >= lo) & (centres < hi), axis=1)
        if not np.any(source_mask) or (kind == 'porous' and np.any(regions[source_mask])):
            raise ValueError('Supply must occupy resolved free-air cells')
        source_rate[source_mask] = source['rate_Cref_per_s']
    if case.exists():
        raise FileExistsError(f'Refusing to replace {case}')
    for d in ['0', 'system', 'constant']:
        (case/d).mkdir(parents=True, exist_ok=True)
    x = (np.arange(nx)+.5)/nx
    xx = np.tile(x, ny*nz)
    eps = np.where(regions==1, parameters['porosity'], 1.) if kind == 'porous' else np.ones_like(xx)
    # All coefficients below are numerical benchmark assumptions, not rice/gas data.
    K = np.where((regions==1)&(kind=='porous'), parameters['K_porous_m2_s'], parameters['D_air_m2_s'])
    c = np.full_like(xx, parameters['initial_mean'])
    if kind != 'uniform':
        c += parameters['initial_cosine_amplitude']*np.cos(math.pi*xx)
    field(case, 'C', c, '0 0 0 0 0 0 0')
    field(case, 'eps', eps, '0 0 0 0 0 0 0')
    field(case, 'K', K, '0 2 -1 0 0 0 0')
    field(case, 'U', None, '0 1 -1 0 0 0 0', True)
    sorption=sorption_parameters(parameters)
    porous=(regions==1)&(kind=='porous')
    field(case,'Q',np.where(porous,sorption['initial_bulk_Q'] if sorption else 0,0),'0 0 0 0 0 0 0')
    for name,key in [('kAds','k_ads_s_inv'),('kDes','k_des_s_inv')]:
        field(case,name,np.where(porous,sorption[key] if sorption else 0,0),'0 0 -1 0 0 0 0')
    field(case, 'sourceRate', source_rate, '0 0 -1 0 0 0 0')
    (case/'constant/transportControl').write_text(header('transportControl') + f'''
sourceEnd {source['end_s'] if source else 0};
steadyEnabled {'true' if termination['mode']=='steady' else 'false'};
relativeRate {termination.get('relative_rate_per_s', 1e-4)};
absoluteRate {termination.get('absolute_rate_per_s', 1e-8)};
holdTime {termination.get('hold_s', 1)};
minimumTime {termination.get('minimum_time_s', 1)};
''')
    lx, ly, lz = lengths
    (case/'system/blockMeshDict').write_text(header('blockMeshDict')+f'''
scale 1;
vertices ((0 0 0)({lx} 0 0)({lx} {ly} 0)(0 {ly} 0)(0 0 {lz})({lx} 0 {lz})({lx} {ly} {lz})(0 {ly} {lz}));
blocks (hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1));
edges ();
boundary (walls {{ type wall; faces ((0 4 7 3)(1 2 6 5)(0 1 5 4)(3 7 6 2)(0 3 2 1)(4 5 6 7)); }});
mergePatchPairs ();
''')
    (case/'system/controlDict').write_text(header('controlDict')+f'''
application porousTracerFoam;
startFrom startTime; startTime 0; stopAt endTime; endTime {parameters['end_s']};
deltaT {dt}; writeControl runTime; writeInterval {parameters['write_interval_s']};
writeFormat ascii; writePrecision 16; timeFormat general; timePrecision 10;
runTimeModifiable false;
''')
    (case/'system/fvSchemes').write_text(header('fvSchemes')+'''
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,C) Gauss upwind; }
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }
''')
    (case/'system/fvSolution').write_text(header('fvSolution')+'''
solvers { C { solver PBiCGStab; preconditioner DILU; tolerance 1e-13; relTol 0; maxIter 2000; } }
''')
    cfg = {**parameters, 'porous_boxes_m':boxes, 'schema': 2, 'kind': kind, 'shape_xyz': shape, 'lengths_m': lengths,
           'dt_s': dt, 'concentration_unit': 'C/C_ref',
           'mass_unit': 'C_ref*m3', 'coordinate_origin_m': [0,0,0],
           'parameter_evidence': 'research_assumption_numerical_benchmark',
           'velocity': 'zero_superficial', 'boundary': 'sealed_no_flux',
           'adsorption': sorption or False, 'bag_resistance': False, 'leakage': False}
    (case/'config.json').write_text(json.dumps(cfg, indent=2))
    (case/'conditions.json').write_text(json.dumps(spec,indent=2))
    (case/'criteria.json').write_text(json.dumps(CRITERIA,indent=2))
    (case/'config.sha256').write_text(fingerprint(cfg)+'\n')
    rows=['# Pre-run conditions','', '| Item | Specification |','|---|---|']
    rows += [f'| {key} | {json.dumps(value,ensure_ascii=False)} |' for key,value in spec.items()]
    (case/'CONDITIONS.md').write_text('\n'.join(rows)+'\n')
    np.save(case/'region_id.npy',regions if kind=='porous' else np.zeros_like(regions))
    names=['config.json','criteria.json','conditions.json','region_id.npy',
           '0/C','0/eps','0/K','0/U','0/Q','0/kAds','0/kDes','0/sourceRate','constant/transportControl',
           'system/blockMeshDict','system/fvSchemes','system/fvSolution']
    manifest={name:hashlib.sha256((case/name).read_bytes()).hexdigest() for name in names}
    (case/'inputs.sha256.json').write_text(json.dumps(manifest,indent=2))
    return cfg, eps, c


def read_field(path, n):
    text = path.read_text()
    if 'boundaryField' not in text or text.count('{')!=text.count('}') or text.count('(')!=text.count(')'):
        raise ValueError(f'Incomplete field: {path}')
    m = re.search(r'internalField\s+uniform\s+([\deE.+-]+)\s*;', text)
    if m:
        value=float(m[1])
        if not np.isfinite(value):
            raise ValueError(f'Non-finite field: {path}')
        return np.full(n, value)
    m = re.search(r'internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;', text, re.S)
    if not m or int(m[1]) != n:
        raise ValueError(f'Invalid field: {path}')
    arr = np.fromstring(m[2], sep=' ')
    if len(arr) != n or not np.isfinite(arr).all():
        raise ValueError(f'Invalid field values: {path}')
    return arr


def run_command(case, command, log_name=None):
    log_path=case/(log_name or f'log.{command}')
    with log_path.open('x') as log:
        process=subprocess.Popen(['/usr/bin/time','-v',command,'-case',str(case)],
                                 stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=process.wait()
        except BaseException:
            import signal
            os.killpg(process.pid,signal.SIGTERM)
            process.wait()
            raise
    if code:
        raise RuntimeError(f'{command} failed ({code}); see {log_path}')


def execute(case, nx, dt, kind, parameters=None, stop_at=None):
    cfg, eps, c0 = generate(case, nx, dt, kind, parameters)
    started = time.perf_counter()
    if stop_at is not None:
        if not 0<stop_at<cfg['end_s'] or not np.isclose(stop_at/cfg['write_interval_s'],round(stop_at/cfg['write_interval_s'])):
            raise ValueError('Stop time must be an intermediate output time')
        control=case/'system/controlDict'
        control.write_text(re.sub(r'endTime\s+[^;]+;',f'endTime {stop_at};',control.read_text()))
    try:
        (case/'state.json').write_text(json.dumps({'status':'running','config_sha256':fingerprint(cfg)}))
        for command in ['blockMesh', 'checkMesh', 'porousTracerFoam']:
            run_command(case,command)
        result=analyse(case,started,stop_at)
        status='paused' if stop_at is not None else 'complete'
        (case/'state.json').write_text(json.dumps({'status':status if result['pass'] else 'failed',
                                                'config_sha256':fingerprint(cfg)}))
        return result
    except BaseException as exc:
        (case/'state.json').write_text(json.dumps({'status':'failed','error':str(exc),
                                                 'config_sha256':fingerprint(cfg)}))
        raise


def analyse(case, started=None, expected_end=None):
    cfg=json.loads((case/'config.json').read_text())
    criteria=json.loads((case/'criteria.json').read_text())
    n=int(np.prod(cfg['shape_xyz']))
    eps=read_field(case/'0/eps',n)
    c0=read_field(case/'0/C',n)
    kind=cfg['kind']
    times = sorted(float(p.name) for p in case.iterdir() if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+)?', p.name))
    fields = np.array([read_field(case/f'{t:g}'/'C', len(eps)) for t in times])
    sorption=cfg.get('adsorption') or None
    adsorbed=np.array([read_field(case/f'{t:g}'/'Q',n) for t in times])
    q0=adsorbed[0]
    region = np.load(case/'region_id.npy',allow_pickle=False)
    np.savez_compressed(case/'concentration.npz', times=times, concentration=fields, sorbed_bulk=adsorbed,
                        region_id=region, porosity=eps, shape_xyz=cfg['shape_xyz'], lengths_m=cfg['lengths_m'])
    mass = fields@eps * np.prod(cfg['lengths_m'])/len(eps)
    logrows = np.array([[float(v) for v in line.split()[1:]] for line in
                        (case/'log.porousTracerFoam').read_text().splitlines() if line.startswith('MASS ')])
    sorbed_rows=np.array([[float(v) for v in line.split()[1:]] for line in
                         (case/'log.porousTracerFoam').read_text().splitlines() if line.startswith('SORBED ')])
    if sorbed_rows.shape!=logrows.shape or not np.allclose(sorbed_rows[:,0],logrows[:,0]):
        raise ValueError('Missing or inconsistent sorption budget log')
    original_mass=float(np.sum(c0*eps+q0)*np.prod(cfg['lengths_m'])/n)
    source = cfg.get('source') if isinstance(cfg.get('source'), dict) else None
    supply_rate = float(read_field(case/'0/sourceRate', n).sum()*np.prod(cfg['lengths_m'])/n) if source else 0.
    supplied = lambda t: np.minimum(np.maximum(np.asarray(t), 0), source['end_s'])*supply_rate if source else np.zeros_like(np.asarray(t))
    log_supply = supplied(logrows[:,0])
    np.savetxt(case/'mass_balance.csv', np.column_stack([logrows[:,0],logrows[:,1],
               log_supply,np.zeros(len(logrows)),sorbed_rows[:,1],logrows[:,1]+sorbed_rows[:,1]-original_mass-log_supply]), delimiter=',',
               header='time_s,gas_Cref_m3,supplied_Cref_m3,outflow_Cref_m3,adsorbed_Cref_m3,balance_error_Cref_m3', comments='')
    exact = cfg['initial_mean']+(c0-cfg['initial_mean'])*np.exp(-cfg['D_air_m2_s']*(np.pi/cfg['lengths_m'][0])**2*times[-1])
    error = float(np.sqrt(np.mean((fields[-1]-exact)**2))) if kind!='porous' and not source else None
    sorption_error=None
    ads_rates=read_field(case/'0/kAds',n)
    des_rates=read_field(case/'0/kDes',n)
    if (sorption and not source and np.allclose(eps,eps[0]) and np.allclose(c0,c0[0]) and np.allclose(q0,q0[0])
            and np.allclose(ads_rates,ads_rates[0]) and np.allclose(des_rates,des_rates[0])):
        a,b=sorption['k_ads_s_inv'],sorption['k_des_s_inv']
        rate=a/eps[0]+b
        if rate>0:
            equilibrium=b*(eps[0]*c0[0]+q0[0])/(a+b*eps[0])
            exact_c=equilibrium+(c0[0]-equilibrium)*np.exp(-rate*np.asarray(times))
        else:
            exact_c=np.full(len(times),c0[0])
        exact_q=eps[0]*c0[0]+q0[0]-eps[0]*exact_c
        sorption_error=float(max(np.sqrt(np.mean((fields-exact_c[:,None])**2)),
                                  np.sqrt(np.mean((adsorbed-exact_q[:,None])**2))))
    total_mass=mass+adsorbed.sum(axis=1)*np.prod(cfg['lengths_m'])/n
    scale=max(abs(original_mass)+float(supplied(times[-1])),1e-15)
    drift = float(max(np.max(np.abs(logrows[:,1]+sorbed_rows[:,1]-original_mass-log_supply)),
                      np.max(np.abs(total_mass-original_mass-supplied(times))))/scale)
    rss = re.search(r'Maximum resident set size \(kbytes\): (\d+)', (case/'log.porousTracerFoam').read_text())
    expected_end=cfg['end_s'] if expected_end is None else expected_end
    log_text=(case/'log.porousTracerFoam').read_text()
    reasons=re.findall(r'^STOP_REASON (steady|time_limit) ([\deE.+-]+)$',log_text,re.M)
    reason, final_time = reasons[-1] if reasons else ('time_limit',str(expected_end))
    steady_requested=(cfg.get('termination') or {}).get('mode')=='steady'
    if reason=='steady':
        expected_end=float(final_time)
    expected_times=np.arange(math.floor(expected_end/cfg['write_interval_s']+1e-8)+1)*cfg['write_interval_s']
    if not np.isclose(expected_times[-1],expected_end,rtol=0,atol=1e-9):
        expected_times=np.append(expected_times,expected_end)
    complete=len(times)==len(expected_times) and np.allclose(times,expected_times,rtol=0,atol=1e-9)
    progress=np.array([[float(v) for v in line.split()[1:]] for line in log_text.splitlines() if line.startswith('PROGRESS ')])
    if progress.size:
        counts=np.searchsorted(times,progress[:,0]+1e-9,side='right')
        np.savetxt(case/'progress.csv',np.column_stack([progress,counts]),delimiter=',',comments='',
                   header='physical_time_s,solver_segment_wall_s,max_C_rate_per_s,max_Q_rate_per_s,mass_relative_error,stable_duration_s,saved_frames_at_step_end')
    segment_text=(case/'log.restart').read_text() if (case/'log.restart').exists() else log_text
    segment_progress=[line.split() for line in segment_text.splitlines() if line.startswith('PROGRESS ')]
    segment_initial=next((float(line.split()[1]) for line in segment_text.splitlines() if line.startswith('MASS ')),0.)
    solver_wall=float(segment_progress[-1][2]) if segment_progress else None
    segment_duration=float(segment_progress[-1][1])-segment_initial if segment_progress else None
    result = {'case':case.name,'cells':len(eps),'elapsed_s':time.perf_counter()-started if started is not None else None,
              'termination_reason':reason,'steady_reached':reason=='steady',
              'physical_duration_s':float(times[-1]-times[0]),'saved_frames':len(times),
              'frame_interval_s':cfg['write_interval_s'],'solver_segment_wall_s':solver_wall,
              'solver_segment_physical_s':segment_duration,
              'physical_seconds_per_wall_second':segment_duration/solver_wall if solver_wall else None,
              'solver_peak_rss_kib': int(rss[1]) if rss else None,
              'mass_relative_drift':drift, 'min_C':float(logrows[:,2].min()),
              'min_Q':float(sorbed_rows[:,2].min()),'sorption_analytic_rmse':sorption_error,
              'analytic_rmse':error, 'output_timeline_complete':bool(complete),
              'pass':bool(complete and (not steady_requested or reason=='steady' or expected_end<cfg['end_s']) and drift<criteria['mass_relative_drift_max']
                          and logrows[:,2].min()>=criteria['minimum_concentration']
                          and sorbed_rows[:,2].min()>=criteria['minimum_concentration']
                          and (sorption_error is None or sorption_error<criteria['sorption_analytic_rmse_max'])
                          and (error is None or error < criteria['analytic_rmse_max'])),
              'output_bytes':sum(p.stat().st_size for p in case.rglob('*') if p.is_file())}
    (case/'checks.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path(__file__).with_name('benchmark.json'))
    p.add_argument('--case',choices=['uniform','diffusion','porous'],help='Run one configured case instead of verification suite')
    p.add_argument('--nx',type=int,default=40)
    p.add_argument('--dt',type=float,default=.005)
    p.add_argument('--stop-at',type=float,help='Planned pause at a complete output checkpoint (single case only)')
    args=p.parse_args()
    if args.stop_at is not None and not args.case:
        p.error('--stop-at requires --case')
    root=args.output.resolve()
    if root.exists():
        raise FileExistsError('Choose a new output folder; previous results are protected')
    for exe in ['blockMesh','checkMesh','porousTracerFoam','/usr/bin/time']:
        if not shutil.which(exe):
            raise RuntimeError(f'{exe} unavailable; source OpenFOAM and build the module first')
    root.mkdir(parents=True)
    env={'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,
         'openfoam':os.environ.get('WM_PROJECT_VERSION'),'cpus':os.cpu_count()}
    (root/'environment.json').write_text(json.dumps(env,indent=2))
    parameters=json.loads(args.config.read_text())
    results=[]
    cases=[('uniform',20,.01),('diffusion',20,.01),('diffusion',40,.01),
                       ('diffusion',80,.01),('diffusion',80,.005),('diffusion',80,.0025),
                       ('porous',20,.01),('porous',40,.005),('porous',80,.0025)]
    if args.case:
        cases=[(args.case,args.nx,args.dt)]
    for kind,nx,dt in cases:
        if kind=='porous' and not args.case:
            spatial=[r['analytic_rmse'] for r in results if r['case'] in ['diffusion_20_0.01','diffusion_40_0.01','diffusion_80_0.01']]
            temporal=[r['analytic_rmse'] for r in results if r['case'] in ['diffusion_80_0.01','diffusion_80_0.005','diffusion_80_0.0025']]
            if not (np.all(np.diff(spatial)<0) and np.all(np.diff(temporal)<0)):
                raise RuntimeError('Stage A refinement gate failed; refusing Stage B')
        result=execute(root/f'{kind}_{nx}_{dt:g}',nx,dt,kind,parameters,args.stop_at)
        results.append(result)
        print(json.dumps(result),flush=True)
        (root/'summary.json').write_text(json.dumps(results,indent=2))
        if not result['pass']:
            raise RuntimeError('Stage gate failed; remaining cases not started')
    (root/'summary.json').write_text(json.dumps(results,indent=2))
    if not all(r['pass'] for r in results):
        raise RuntimeError('Numerical verification failed; inspect summary.json')


if __name__=='__main__':
    main()
