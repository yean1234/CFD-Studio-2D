"""Run a Studio execution from an immutable input snapshot in a fresh folder."""
import argparse
import hashlib
import json
from pathlib import Path
import traceback
import re
import subprocess
import os
import threading
import time
import signal

from cfd_studio.execution_workspace import atomic_json, read_json


def run(job_path):
    job_path = Path(job_path)
    job = read_json(job_path)
    stopped = threading.Event()
    def watch():
        while not stopped.wait(1):
            atomic_json(job_path.with_name('heartbeat.json'), {'time': time.time()})
            if job_path.with_name('stop.json').exists():
                os.kill(os.getpid(), signal.SIGINT)
                return
    threading.Thread(target=watch, daemon=True).start()
    try:
        input_path = job_path.with_name('input.json')
        if hashlib.sha256(input_path.read_bytes()).hexdigest() != job['input_sha256']:
            raise ValueError('실행 설정 스냅샷이 변경되었습니다')
        config = read_json(input_path)
        from .warehouse_coupled import execute, validate
        validate(config)
        job['status'] = 'running'
        atomic_json(job_path, job)
        output = job['output']
        if os.name != 'nt' and re.match(r'^[A-Za-z]:', output):
            output = subprocess.check_output(['wslpath', '-u', output], text=True).strip()
        checks = execute(config, Path(output))
        policy = job.get('termination', {})
        if policy.get('mode') == 'frames':
            count = checks.get('frames', 0) - (0 if policy.get('include_initial') else 1)
            if count != policy['frames']:
                raise ValueError(f'완전 저장 프레임 수 불일치: {count}/{policy["frames"]}')
            job['completion_reason'] = 'frames'
        else:
            job['completion_reason'] = 'time'
        job['saved_frames'] = checks.get('frames')
        job['status'] = 'complete' if checks['execution_checks_pass'] else 'failed'
        if job['status'] == 'failed':
            job['error'] = '실행·보존 검사 미달. 검사 기록을 확인해 주세요.'
        atomic_json(job_path, job)
        return 0 if job['status'] == 'complete' else 1
    except KeyboardInterrupt:
        job.update(status='stopped', error='사용자가 해당 실행을 중단했습니다', completion_reason='stopped')
        atomic_json(job_path, job)
        return 130
    except Exception as error:
        job.update(status='failed', error=str(error))
        atomic_json(job_path, job)
        traceback.print_exc()
        return 1
    finally:
        stopped.set()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().job))
