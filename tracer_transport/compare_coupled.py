"""Separate grid and time-control sensitivity, not a convergence certification."""
import argparse
import json
from pathlib import Path
import numpy as np


def load(case):
    with np.load(Path(case)/'concentration.npz',allow_pickle=False) as a:
        return {name:a[name] for name in ('times_s','cell_centres_m','concentration','temperature_K','velocity_m_s')}


def compare(reference,candidate):
    a,b=load(reference),load(candidate)
    end=min(a['times_s'][-1],b['times_s'][-1])
    ai=int(np.flatnonzero(a['times_s']==end)[0]);bi=int(np.flatnonzero(b['times_s']==end)[0])
    xyz,other=a['cell_centres_m'],b['cell_centres_m']
    if np.array_equal(xyz,other):
        indices=np.arange(len(xyz)); distances=np.zeros(len(xyz))
    else:
        indices=np.empty(len(xyz),int)
        # These cases retain identical x resolution. Refuse a different x grid.
        for x in np.unique(xyz[:,0]):
            rows=np.flatnonzero(np.isclose(xyz[:,0],x,rtol=0,atol=1e-9))
            choices=np.flatnonzero(np.isclose(other[:,0],x,rtol=0,atol=1e-9))
            if not len(choices):raise ValueError('Comparison requires matching x columns')
            distance=np.sum((xyz[rows,None,:]-other[None,choices,:])**2,axis=2)
            indices[rows]=choices[np.argmin(distance,axis=1)]
        distances=np.linalg.norm(xyz-other[indices],axis=1)
    delta_c=b['concentration'][bi,indices]-a['concentration'][ai]
    delta_t=b['temperature_K'][bi,indices]-a['temperature_K'][ai]
    delta_u=b['velocity_m_s'][bi,indices]-a['velocity_m_s'][ai]
    background=json.loads((Path(reference)/'transport_input.json').read_text())['initial']['background_mg_m3']*1e-6
    relative_c=float(np.linalg.norm(delta_c)/np.linalg.norm(a['concentration'][ai]-background))
    relative_u=float(np.linalg.norm(delta_u)/np.linalg.norm(a['velocity_m_s'][ai]))
    return {'reference':Path(reference).name,'candidate':Path(candidate).name,'time_s':float(end),
        'mapping':'nearest fine cell in same x column, unweighted L2; not conservative remapping',
        'maximum_mapping_distance_m':float(distances.max()),
        'concentration_rmse_mg_m3':float(np.sqrt(np.mean(delta_c**2))*1e6),
        'concentration_relative_L2_above_background':relative_c,
        'temperature_rmse_C':float(np.sqrt(np.mean(delta_t**2))),
        'velocity_vector_relative_L2':relative_u,
        'reference_final_peak_mg_m3':float(a['concentration'][ai].max()*1e6),
        'candidate_final_peak_mg_m3':float(b['concentration'][bi].max()*1e6),
        'grid_converged':False,'experimental_validation':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--grid',type=Path,required=True);p.add_argument('--time',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report={'grid_sensitivity':compare(args.reference,args.grid),'time_control_sensitivity':compare(args.reference,args.time),
        'caveat':'Grid comparison uses automatic Co-based time steps: dt differs as mesh changes. Loaded-cell masks and discretized initial mass also differ. Not a pure fixed-dt grid convergence or Richardson/GCI study.'}
    with args.output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
