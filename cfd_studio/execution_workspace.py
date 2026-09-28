"""Project containers and immutable CFD executions; no relocation of old data.

Uses only the standard library so the bundled Windows Python can serve it.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return copy.deepcopy(default)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 80 or any(ord(c) < 32 for c in value):
        raise ValueError('이름은 1~80자로 입력해 주세요')
    return value.strip()


class ExecutionWorkspace:
    def __init__(self, root, project_roots, folder=None, output=None, settings=None, busy=None):
        self.root = Path(root).resolve()
        self.project_roots = project_roots
        self.folder = Path(folder or self.root/'cfd_studio/_runtime/executions')
        self.output = Path(output or self.root/'output')
        self.settings = settings or {}
        self.busy = busy or (lambda: False)
        self.lock = threading.RLock()
        self.processes = {}

    def external_entries(self):
        """Explicitly linked result folders; never scan or relocate their siblings."""
        return read_json(self.folder/'external_results.json', [])

    def external_paths(self):
        return [Path(item['path']) for item in self.external_entries()]

    def restore_external(self, project_name, path):
        """Restore an existing result by reference, preserving all source bytes."""
        project_name = label(project_name)
        path = Path(path).resolve()
        meta = read_json(path/'meta.json', {})
        rid = meta.get('run_id') or meta.get('project_id')
        if not path.is_dir() or not rid or not (path/'case_config.json').is_file():
            raise ValueError('원본 메타데이터와 실행 설정을 확인해 주세요')
        key = 'legacy:' + str(rid)
        with self.lock:
            existing = self.discover().get(key)
            if existing and Path(existing['path']).resolve() != path:
                raise ValueError('같은 실행 ID가 다른 경로에 있습니다')
            data = self._catalog(self.discover())
            project = next((p for p in data['projects'] if p['name'] == project_name), None)
            if project is None:
                project = {'id': uuid.uuid4().hex, 'name': project_name, 'created': time.time(), 'runs': []}
                data['projects'].append(project)
            for p in data['projects']:
                p['runs'] = [r for r in p['runs'] if r != key]
            project['runs'].append(key)
            entries = [e for e in self.external_entries() if Path(e['path']).resolve() != path]
            entries.append({'path': str(path), 'project_id': project['id']})
            atomic_json(self.folder/'projects.json', data)
            atomic_json(self.folder/'external_results.json', entries)
            return {'project_id': project['id'], 'run_key': key}

    def discover(self):
        """Read original artifacts without healing, renaming, or rewriting them."""
        records = {}
        roots = self.project_roots() if callable(self.project_roots) else self.project_roots
        candidates = [(p, None) for base in roots for p in sorted(Path(base).glob('*'))]
        candidates += [(Path(e['path']), e['project_id']) for e in self.external_entries()]
        seen = set()
        for p, project_id in candidates:
            if not p.is_dir() or p.name.startswith('_') or str(p.resolve()).casefold() in seen:
                continue
            seen.add(str(p.resolve()).casefold())
            meta = read_json(p/'meta.json', {})
            rid = str(meta.get('run_id') or meta.get('project_id') or p.name)
            key = 'legacy:' + rid
            if key in records:
                continue
            cfg = read_json(p/'case_config.json', None) or read_json(p/'config.json', {})
            analysis = cfg.get('_해석유형') or ('immersion' if 'tank' in cfg and 'dielectric_fluid' in cfg else 'unknown')
            records[key] = {'id': key, 'kind': 'legacy', 'rid': rid, 'name': meta.get('name') or p.name,
                'path': str(p), 'model': analysis,
                'status': 'complete' if meta.get('completed') else 'saved',
                'created': meta.get('created') or p.stat().st_mtime, 'end_s': meta.get('tmax') or meta.get('end'),
                'has_results': any(p.glob('*.bin')), 'study_attempt_id': meta.get('study_attempt_id')}
            if project_id:
                records[key]['project_id'] = project_id
        for p in sorted(self.output.glob('warehouse_transport_*')):
            if not p.is_dir() or p.is_symlink() or not (p/'model_contract.json').is_file():
                continue
            model = read_json(p/'model_contract.json', {})
            state = read_json(p/'state.json', {})
            checks = read_json(p/'checks.json', {})
            key = 'warehouse:' + p.name
            valid = state.get('status') == 'complete' and bool(checks.get('execution_checks_pass') or checks.get('numerical_pass'))
            records[key] = {'id': key, 'kind': 'warehouse', 'rid': p.name, 'name': p.name,
                'path': str(p), 'model': model.get('kind'), 'status': state.get('status', 'saved'),
                'created': (p/'model_contract.json').stat().st_mtime,
                'end_s': checks.get('simulated_seconds'), 'has_results': valid and (p/'concentration.npz').is_file(),
                'numerical_pass': checks.get('numerical_pass', False), 'experimental_validation': False}
        for p in (self.folder/'runs').glob('*/job.json'):
            job = read_json(p, {})
            key = job['run_key']
            current = records.get(key, {})
            records[key] = {**current, 'id': key, 'kind': 'warehouse', 'rid': Path(job['output']).name,
                'name': job['name'], 'path': job['output'], 'created': job['created'], 'status': job['status'],
                'end_s': job['end_s'], 'project_id': job['project_id'], 'job_id': job['id'],
                'model': 'clo2_coupled_scenario', 'has_results': current.get('has_results', False),
                'error': job.get('error', ''), 'numerical_pass': current.get('numerical_pass', False),
                'experimental_validation': False}
        return records

    def _catalog(self, records):
        path = self.folder/'projects.json'
        data = read_json(path, None)
        if data is None:
            data = {'schema': 1, 'projects': [{'id': uuid.uuid4().hex, 'name': '식량창고', 'created': time.time(), 'runs': []}]}
        if data.get('schema') != 1 or not isinstance(data.get('projects'), list) or not data['projects']:
            raise ValueError('프로젝트 목록 형식을 확인해 주세요')
        before = json.dumps(data, sort_keys=True)
        projects = {p['id']: p for p in data['projects']}
        assigned = {rid for p in projects.values() for rid in p['runs']}
        for key, record in records.items():
            if key not in assigned:
                target = projects.get(record.get('project_id'), data['projects'][0])
                target['runs'].append(key)
        if not path.exists() or json.dumps(data, sort_keys=True) != before:
            atomic_json(path, data)
        return data

    def snapshot(self):
        with self.lock:
            records = self.discover()
            data = self._catalog(records)
            projects = []
            for p in data['projects']:
                runs = sorted((records[k] for k in p['runs'] if k in records), key=lambda r: r['created'], reverse=True)
                projects.append({'id': p['id'], 'name': p['name'], 'created': p['created'], 'runs': runs})
            return {'projects': projects, 'busy': any(r['status'] in ('queued', 'running') for r in records.values())}

    def create_project(self, name):
        with self.lock:
            data = self._catalog(self.discover())
            project = {'id': uuid.uuid4().hex, 'name': label(name), 'created': time.time(), 'runs': []}
            data['projects'].append(project)
            atomic_json(self.folder/'projects.json', data)
            return project

    def rename_project(self, key, name):
        with self.lock:
            data = self._catalog(self.discover())
            project = next((p for p in data['projects'] if p['id'] == key), None)
            if project is None:
                raise ValueError('프로젝트를 찾을 수 없습니다')
            project['name'] = label(name)
            atomic_json(self.folder/'projects.json', data)

    def detail(self, key):
        records = self.discover()
        if key not in records:
            raise ValueError('실행을 찾을 수 없습니다')
        record = records[key]
        p = Path(record['path'])
        if record['kind'] == 'warehouse':
            config = read_json(p/'transport_input.json', {})
            candidates = [p/'log.warehouseBuoyantFoam', p/'log.porousTracerFoam', p/'log.blockMesh']
        else:
            config = read_json(p/'case_config.json', None) or read_json(p/'config.json', {})
            candidates = [p/n for n in ('solver.log', 'log.simpleFoam', 'log.icoReactingMultiphaseInterFoam', 'execution.log')]
            attempt = record.get('study_attempt_id')
            if isinstance(attempt, str) and re.fullmatch('[a-f0-9]{32}', attempt):
                source = self.root/'cfd_studio/Studies/attempts'/attempt
                candidates = [source/'raw/log.porousTracerFoam', source/'execution.log'] + candidates
        if record.get('job_id'):
            folder = self.folder/'runs'/record['job_id']
            config = read_json(folder/'input.json')
            candidates.append(folder/'execution.log')
        available = [q for q in candidates if q.is_file()]
        # Prefer a solver log with actual content over an empty launcher log.
        path = next((q for q in available if q.stat().st_size), None)
        log = ''
        if path:
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size-50000))
                log = stream.read().decode('utf-8', errors='replace')
        return {**record, 'config': config, 'log': log, 'log_source': str(path) if path else None,
                'checks': read_json(p/'checks.json', {}), 'grid': read_json(p/'grid_assessment.json', None)}

    def template(self):
        return read_json(self.root/'tracer_transport/warehouse_porous_convergence.json')

    def _command(self, job_path):
        prefix = []
        root, job = str(self.root), str(job_path.resolve())
        if os.name == 'nt':
            prefix = ['wsl.exe']
            if self.settings.get('wsl_distro'):
                prefix += ['-d', self.settings['wsl_distro']]
            root, job = [subprocess.check_output(prefix+['--exec', 'wslpath', '-u', p.replace('\\', '/')], text=True, encoding='utf-8', timeout=15).strip() for p in (root, job)]
            prefix += ['--exec']
        shell = ('shopt -s nullglob; rcs=(/opt/openfoam*/etc/bashrc /usr/lib/openfoam/openfoam*/etc/bashrc); '
                 '((${#rcs[@]})) || { echo "OpenFOAM 환경 없음"; exit 1; }; source "${rcs[-1]}"; '
                 'cd '+shlex.quote(root)+' || exit 1; '
                 'command -v warehouseBuoyantFoam >/dev/null || wmake tracer_transport/coupled_solver || exit 1; '
                 'exec python3 -m tracer_transport.studio_run --job '+shlex.quote(job))
        return prefix + ['bash', '-c', shell]

    def start(self, project_id, name, config):
        name = label(name)
        # Basic validation on Windows; the solver performs its full check in WSL.
        if not isinstance(config, dict) or not isinstance(config.get('numerics'), dict):
            raise ValueError('계산 설정 형식을 확인해 주세요')
        config = json.loads(json.dumps(config, allow_nan=False))
        n = config['numerics']
        for key in ('end_s', 'dt_s', 'write_interval_s'):
            value = n.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('시간·계산 간격은 양수로 입력해 주세요')
        if n['dt_s'] > n['write_interval_s'] or n['write_interval_s'] > n['end_s']:
            raise ValueError('계산 간격 ≤ 저장 간격 ≤ 종료시간 조건을 확인해 주세요')
        ratio = n['end_s']/n['write_interval_s']
        if not math.isclose(ratio, round(ratio), rel_tol=1e-10):
            raise ValueError('종료시간은 저장 간격의 배수로 입력해 주세요')
        with self.lock:
            snap = self.snapshot()
            if not any(p['id'] == project_id for p in snap['projects']):
                raise ValueError('프로젝트를 선택해 주세요')
            if snap['busy'] or self.busy():
                raise ValueError('진행 중인 계산이 있습니다. 완료 후 새 실행을 시작해 주세요')
            key = uuid.uuid4().hex
            folder = self.folder/'runs'/key
            folder.mkdir(parents=True, exist_ok=False)
            output = self.output/('warehouse_transport_ui_'+key)
            job = {'id': key, 'project_id': project_id, 'name': name, 'created': time.time(),
                   'status': 'queued', 'output': str(output.resolve()), 'end_s': n['end_s'],
                   'run_key': 'warehouse:'+output.name}
            atomic_json(folder/'input.json', config)
            job['input_sha256'] = hashlib.sha256((folder/'input.json').read_bytes()).hexdigest()
            atomic_json(folder/'job.json', job)
            try:
                command = self._command(folder/'job.json')
                log = (folder/'execution.log').open('x', encoding='utf-8')
                try:
                    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
                        start_new_session=os.name != 'nt')
                finally:
                    log.close()
                self.processes[key] = process
                threading.Thread(target=self._wait, args=(folder, process), daemon=True).start()
            except Exception as error:
                job.update(status='failed', error=str(error))
                atomic_json(folder/'job.json', job)
                raise
            return job

    def _wait(self, folder, process):
        code = process.wait()
        with self.lock:
            job = read_json(folder/'job.json')
            if job['status'] in ('queued', 'running'):
                job.update(status='failed', error=f'계산 프로세스 종료 ({code}). 실행 로그를 확인해 주세요.')
                atomic_json(folder/'job.json', job)
            self.processes.pop(job['id'], None)


def get_route(handler, workspace):
    url = urlparse(handler.path)
    if url.path == '/execution_workspace.js':
        handler._send(200, Path(__file__).with_suffix('.js').read_bytes(), 'text/javascript; charset=utf-8')
        return True
    if not url.path.startswith('/api/executions'):
        return False
    try:
        if url.path == '/api/executions':
            result = workspace.snapshot()
        elif url.path == '/api/executions/template':
            result = {'config': workspace.template()}
        elif url.path == '/api/executions/detail':
            result = workspace.detail(parse_qs(url.query).get('id', [''])[0])
        else:
            raise ValueError('알 수 없는 요청입니다')
        handler._json(result)
    except (ValueError, OSError, KeyError) as error:
        handler._json({'ok': False, 'msg': str(error)}, 400)
    return True


def post_route(handler, workspace, body):
    path = urlparse(handler.path).path
    if not path.startswith('/api/executions'):
        return False
    try:
        if not isinstance(body, dict):
            raise ValueError('요청 형식을 확인해 주세요')
        if path == '/api/executions/project':
            result = workspace.create_project(body.get('name'))
        elif path == '/api/executions/rename':
            workspace.rename_project(body.get('id'), body.get('name'))
            result = {}
        elif path == '/api/executions/start':
            result = workspace.start(body.get('project_id'), body.get('name'), body.get('config'))
        else:
            raise ValueError('알 수 없는 요청입니다')
        handler._json({'ok': True, 'result': result})
    except (ValueError, OSError, KeyError, TypeError) as error:
        handler._json({'ok': False, 'msg': str(error)}, 400)
    return True
