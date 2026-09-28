"""Conservative three-grid comparison for the sealed porous-grain scenario.

Acceptance criteria are explicit numerical targets, not experimental validation.
GCI follows the three-grid constant-ratio monotonic formula in NASA/NPARC's
spatial-convergence tutorial. Non-monotonic or non-decreasing data are rejected.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .porous_warehouse_mesh import generate_mesh,restrict_to_base

CRITERIA={'concentration_relative_L2':.05,'velocity_relative_L2':.05,'temperature_rmse_C':.05,'qoi_GCI_fraction':.05}
SOURCE='https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html'


def signature(spec):
    spec=copy.deepcopy(spec)
    spec['porous_mesh'].pop('refinement')
    spec['coupled'].pop('processes',None)
    return hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()


def gci(coarse,medium,fine,r=2.):
    a=coarse-medium;b=medium-fine
    if abs(a)<1e-14 or abs(b)<1e-14:return {'eligible':False,'reason':'differences too small for observed order'}
    if a*b<=0:return {'eligible':False,'reason':'non_monotonic'}
    p=math.log(abs(a/b))/math.log(r)
    if p<=0:return {'eligible':False,'reason':'differences do not decrease','observed_order':p}
    if p>2.5:return {'eligible':False,'reason':'apparent order exceeds supported spatial scheme; more grids needed','observed_order':p}
    if abs(fine)<1e-14 or abs(medium)<1e-14:return {'eligible':False,'reason':'quantity near zero'}
    gf=1.25*abs(b/fine)/(r**p-1)
    gm=1.25*abs(a/medium)/(r**p-1)
    asymptotic=gm/(r**p*gf)
    return {'eligible':True,'observed_order':p,'fine_GCI_fraction':gf,'asymptotic_ratio':asymptotic,
            'pass':bool(gf<=CRITERIA['qoi_GCI_fraction'] and .85<=asymptotic<=1.15)}


def load(case):
    case=Path(case);spec=json.loads((case/'transport_input.json').read_text());checks=json.loads((case/'checks.json').read_text())
    if not checks.get('execution_checks_pass'):raise ValueError(f'Execution gates failed: {case}')
    if spec['coupled'].get('time_mode')!='fixed':raise ValueError('Fixed time step required')
    if checks.get('maximum_observed_Courant',1)>.5:raise ValueError('CFL limit exceeded')
    with np.load(case/'concentration.npz',allow_pickle=False) as f:
        a={k:f[k] for k in ('times_s','concentration','temperature_K','velocity_m_s','cell_volumes_m3','loaded_region')}
    _,layout=generate_mesh(spec)
    if not np.allclose(a['cell_volumes_m3'],layout['cell_volumes_m3'],rtol=1e-9,atol=1e-9):raise ValueError('Volume layout mismatch')
    a.update(spec=spec,checks=checks,layout=layout,case=case,
             solver_sources=json.loads((case/'model_contract.json').read_text())['solver_sources_sha256'])
    return a


def pair(coarse,fine):
    if fine['spec']['porous_mesh']['refinement']!=2*coarse['spec']['porous_mesh']['refinement']:
        raise ValueError('Expected nested refinement ratio 2')
    v=coarse['cell_volumes_m3']; vf=fine['cell_volumes_m3'];parent=fine['layout']['half_parent']
    mapped_volume=np.bincount(parent,weights=vf,minlength=len(v))
    if not np.allclose(mapped_volume,v,atol=1e-8,rtol=1e-9):raise ValueError('Refined cells do not partition coarse cells')
    background=coarse['spec']['initial']['background_mg_m3']*1e-6
    rows=[]
    for i,t in enumerate(coarse['times_s']):
        if t==0:continue
        C=coarse['concentration'][i];U=coarse['velocity_m_s'][i];T=coarse['temperature_K'][i]
        dc=restrict_to_base(fine['concentration'][i],vf,parent)-C
        du=restrict_to_base(fine['velocity_m_s'][i],vf,parent)-U
        dtemp=restrict_to_base(fine['temperature_K'][i],vf,parent)-T
        cr=float(np.sqrt(np.sum(dc*dc*v)/max(np.sum((C-background)**2*v),1e-50)))
        ur=float(np.sqrt(np.sum(np.sum(du*du,axis=1)*v)/max(np.sum(np.sum(U*U,axis=1)*v),1e-50)))
        tr=float(np.sqrt(np.sum(dtemp*dtemp*v)/v.sum()))
        rows.append({'time_s':float(t),'concentration_relative_L2':cr,'velocity_relative_L2':ur,'temperature_rmse_C':tr})
    worst={k:max(row[k] for row in rows) for k in ('concentration_relative_L2','velocity_relative_L2','temperature_rmse_C')}
    return {'coarse_cells':len(v),'fine_cells':len(vf),'mapping':'exact nested-cell volume-weighted restriction','frames':rows,'worst':worst,
        'pass':all(worst[k]<=CRITERIA[k] for k in worst)}


def assess(cases):
    a=[load(p) for p in cases]
    if [v['spec']['porous_mesh']['refinement'] for v in a]!=[1,2,4]:raise ValueError('Provide r1/r2/r4 in order')
    if len({signature(v['spec']) for v in a})!=1:raise ValueError('Physical/numerical settings differ beyond grid/process count')
    if any(v['solver_sources']!=a[0]['solver_sources'] for v in a):raise ValueError('Solver source versions differ')
    for name in ('fvSchemes','fvSolution'):
        if len({hashlib.sha256((v['case']/'system'/name).read_bytes()).hexdigest() for v in a})!=1:
            raise ValueError('Discretization or linear solver settings differ')
    if any(not np.array_equal(v['times_s'],a[0]['times_s']) for v in a):raise ValueError('Comparison timelines differ')
    bulk=[float(np.sum(v['cell_volumes_m3']*v['loaded_region'])) for v in a]
    mass=[float(np.sum(v['concentration'][0]*v['cell_volumes_m3']*np.where(v['loaded_region'],v['spec']['loading']['porosity'],1.))) for v in a]
    if not np.allclose(bulk,bulk[0],rtol=1e-10) or not np.allclose(mass,mass[0],rtol=1e-9,atol=0):raise ValueError('Grain volume or initial inventory differs')
    qoi={k:[] for k in ('grain_inventory_kg','rms_speed_m_s','mean_cooling_K')}
    for v in a:
        vol=v['cell_volumes_m3'];grain=v['loaded_region'];eps=v['spec']['loading']['porosity']
        qoi['grain_inventory_kg'].append(float(np.sum(v['concentration'][-1]*vol*grain*eps)))
        qoi['rms_speed_m_s'].append(float(np.sqrt(np.sum(np.sum(v['velocity_m_s'][-1]**2,axis=1)*vol)/vol.sum())))
        initial=v['spec']['coupled']['initial_temperature_C']+273.15
        qoi['mean_cooling_K'].append(float(np.sum((initial-v['temperature_K'][-1])*vol)/vol.sum()))
    gcis={k:{'values_coarse_to_fine':values,**gci(*values)} for k,values in qoi.items()}
    pairs=[pair(a[0],a[1]),pair(a[1],a[2])]
    passed=pairs[-1]['pass'] and all(g.get('pass',False) for g in gcis.values())
    return {'cases':[str(v['case']) for v in a],'cells':[len(v['cell_volumes_m3']) for v in a],
        'compared_until_s':float(a[0]['times_s'][-1]),'fixed_dt_s':a[0]['spec']['numerics']['dt_s'],
        'grain_bulk_volumes_m3':bulk,'initial_inventories_kg':mass,'physical_settings_sha256':signature(a[0]['spec']),
        'criteria':CRITERIA,'pairs':pairs,'qoi_GCI':gcis,'grid_converged':bool(passed),
        'scope':'sealed homogenized porous grain, initial 300 s only; not a full-duration or experimental validation',
        'experimental_validation':False,'method_source':SOURCE}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cases',nargs=3,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();report=assess(args.cases)
    with args.output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
