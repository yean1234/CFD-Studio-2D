"""Actual OpenFOAM integration checks; requires built solver on PATH."""
import argparse
import json
from pathlib import Path
import numpy as np
from .protocol import CRITERIA
from .run import execute, generate, read_field, run_command
from .restart import restart


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    root=parser.parse_args().output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    (root/'criteria.json').write_text(json.dumps(CRITERIA,indent=2))
    params=json.loads(Path(__file__).with_name('block3d_test.json').read_text())
    full=execute(root/'continuous',40,.005,'porous',params)
    paused=execute(root/'paused',40,.005,'porous',params,stop_at=.5)
    # Simulate an interrupted write beyond the last complete snapshot, never real data.
    damaged=root/'paused/0.6/C'
    damaged.parent.mkdir()
    damaged.write_text('FoamFile { class volScalarField; }\ninternalField nonuniform List<scalar>\n2560\n(\n1\n')
    resumed=restart(root/'paused',root/'resumed')
    count=2560
    error=float(np.max(np.abs(read_field(root/'continuous/1/C',count)-read_field(root/'resumed/1/C',count))))
    record=json.loads((root/'resumed/restart.json').read_text())
    mismatch=False
    (root/'paused/0/K').write_text((root/'paused/0/K').read_text()+'\n// modified for rejection test\n')
    try:
        restart(root/'paused',root/'must_not_run')
    except ValueError:
        mismatch=not (root/'must_not_run').exists()
    failure=root/'failure_probe';failure.mkdir()
    failure_preserved=False
    try:
        run_command(failure,'/bin/false','log.failure')
    except RuntimeError:
        failure_preserved=(failure/'log.failure').is_file()
    failure_case=root/'solver_failure'
    generate(failure_case,40,.005,'porous',params)
    run_command(failure_case,'blockMesh')
    solution=failure_case/'system/fvSolution'
    solution.write_text(solution.read_text().replace('PBiCGStab','deliberatelyInvalidSolver'))
    solver_failure_preserved=False
    try:
        run_command(failure_case,'porousTracerFoam')
    except RuntimeError:
        solver_failure_preserved='FOAM FATAL' in (failure_case/'log.porousTracerFoam').read_text()
    result={'continuous':full,'paused':paused,'resumed':resumed,
            'restart_max_abs_difference':error,'anchor_s':record['anchor_s'],
            'damaged_checkpoint_skipped':'0.6' in record['skipped_incomplete'],
            'changed_input_rejected':mismatch,'failure_log_preserved':failure_preserved,
            'actual_solver_failure_log_preserved':solver_failure_preserved,
            'source_damaged_checkpoint_preserved':damaged.exists()}
    result['pass']=bool(all(r['pass'] for r in [full,paused,resumed])
                        and error<=CRITERIA['restart_max_abs_difference']
                        and record['anchor_s']==.5 and result['damaged_checkpoint_skipped']
                        and mismatch and failure_preserved and solver_failure_preserved and damaged.exists())
    (root/'restart_checks.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if not result['pass']:
        raise RuntimeError('Restart verification failed')


if __name__=='__main__':
    main()
