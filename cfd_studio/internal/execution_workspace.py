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
import struct
import subprocess
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse
from zipfile import BadZipFile
from cfd_studio.solver_catalog import config_solver, result_axis


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


def result_logs(root, config):
    """Prefer the configured solver, then available solver logs, then setup logs."""
    root = Path(root)
    solver = config_solver(config)
    preferred = [root/('log.'+solver)] if solver and re.fullmatch(r'[A-Za-z0-9_+-]+', solver) else []
    setup = {'log.blockMesh', 'log.checkMesh', 'log.snappyHexMesh', 'log.decomposePar', 'log.reconstructPar'}
    logs = sorted(root.glob('log.*'), key=lambda p: (p.name in setup, p.name))
    candidates = preferred + [root/'solver.log'] + [p for p in logs if p.name not in setup] + [root/'execution.log'] + [p for p in logs if p.name in setup]
    return list(dict.fromkeys(p for p in candidates if not p.is_symlink()))


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 80 or any(ord(c) < 32 for c in value):
        raise ValueError('이름은 1~80자로 입력해 주세요')
    return value.strip()


def config_kind(config):
    if not isinstance(config, dict):
        raise ValueError('설정은 JSON 객체여야 합니다')
    if 'coupled' in config and 'numerics' in config:
        return 'warehouse'
    if config.get('_해석유형') == 'grain_silo':
        return 'grain_silo'
    if 'tank' in config and 'dielectric_fluid' in config:
        return 'immersion'
    return 'unsupported'


def validate_settings(config):
    json.dumps(config, allow_nan=False)
    def check(value, path='설정'):
        if value is None:
            raise ValueError(path+' 값을 입력해 주세요')
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r'(^|_)(provenance|source|sources|reference|references|citation|citations|evidence|basis|sha256)($|_)', key, re.I) or key in ('unresolved', 'assumptions', 'study', 'solver_options', 'published_numerics'):
                    continue
                check(item, path+'.'+key)
        elif isinstance(value, list):
            for i, item in enumerate(value): check(item, path+f'[{i}]')
    check(config)
    kind = config_kind(config)
    if kind == 'warehouse':
        for section in ('numerics', 'coupled', 'geometry_spec', 'loading', 'initial', 'temperature'):
            if not isinstance(config.get(section), dict):
                raise ValueError('설정 항목 누락: '+section)
        for key in ('end_s', 'dt_s', 'write_interval_s'):
            value = config['numerics'].get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('계산 시간과 간격을 양수로 입력해 주세요')
    elif kind in ('immersion', 'grain_silo'):
        from cfd_studio.config_presets import validate_numerics
        validate_numerics(config)
    else:
        raise ValueError('새 실행을 지원하지 않는 설정입니다')
    return kind


from cfd_studio.run_management import RunManagement
from cfd_studio.project_storage import ProjectStorage, project_path


from cfd_studio.cfd_forms import CFDForms


