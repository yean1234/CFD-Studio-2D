"""Actual solver checks: pulse mass, zero start, restart and steady/time-limit distinction."""
import argparse
import json
from pathlib import Path
import numpy as np
from .run import execute
from .restart import restart


def verify(root):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=False)
    base=json.loads(Path(__file__).with_name('supply_test.json').read_text())
    steady=execute(root/'steady',20,.05,'porous',base)
    assert steady['pass'] and steady['steady_reached'] and 4 < steady['physical_duration_s'] < base['end_s']
    with np.load(root/'steady/concentration.npz') as d:
        assert d['times'][0]==0 and np.all(d['concentration'][0]==0) and np.all(d['sorbed_bulk'][0]==0)
    short={**base,'end_s':6,'termination':{'mode':'time'}}
    full=execute(root/'full',20,.05,'porous',short)
    paused=execute(root/'paused',20,.05,'porous',short,stop_at=1)
    resumed=restart(root/'paused',root/'resumed')
    with np.load(root/'full/concentration.npz') as a,np.load(root/'resumed/concentration.npz') as b:
        error=max(float(np.max(np.abs(a[key]-b[key]))) for key in ['concentration','sorbed_bulk'])
    assert error<1e-10 and full['pass'] and paused['pass'] and resumed['pass']
    cap=execute(root/'time_limit',20,.05,'porous',{**base,'end_s':6})
    assert not cap['pass'] and not cap['steady_reached'] and cap['termination_reason']=='time_limit'
    offgrid=execute(root/'offgrid_pulse',20,.05,'porous',
                    {**short,'source':{**base['source'],'end_s':.123}})
    assert offgrid['pass']
    result={'steady':steady,'restart_max_abs':error,'time_limit_rejected':True,'offgrid_pulse':offgrid,
            'full':full,'resumed':resumed,'pass':True}
    (root/'summary.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    print(json.dumps(verify(parser.parse_args().output),indent=2))
