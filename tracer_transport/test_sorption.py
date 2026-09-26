"""Isolated sorption tests, coupled block transport and complete-state restart tests."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import numpy as np
from .protocol import CRITERIA
from .run import execute, read_field
from .restart import restart


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    root=parser.parse_args().output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    (root/'criteria.json').write_text(json.dumps(CRITERIA,indent=2))
    base=json.loads(Path(__file__).with_name('sorption_test.json').read_text())
    results=[]

    def run(name,params,dt=.005,stop=None):
        result=execute(root/name,20,dt,'porous',params,stop_at=stop)
        results.append(result)
        (root/'summary.json').write_text(json.dumps(results,indent=2))
        if not result['pass']:
            raise RuntimeError(f'Gate failed: {name}; further tests not started')
        return result

    errors=[]
    for dt in [.02,.01,.005]:
        errors.append(run(f'exchange_{dt:g}',base,dt)['sorption_analytic_rmse'])
    if not np.all(np.diff(errors)<0):
        raise RuntimeError('Sorption time refinement failed')
    off={**base,'adsorption':False}
    zero=deepcopy(base);zero['adsorption'].update(k_ads_s_inv=0,k_des_s_inv=0)
    run('off',off);run('zero_rates',zero)
    count=20*4*4
    off_difference=float(np.max(np.abs(read_field(root/'off/2/C',count)-read_field(root/'zero_rates/2/C',count))))
    desorb=deepcopy(base)
    desorb['initial_mean']=0
    desorb['adsorption'].update(k_ads_s_inv=0,k_des_s_inv=.4,initial_bulk_Q=.4)
    run('desorption',desorb)
    irreversible=deepcopy(base);irreversible['adsorption']['k_des_s_inv']=0
    run('irreversible',irreversible)
    block=json.loads(Path(__file__).with_name('block3d_test.json').read_text())
    block['adsorption']=deepcopy(base['adsorption'])
    run('block3d',block)
    run('paused',base,stop=1.)
    # C is valid, but the matching Q is absent: resume must roll back as a unit.
    invalid=root/'paused/1.1';invalid.mkdir()
    shutil.copy2(root/'paused/1/C',invalid/'C')
    resumed=restart(root/'paused',root/'resumed')
    results.append(resumed)
    err_c=float(np.max(np.abs(read_field(root/'exchange_0.005/2/C',count)-read_field(root/'resumed/2/C',count))))
    err_q=float(np.max(np.abs(read_field(root/'exchange_0.005/2/Q',count)-read_field(root/'resumed/2/Q',count))))
    restart_record=json.loads((root/'resumed/restart.json').read_text())
    r={'time_refinement_rmse':errors,'zero_rates_vs_off_max_error':off_difference,
       'restart_C_max_error':err_c,'restart_Q_max_error':err_q,
       'incomplete_Q_rollback':restart_record['anchor_s']==1. and '1.1' in restart_record['skipped_incomplete'],
       'max_total_mass_relative_drift':max(x['mass_relative_drift'] for x in results),
       'cases':len(results)}
    r['pass']=bool(all(x['pass'] for x in results) and off_difference<=CRITERIA['zero_rates_equivalence_max']
                   and max(err_c,err_q)<=CRITERIA['restart_max_abs_difference'] and r['incomplete_Q_rollback'])
    (root/'summary.json').write_text(json.dumps(results,indent=2))
    (root/'sorption_checks.json').write_text(json.dumps(r,indent=2))
    print(json.dumps(r,indent=2))
    if not r['pass']:
        raise RuntimeError('Sorption verification failed')


if __name__=='__main__':
    main()
