"""Run a Studio execution from an immutable input snapshot in a fresh folder."""
import argparse
import hashlib
import json
from pathlib import Path
import traceback
import re
import subprocess
import os

from cfd_studio.execution_workspace import atomic_json, read_json


def run(job_path):
    job_path = Path(job_path)
    job = read_json(job_path)
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
        job['status'] = 'complete' if checks['execution_checks_pass'] else 'failed'
        if job['status'] == 'failed':
            job['error'] = '실행·보존 검사 미달. 검사 기록을 확인해 주세요.'
        atomic_json(job_path, job)
        return 0 if job['status'] == 'complete' else 1
    except Exception as error:
        job.update(status='failed', error=str(error))
        atomic_json(job_path, job)
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().job))