class ExecutionWorkspace(ProjectStorage, RunManagement, CFDForms):
    def __init__(self, root, project_roots, folder=None, output=None, settings=None, busy=None, live=None):
        self.root = Path(root).resolve()
        self.project_roots = project_roots
        self.folder = Path(folder or self.root/'cfd_studio/_runtime/executions').resolve()
        self.output = Path(output or self.root/'output').resolve()
        self.settings = settings or {}
        self.busy = busy or (lambda: False)
        self.live = live or (lambda: {})
        self.lock = threading.RLock()
        self.processes = {}
        from cfd_studio.result_series import ResultSeries
        self.series = ResultSeries(self)
        from cfd_studio.csv_export import CSVExports
        self.csv_exports = CSVExports(self.series)

    def external_entries(self):
        """Explicitly linked result folders; never scan or relocate their siblings."""
        return read_json(self.folder/'external_results.json', [])

    def external_paths(self):
        return [project_path(item['path']) for item in self.external_entries()]

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
            self.persist_catalog(data)
            atomic_json(self.folder/'external_results.json', entries)
            return {'project_id': project['id'], 'run_key': key}

    def discover(self):
        """Read original artifacts without healing, renaming, or rewriting them."""
        records = {}
        roots = self.project_roots() if callable(self.project_roots) else self.project_roots
        candidates = [(p, None) for base in roots for p in sorted(Path(base).glob('*'))]
        candidates = [(Path(e['path']), e['project_id']) for e in self.managed_result_entries() if e['kind'] == 'legacy'] + candidates
        candidates += [(project_path(e['path']), e['project_id']) for e in self.external_entries()]
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
                'has_results': any(p.glob('*.bin')), 'study_attempt_id': meta.get('study_attempt_id'),
                'last_saved': meta.get('tmax'), 'completion_reason': meta.get('completion_reason'),
                'time_unit': '회' if result_axis(cfg) == 'iteration' else 's', 'result_status': 'ready' if any(p.glob('*.bin')) else 'none',
                'numerical_status': 'unchecked'}
            if project_id:
                records[key]['project_id'] = project_id
        warehouse_paths = [Path(e['path']) for e in self.managed_result_entries() if e['kind'] == 'warehouse'] + sorted(self.output.glob('warehouse_transport_*'))
        for p in warehouse_paths:
            if not p.is_dir() or p.is_symlink() or not (p/'model_contract.json').is_file():
                continue
            model = read_json(p/'model_contract.json', {})
            state = read_json(p/'state.json', {})
            checks = read_json(p/'checks.json', {})
            key = 'warehouse:' + p.name
            if key in records:
                continue
            valid = state.get('status') == 'complete' and bool(checks.get('execution_checks_pass') or checks.get('numerical_pass'))
            records[key] = {'id': key, 'kind': 'warehouse', 'rid': p.name, 'name': p.name,
                'path': str(p), 'model': model.get('kind'), 'status': state.get('status', 'saved'), 'error': state.get('error', ''),
                'created': (p/'model_contract.json').stat().st_mtime,
                'end_s': checks.get('simulated_seconds'), 'has_results': valid and (p/'concentration.npz').is_file(),
                'numerical_pass': checks.get('numerical_pass', False), 'experimental_validation': False,
                'last_saved': checks.get('simulated_seconds'), 'frames': checks.get('frames'),
                'result_status': 'ready' if valid and (p/'concentration.npz').is_file() else 'none',
                'numerical_status': 'passed' if checks.get('numerical_pass') else 'incomplete' if checks else 'unchecked'}
        job_paths = list((self.folder/'runs').glob('*/job.json'))
        for project in self.stored_projects():
            if project.get('storage_path'):
                job_paths += list(project_path(project['storage_path']).glob('Cases/*/Attempts/*/job.json'))
        for p in job_paths:
            job = read_json(p, {})
            if job.get('case_id'):
                continue
            key = job['run_key']
            current = records.get(key, {})
            records[key] = {**current, 'id': key, 'kind': 'warehouse', 'rid': Path(job['output']).name,
                'name': job['name'], 'path': current.get('path', job['output']), 'created': job['created'], 'status': job['status'],
                'end_s': job['end_s'], 'project_id': job['project_id'], 'job_id': job['id'], 'job_path': str(p),
                'model': 'clo2_coupled_scenario', 'has_results': current.get('has_results', False),
                'error': job.get('error', ''), 'numerical_pass': current.get('numerical_pass', False),
                'experimental_validation': False}
        live = self.live()
        active = records.get('legacy:'+str(live.get('rid', '')))
        if active and live.get('running'):
            active['status'] = 'running'
        q = self.queue_data()
        attached = {c.get('result_key') for c in q['cases'].values()}
        for c in q['cases'].values():
            records[c['id']] = self.case_record(c, records)
        for key in attached:
            records.pop(key, None)
        return records

    def _catalog(self, records):
        path = self.folder/'projects.json'
        data = read_json(path, None)
        if data is None:
            data = {'schema': 1, 'projects': []}
        if data.get('schema') != 1 or not isinstance(data.get('projects'), list):
            raise ValueError('프로젝트 목록 형식을 확인해 주세요')
        before = json.dumps(data, sort_keys=True)
        if records and not data['projects']:
            data['projects'].append({'id': uuid.uuid4().hex, 'name': '가져온 결과', 'created': time.time(), 'runs': []})
        projects = {p['id']: p for p in data['projects']}
        assigned = {rid for p in projects.values() for rid in p['runs']}
        for key, record in records.items():
            if key not in assigned:
                target = projects.get(record.get('project_id'), data['projects'][0])
                target['runs'].append(key)
        for project in data['projects']:
            links = project.setdefault('linked_results', [])
            known = {str(project_path(i['path'])) for i in links if i.get('external')}
            storage = project_path(project['storage_path']) if project.get('storage_path') else None
            for key in project['runs']:
                record = records.get(key, {})
                if not record.get('path') or key.startswith('case:'):
                    continue
                result_path = project_path(record['path'])
                if storage and result_path.is_relative_to(storage):
                    continue
                if str(result_path) not in known:
                    links.append({'kind': record['kind'], 'path': str(result_path), 'external': True})
                    known.add(str(result_path))
        if not path.exists() or json.dumps(data, sort_keys=True) != before or any(not p.get('storage_path') for p in data['projects']):
            self.persist_catalog(data)
        return data

    def snapshot(self):
        with self.lock:
            records = self.discover()
            data = self._catalog(records)
            projects = []
            for p in data['projects']:
                runs = sorted(({**records[k], 'project_id': p['id']} for k in p['runs'] if k in records), key=lambda r: r['created'], reverse=True)
                projects.append({'id': p['id'], 'name': p['name'], 'description': p.get('description', ''), 'default_preset': p.get('default_preset'), 'form_id': self.project_form(p, records), 'initial_config': copy.deepcopy(p.get('initial_config')), 'created': p['created'], 'storage_path': p.get('storage_path', ''), 'storage_available': bool(p.get('storage_path') and project_path(p['storage_path']).is_dir()), 'runs': runs})
            return {'projects': projects, 'queue': self.queue_summary(), 'busy': bool(self.busy()) or any(r['status'] in ('queued', 'running') and not r['id'].startswith('case:') or r['status'] == 'running' for r in records.values())}

    def result_progress(self, project_id):
        records = self.discover()
        project = next((p for p in self._catalog(records)['projects'] if p['id'] == project_id), None)
        if project is None:
            raise ValueError('프로젝트를 찾을 수 없습니다')
        rows = []
        for key in project['runs']:
            if key not in records:
                continue
            record = records[key]
            try:
                info = self.result_info(record) if record.get('path') and getattr(self, 'result_info', None) else {}
                value = {**record, **info}
                extract = value.get('extract') or {}
                state = value.get('result_status', 'none')
                active = state == 'preparing' or bool(extract.get('busy'))
                failed = bool(extract.get('failed'))
                total = max(0, int(extract.get('total') or 0))
                done = max(0, int(extract.get('done') or 0))
                percent = min(99, int(100*done/total)) if total else None
                if state == 'ready' and not active and not failed:
                    percent, text = 100, '준비됨'
                elif active:
                    text = '변환 중' if total else '확인 중'
                elif failed:
                    text = '일부 실패'
                elif state == 'update':
                    percent, text = None, '업데이트 필요'
                else:
                    percent, text = 0, '결과 없음'
                rows.append({'id': key, 'percent': percent, 'label': text, 'active': active,
                             'error': str(extract.get('last_error') or '') if failed else ''})
            except (ValueError, OSError, KeyError, BadZipFile, EOFError) as error:
                rows.append({'id': key, 'percent': None, 'label': '확인 실패', 'active': False, 'error': str(error)})
        return {'project_id': project_id, 'runs': rows}

    def create_project(self, name, description='', default_preset=None, storage_path=None, form_id=None, initial_config=None, preset_name=None):
        with self.lock:
            data = self._catalog(self.discover())
            if not isinstance(description, str) or len(description) > 4000:
                raise ValueError('프로젝트 설명은 4,000자 이내로 입력하세요')
            if default_preset:
                self.template(default_preset)
            if form_id:
                self.check_form_preset(form_id, default_preset)
            project = {'form_id': form_id, 'id': uuid.uuid4().hex, 'name': label(name), 'description': description, 'default_preset': default_preset, 'created': time.time(), 'runs': []}
            if initial_config is not None:
                if not form_id:raise ValueError('CFD Template을 선택하세요')
                self.check_project_config(form_id,initial_config)
                project['initial_config']=copy.deepcopy(initial_config)
            elif form_id and self.form(form_id).get('definition_only') and not default_preset:
                raise ValueError('프로젝트 Config를 입력하세요')
            saved=None
            try:
                if preset_name:
                    if initial_config is None:raise ValueError('프리셋에 저장할 Config를 입력하세요')
                    saved=self.save_scoped_preset(preset_name,initial_config,form_id)
                    project['default_preset']=saved['id']
                self.prepare_project_folder(project, storage_path)
                data['projects'].append(project)
                self.persist_catalog(data)
                return project
            except Exception:
                if saved:self.preset_paths()[saved['id']].unlink(missing_ok=True)
                raise

    def rename_project(self, key, name):
        with self.lock:
            data = self._catalog(self.discover())
            project = next((p for p in data['projects'] if p['id'] == key), None)
            if project is None:
                raise ValueError('프로젝트를 찾을 수 없습니다')
            project['name'] = label(name)
            self.persist_catalog(data)

    def detail(self, key):
        records = self.discover()
        if key not in records:
            raise ValueError('실행을 찾을 수 없습니다')
        record = records[key]
        if record.get('path') and getattr(self, 'result_info', None):
            record = {**record, **self.result_info(record)}
        case = self.queue_data()['cases'].get(key)
        if case and not case.get('result_key'):
            attempt = case.get('attempts', [])
            log_path = Path(attempt[-1]['job_path']).with_name('execution.log') if attempt else None
            log = log_path.read_text(encoding='utf-8', errors='replace')[-50000:] if log_path and log_path.exists() else ''
            return {**record, 'recovery': self.recovery(record, case['config'], log), 'config': copy.deepcopy(case['config']), 'log': log, 'checks': {}, 'grid': None}
        p = Path(record['path'])
        if record['kind'] == 'warehouse':
            config = read_json(p/'transport_input.json', {})
            candidates = result_logs(p, config)
        else:
            config = read_json(p/'case_config.json', None) or read_json(p/'config.json', {})
            candidates = result_logs(p, config)
            attempt = record.get('study_attempt_id')
            if isinstance(attempt, str) and re.fullmatch('[a-f0-9]{32}', attempt):
                source = self.root/'cfd_studio/Studies/attempts'/attempt
                candidates = result_logs(source/'raw', config) + [source/'execution.log'] + candidates
        if record.get('job_id'):
            folder = Path(record['job_path']).parent if record.get('job_path') else self.folder/'runs'/record['job_id']
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
        if case:
            config = copy.deepcopy(case['config'])
            if not log and case.get('attempts'):
                lp = Path(case['attempts'][-1]['job_path']).with_name('execution.log')
                log = lp.read_text(encoding='utf-8', errors='replace')[-50000:] if lp.exists() else ''
        live = self.live()
        if key == 'legacy:'+str(live.get('rid', '')) and live.get('running'):
            log = live.get('log') or log
        return {**record, 'recovery': self.recovery(record, config, log, read_json(p/'checks.json', {})), 'config': config, 'log': log, 'log_source': str(path) if path else None,
                'checks': read_json(p/'checks.json', {}), 'grid': read_json(p/'grid_assessment.json', None)}

    def preset_paths(self):
        paths = {'warehouse': self.root/'tracer_transport/warehouse_porous_convergence.json'}
        for folder, prefix in ((self.root/'cfd_studio/configs', 'config:'), (self.folder/'presets', 'preset:')):
            paths.update({prefix+p.stem: p for p in sorted(folder.glob('*.json'))})
        paths.update({'scoped:'+p.stem: p for p in (self.folder/'form_presets').glob('*.json')})
        return paths

    def template(self, key='warehouse'):
        if key.startswith('form:'):
            return copy.deepcopy(self.form(key[5:])['config'])
        paths = self.preset_paths()
        if key not in paths:
            raise ValueError('설정을 찾을 수 없습니다')
        value = read_json(paths[key])
        return value['config'] if key.startswith('scoped:') else value

    def presets(self):
        items = []
        for key, path in self.preset_paths().items():
            value = read_json(path)
            items.append({'id': key, 'name': value['name'] if key.startswith('scoped:') else '저장고 연결 기본값' if key == 'warehouse' else path.stem,
                'model': config_kind(self.template(key)), 'form_id': self.preset_form(key)})
        items.extend({'id': 'form:'+f['id'], 'name': '기존 입력값', 'model': f['model'], 'form_id': f['id']} for f in self.forms() if not f.get('definition_only'))
        return items

    def save_preset(self, name, config, form_id=None):
        if form_id:
            return self.save_scoped_preset(name, config, form_id)
        from cfd_studio.config_presets import save_new_preset
        validate_settings(config)
        target = save_new_preset(self.folder/'presets', label(name), config)
        return {'id': 'preset:'+target.stem, 'name': target.stem}

    def attach_legacy(self, project_id, rid):
        with self.lock:
            data = self._catalog(self.discover())
            project = next((p for p in data['projects'] if p['id'] == project_id), None)
            key = 'legacy:'+str(rid)
            if project is None or key not in self.discover():
                raise ValueError('프로젝트 또는 실행을 찾을 수 없습니다')
            for p in data['projects']:
                p['runs'] = [r for r in p['runs'] if r != key]
            project['runs'].append(key)
            self.persist_catalog(data)
            return key

    def _command(self, job_path):
        prefix = []
        root, job = str(self.root), str(job_path.resolve())
        if os.name == 'nt':
            prefix = ['wsl.exe']
            if self.settings.get('wsl_distro'):
                prefix += ['-d', self.settings['wsl_distro']]
            root, job = [subprocess.check_output(prefix+['--exec', 'wslpath', '-u', p.replace('\\', '/')], text=True, encoding='utf-8', timeout=15, creationflags=0x08000000 if os.name == 'nt' else 0).strip() for p in (root, job)]
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
            folder = self.attempt_folder(project_id, key, key)
            folder.mkdir(parents=True, exist_ok=False)
            output = folder/'Raw'/('warehouse_transport_ui_'+key)
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
                        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000) if os.name == 'nt' else 0,
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
    if url.path in ('/execution_workspace.js', '/config_editor.js', '/input_validation.js', '/form_config_editor.js', '/form_wizard.js', '/warehouse_viewer.js', '/data_sheet_viewer.js'):
        handler._send(200, Path(__file__).with_name(url.path[1:]).read_bytes(), 'text/javascript; charset=utf-8')
        return True
    if not url.path.startswith('/api/executions'):
        return False
    try:
        if url.path == '/api/executions':
            result = workspace.snapshot()
        elif url.path == '/api/executions/template':
            result = {'config': workspace.template(parse_qs(url.query).get('id', ['warehouse'])[0])}
        elif url.path == '/api/executions/storage-defaults':
            result = workspace.project_defaults()
        elif url.path == '/api/executions/export-csv-download':
            workspace.csv_exports.download(handler, parse_qs(url.query).get('token', [''])[0])
            return True
        elif url.path == '/api/executions/chart-catalog':
            result = workspace.series.catalog(parse_qs(url.query).get('id', [''])[0])
        elif url.path == '/api/executions/chart':
            q = parse_qs(url.query)
            result = workspace.series.page(q.get('id', [''])[0], q.get('metric', [''])[0], int(q.get('offset', ['0'])[0]), int(q.get('limit', ['16'])[0]))
        elif url.path == '/api/executions/point-chart':
            q = parse_qs(url.query)
            result = workspace.series.point_page(q.get('id', [''])[0], q.get('field', [''])[0],
                [float(q.get(k, [''])[0]) for k in ('x','y','z')], int(q.get('offset', ['0'])[0]), int(q.get('limit', ['16'])[0]))
        elif url.path == '/api/executions/forms':
            result = {'forms': workspace.forms(), 'templates': workspace.form_templates()}
        elif url.path == '/api/executions/form-profiles':
            from cfd_studio.form_wizard import profiles
            result = {'profiles': profiles()}
        elif url.path == '/api/executions/config-template':
            result = {'config': json.loads((Path(__file__).resolve().parents[1]/'templates/cfd-config-template.json').read_text(encoding='utf-8'))}
        elif url.path == '/api/executions/solvers':
            result = workspace.solver_catalog()
        elif url.path == '/api/executions/presets':
            result = {'presets': workspace.presets()}
        elif url.path == '/api/executions/result-progress':
            result = workspace.result_progress(parse_qs(url.query).get('project_id', [''])[0])
        elif url.path == '/api/executions/detail':
            result = workspace.detail(parse_qs(url.query).get('id', [''])[0])
        else:
            raise ValueError('알 수 없는 요청입니다')
        handler._json(result)
    except (ValueError, OSError, KeyError, BadZipFile, EOFError) as error:
        handler._json({'ok': False, 'msg': str(error)}, 400)
    return True


