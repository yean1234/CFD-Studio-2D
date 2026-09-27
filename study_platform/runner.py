"""OpenFOAM 환경에서 불변 입력 한 건을 실행한다. 결과는 실행별로 분리한다."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time

class EnvironmentFailure(RuntimeError):
    pass


def run(folder, resume=None):
    folder = Path(folder).resolve()
    try:
        return _run(folder, resume)
    except Exception as exc:
        category = 'case'
        if (isinstance(exc, (EnvironmentFailure, ImportError, MemoryError))
                or isinstance(exc, OSError) and exc.errno != errno.ENOENT):
            category = 'environment'
        report = {'category': category, 'error': str(exc), 'type': type(exc).__name__}
        try:
            (folder/'failure.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        except OSError:
            # 오류 보고서를 쓰지 못하면 호출 측이 안전하게 대기열을 보류한다.
            pass
        raise


def _run(folder, resume):
    import numpy as np
    from tracer_transport.run import execute
    from tracer_transport.restart import restart
    from tracer_transport.export_studio import export_case

    spec = json.loads((folder/'input.json').read_text(encoding='utf-8'))
    for exe in ('blockMesh', 'checkMesh', 'porousTracerFoam', '/usr/bin/time'):
        if not shutil.which(exe):
            raise EnvironmentFailure(f'{exe} 실행 파일을 찾을 수 없습니다. OpenFOAM 환경을 확인해 주세요')
    solver = Path(shutil.which('porousTracerFoam'))
    environment = {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform(),
                   'openfoam': os.environ.get('WM_PROJECT_VERSION'), 'solver_sha256': hashlib.sha256(solver.read_bytes()).hexdigest(),
                   'cpu_count': os.cpu_count(), 'mpi': False, 'gpu': False}
    (folder/'environment.json').write_text(json.dumps(environment, indent=2))
    started = time.monotonic()
    result = restart(resume, folder/'raw') if resume else execute(folder/'raw', spec['nx'], spec['dt'], spec['kind'], spec['parameters'])
    with np.load(folder/'raw/concentration.npz', allow_pickle=False) as data:
        c, times = data['concentration'], data['times']
        series = c.mean(axis=1)
        metrics = {'version': 'equal_cell_volume_mean_v1', 'unit': 'C/C_ref',
                   'time_unit': 's', 'weighting': 'equal_bulk_cell_volume; not insect exposure',
                   'times': times.tolist(), 'mean_C': series.tolist(),
                   'final_min_C': float(c[-1].min()), 'final_max_C': float(c[-1].max()),
                   'final_mean_C': float(series[-1]), 'physical_end_s': float(times[-1]),
                   'evaluation_window_s': [float(times[0]), float(times[-1])], 'wall_s': time.monotonic()-started}
    (folder/'metrics.json').write_text(json.dumps(metrics, indent=2))
    if result['pass']:
        export_case(folder/'raw', folder/'viewer')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.folder, args.resume)), flush=True)