def post_route(handler, workspace, body):
    path = urlparse(handler.path).path
    if not path.startswith('/api/executions'):
        return False
    try:
        if not isinstance(body, dict):
            raise ValueError('요청 형식을 확인해 주세요')
        if path == '/api/executions/project-config-check':
            workspace.check_project_config(body.get('form_id'),body.get('config'))
            result={'valid':True}
        elif path == '/api/executions/form-inspect':
            from cfd_studio.solver_requirements import inspect_config
            result = inspect_config(body.get('solver'),body.get('config'))
        elif path == '/api/executions/form-generate':
            from cfd_studio.form_wizard import generate
            result = generate(body.get('solver'), body.get('answers'))
        elif path == '/api/executions/solver-check':
            result = workspace.solver_catalog(check=True)
        elif path == '/api/executions/preset':
            result = workspace.save_preset(body.get('name'), body.get('config'), body.get('form_id'))
        elif path == '/api/executions/form':
            result = workspace.save_form(body.get('name'), body.get('model'), body.get('solver'), body.get('config'), body.get('id'), body.get('revision'), body.get('description', ''), body.get('sections'), body.get('config_schema'), body.get('input_schema'))
        elif path == '/api/executions/project':
            workspace.form(body.get('form_id'))
            result = workspace.create_project(body.get('name'), body.get('description', ''), body.get('default_preset'), body.get('storage_path'), body.get('form_id'), body.get('initial_config'), body.get('preset_name'))
        elif path == '/api/executions/project-open':
            result = workspace.open_project(body.get('storage_path'))
        elif path == '/api/executions/project-pick':
            result = workspace.pick_project_folder(body.get('path', ''))
        elif path == '/api/executions/rename':
            workspace.rename_project(body.get('id'), body.get('name'))
            result = {}
        elif path == '/api/executions/project-edit':
            result = workspace.edit_project(body.get('id'), body.get('name'), body.get('description', ''), body.get('default_preset'), body.get('storage_path'), body.get('form_id'))
        elif path == '/api/executions/preset-rename':
            result = workspace.rename_preset(body.get('id'), body.get('name'))
        elif path == '/api/executions/case':
            result = workspace.save_case(body.get('project_id'), body.get('name'), body.get('config'), body.get('id'), body.get('revision'), body.get('preset_id'), body.get('preset_name'))
        elif path == '/api/executions/export-csv':
            result = workspace.csv_exports.prepare(body.get('id'))
        elif path == '/api/executions/recover':
            result = workspace.recover_case(body.get('id'), body.get('action'))
        elif path == '/api/executions/queue':
            result = workspace.queue_action(body.get('action'), body.get('ids'), body.get('id'))
        elif path == '/api/executions/result':
            if not getattr(workspace, 'result_prepare', None):
                raise ValueError('결과 변환 실행기 연결이 없습니다')
            result = workspace.result_prepare(workspace.detail(body.get('id')))
        elif path == '/api/executions/folder':
            result = workspace.open_result_folder(body.get('id'))
        elif path == '/api/executions/start':
            result = workspace.start(body.get('project_id'), body.get('name'), body.get('config'))
        else:
            raise ValueError('알 수 없는 요청입니다')
        handler._json({'ok': True, 'result': result})
    except (ValueError, OSError, KeyError, TypeError, BadZipFile, EOFError, struct.error) as error:
        handler._json({'ok': False, 'msg': str(error)}, 400)
    return True
