"""Persistent case drafts, immutable attempts and a single execution queue.

No solver equations or material defaults are defined here.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid


def read(path, default=None):
    from cfd_studio.execution_workspace import read_json
    return read_json(path, default)


def write(path, value):
    from cfd_studio.execution_workspace import atomic_json
    atomic_json(path, value)


def termination(config):
    """Validate exactly one stop policy; derive solver limits on a private copy."""
    from cfd_studio.execution_workspace import config_kind, validate_settings
    c = copy.deepcopy(config)
    kind = config_kind(c)
    steady = kind == 'grain_silo' and c.get('openfoam_mapping', {}).get('solver') == 'simpleFoam'
    n = c.get('numerics', {}) if kind == 'warehouse' else c.get('run', {})
    end_key = 'end_s' if kind == 'warehouse' else 'max_iterations' if steady else 'end_time_s'
    write_key = 'write_interval_iterations' if steady else 'write_interval_s'
    policy = copy.deepcopy(c.get('_studio', {}).get('termination') or
                           {'mode': 'frames' if steady else 'time', **({'frames': max(1, int(n.get(end_key, 1)/max(n.get(write_key, 1), 1))), 'include_initial': False} if steady else {'time_s': n.get(end_key)})})
    mode = policy.get('mode')
    if mode not in ('time', 'frames', 'convergence'):
        raise ValueError('종료 방식을 하나 선택하세요')
    if mode == 'convergence':
        raise ValueError('현재 실행기는 수렴 기준의 연속 유지 구간을 검증하지 않습니다. 수렴 종료를 사용할 수 없습니다.')
    if steady and mode == 'time':
        raise ValueError('정상 해석의 반복 횟수는 물리시간이 아닙니다. 저장 프레임 수를 선택하세요.')
    interval = n.get('viz_interval_s', n.get(write_key)) if kind == 'immersion' else n.get(write_key)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
        raise ValueError('결과 저장 간격은 양수여야 합니다')
    if mode == 'frames':
        count = policy.get('frames')
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError('저장 프레임 수는 양의 정수여야 합니다')
        initial = policy.get('include_initial', False)
        if not isinstance(initial, bool):
            raise ValueError('0초 프레임 포함 여부를 선택하세요')
        if steady and initial:
            raise ValueError('정상 해석은 0초 물리 프레임이 없습니다. 초기 프레임을 제외하세요.')
        end = interval * (count - int(initial))
        if end <= 0:
            raise ValueError('초기 프레임을 포함하면 최소 2개를 지정하세요')
        policy = {'mode': mode, 'frames': count, 'include_initial': initial}
    else:
        end = policy.get('time_s')
        if isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end) or end <= 0:
            raise ValueError('목표 물리시간은 양수여야 합니다')
        policy = {'mode': mode, 'time_s': end}
    n[end_key] = end
    if kind != 'warehouse':
        n['stop_mode'] = 'fixed'
        if steady:
            n['end_time_s'] = end
    if kind == 'warehouse':
        if n.get('dt_s', 0) > interval or interval > end:
            raise ValueError('솔버 시간간격 ≤ 저장 간격 ≤ 계산 종료시간 조건을 확인하세요')
        if not math.isclose(end/interval, round(end/interval), rel_tol=1e-10):
            raise ValueError('이 실행기는 목표 물리시간을 저장 간격의 배수로 지정해야 합니다')
    validate_settings(c)
    c.setdefault('_studio', {})['termination'] = policy
    goals = c['_studio'].get('goals', '')
    if not isinstance(goals, str) or len(goals) > 4000:
        raise ValueError('목표값·비교 목적은 4,000자 이내로 입력하세요')
    return c, policy, end


def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in sorted(set(a)|set(b)):
            if key == '_studio':
                continue
            result.extend(differences(a.get(key), b.get(key), (path+'.' if path else '')+key))
        return result
    return [] if a == b else [{'path': path, 'before': a, 'after': b}]


class RunManagement:
    def recovery(self, record, config, log='', checks=None):
        """Explain recorded failures without inferring a cause from exit status alone."""
        state = record.get('status')
        if state not in ('failed', 'stopped'):
            return None
        result = {'retry': False, 'resume': False, 'category': 'runtime',
                  'reason': record.get('error') or ('사용자가 계산을 중단했습니다.' if state == 'stopped' else '실행이 실패했지만 상세 오류가 기록되지 않았습니다.'),
                  'evidence': '', 'action': '실행 환경과 솔버 로그를 확인한 뒤 다시하기를 선택하세요.'}
        if (checks or {}).get('execution_checks_pass') is False:
            failures = []
            if checks.get('timeline_complete') is False:
                failures.append('저장 시점 또는 종료 시점이 목표와 일치하지 않음')
            for key, title, limit in [('relative_balance_error', '질량수지 상대 오차', 1e-6),
                                      ('relative_energy_balance_error', '에너지수지 상대 오차', .01),
                                      ('max_divergence_s_inv', '최대 속도 발산 (1/s)', 1e-5)]:
                value = checks.get(key)
                if isinstance(value, (int, float)) and (not math.isfinite(value) or value >= limit):
                    failures.append(f'{title}: {value:.6g} (통과 기준 < {limit:g})')
            minimum = checks.get('minimum_concentration_kg_m3')
            if isinstance(minimum, (int, float)) and minimum < -1e-14:
                failures.append(f'음의 농도: {minimum:.6g} kg/m³ (하한 -1e-14)')
            result.update(category='result_check', reason='계산 후 결과 검사 미달: '+('; '.join(failures) or '저장된 검사 기록에서 실행·보존 검사를 통과하지 못했습니다.'),
                          action='검사 기록을 확인하세요. 같은 Config로 다시 계산하면 동일한 검사 미달이 반복될 수 있습니다.')
        lines = log.splitlines()
        for i, line in enumerate(lines):
            if 'trapping enabled' in line.lower():
                continue
            if any(mark in line.lower() for mark in ('fatal error', 'fatal io error', 'traceback', 'permission denied', 'no space left', 'not found', 'floating point exception')):
                result['evidence'] = '\n'.join(lines[i:i+12])[:3000]
        try:
            termination(config)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            result.update(category='config', reason='Config 검증 실패: '+str(error),
                          action='Config 보기에서 이 Config로 새 Case를 선택하고 입력값을 수정하세요.')
            return result
        result['retry'] = True
        if state == 'stopped':
            case = self.queue_data()['cases'].get(record['id'])
            if case and case.get('kind') != 'warehouse' and getattr(self, 'legacy_recovery', None):
                try:
                    result.update(self.legacy_recovery(case))
                except (ValueError, OSError, KeyError) as error:
                    result['resume_reason'] = '재시작 데이터 확인 실패: '+str(error)
            else:
                result['resume_reason'] = ('이 실행기는 저장 지점 재개가 연결되어 있지 않습니다. 다시하기는 새 실행 기록에서 처음부터 계산합니다.' if record.get('kind') == 'warehouse' else '이 Case의 재시작 데이터 연결이 없습니다.')
            result['action'] = ('이어하기를 선택하면 확인된 저장 지점부터 계산합니다.' if result['resume'] else result.get('resume_reason', '재시작 데이터를 확인할 수 없습니다.'))
        return result

    def recover_case(self, key, action):
        if action not in ('retry', 'continue_case'):
            raise ValueError('지원하지 않는 복구 작업입니다')
        with self.lock:
            record = self.detail(key)
            recovery = record.get('recovery') or {}
            if not recovery.get('resume' if action == 'continue_case' else 'retry'):
                raise ValueError(recovery.get('resume_reason') or recovery.get('reason') or '복구할 수 있는 실패·중단 Case를 선택하세요')
            if key not in self.queue_data()['cases']:
                project = next((p for p in self.snapshot()['projects'] if any(r['id'] == key for r in p['runs'])), None)
                if not project:
                    raise ValueError('Case의 프로젝트 연결을 찾을 수 없습니다')
                created = self.save_case(project['id'], record['name'][:74]+' 다시하기', record['config'])
                key = created['run_key']
                self.queue_action('enqueue', ids=[key])
                self.queue_action('pause')
            else:
                self.queue_action(action, case_id=key)
            return {'id': key, 'queue': self.queue_summary()}

    def queue_data(self):
        return self.read_project_queue()

    def save_queue(self, q):
        self.write_project_queue(q)

    def case_record(self, case, discovered):
        output = discovered.get(case.get('result_key'), {})
        policy = case['config']['_studio']['termination']
        return {**output, **{k: case.get(k) for k in ('id', 'name', 'created', 'project_id', 'error', 'completion_reason')},
                'kind': output.get('kind', case['kind']), 'rid': output.get('rid', ''),
                'path': output.get('path', case.get('output', '')), 'model': output.get('model', case['kind']),
                'status': case['status'], 'editable': not case.get('attempts'), 'revision': case['revision'],
                'has_results': output.get('has_results', False), 'termination': policy,
                'end_s': case.get('end_s'), 'goals': case['config'].get('_studio', {}).get('goals', ''),
                'differences': differences(case.get('baseline', {}), case['config']),
                'form_id': case.get('form_id'), 'form_snapshot': {k:v for k,v in case['form_snapshot'].items() if k != 'config'} if case.get('form_snapshot') else None, 'preset_id': case.get('preset_id'), 'attempts': case.get('attempts', []),
                'last_saved': output.get('last_saved'), 'result_status': output.get('result_status', 'none'),
                'numerical_status': output.get('numerical_status', 'unchecked')}

    def save_case(self, project_id, name, config, case_id=None, revision=None, preset_id=None, preset_name=None):
        from cfd_studio.execution_workspace import label, config_kind
        name = label(name)
        config, policy, end = termination(config)
        with self.lock:
            project = next((p for p in self.snapshot()['projects'] if p['id'] == project_id), None)
            if not project:
                raise ValueError('프로젝트를 찾을 수 없습니다')
            self.project_folder(project_id)
            q = self.queue_data()
            old = q['cases'].get(case_id) if case_id else None
            if case_id and not old:
                raise ValueError('실행을 찾을 수 없습니다')
            if old and (old['project_id'] != project_id or old.get('attempts') or old['status'] not in ('draft', 'queued')):
                raise ValueError('시작한 실행은 변경할 수 없습니다. 새 실행으로 복제하세요.')
            if old and revision != old['revision']:
                raise ValueError('다른 화면에서 설정이 변경되었습니다. 다시 열어 주세요.')
            form_id = project.get('form_id')
            if form_id:
                self.check_form_config(form_id, config)
                self.check_form_preset(form_id, preset_id)
            source = old.get('baseline', {}) if old else self.template(preset_id) if preset_id else copy.deepcopy(project.get('initial_config') or config)
            key = case_id or 'case:'+uuid.uuid4().hex
            case = {**(old or {}), 'id': key, 'project_id': project_id, 'name': name, 'config': config,
                    'form_id': form_id, 'form_snapshot': copy.deepcopy(old.get('form_snapshot') if old else self.form(form_id)) if form_id else None,
                    'baseline': source, 'preset_id': old.get('preset_id') if old else preset_id,
                    'kind': config_kind(config), 'created': old['created'] if old else time.time(),
                    'status': old['status'] if old else 'draft', 'end_s': end,
                    'revision': old['revision']+1 if old else 1, 'attempts': old.get('attempts', []) if old else []}
            saved = None
            try:
                # Saving the optional preset must succeed before the draft can change.
                if preset_name:
                    saved = self.save_preset(preset_name, config, form_id) if form_id else self.save_preset(preset_name, config)
                from cfd_studio.config_assets import store_definitions
                case['definition_assets']=store_definitions(self.project_folder(project_id)/'Cases'/key.removeprefix('case:'),config)
                q['cases'][key] = case
                self.save_queue(q)
            except Exception:
                if saved:
                    self.preset_paths()[saved['id']].unlink(missing_ok=True)
                raise
            return {'run_key': key, 'preset': saved, 'revision': case['revision']}

    def queue_action(self, action, ids=None, case_id=None):
        with self.lock:
            q = self.queue_data()
            if action == 'enqueue':
                if not ids or len(ids) != len(set(ids)):
                    raise ValueError('추가할 실행을 선택하세요')
                for key in ids:
                    c = q['cases'].get(key)
                    if not c or c['status'] != 'draft' or c.get('attempts'):
                        raise ValueError('시작하지 않은 실행만 대기열에 추가할 수 있습니다')
                for key in ids:
                    q['cases'][key]['status'] = 'queued'
                    q['order'].append(key)
            elif action == 'reorder':
                if not isinstance(ids, list) or len(ids) != len(set(ids)) or set(ids) != set(q['order']):
                    raise ValueError('현재 대기열 전체의 순서를 지정하세요')
                q['order'] = ids
            elif action == 'remove':
                if case_id not in q['order']:
                    raise ValueError('아직 시작하지 않은 대기 실행만 제외할 수 있습니다')
                q['order'].remove(case_id)
                c = q['cases'][case_id]
                c['status'] = c.pop('queued_from_status', 'draft')
                c.pop('next_mode', None)
            elif action == 'pause':
                q['paused'] = True
            elif action == 'resume':
                if any(key not in q['cases'] for key in q['order']):
                    raise ValueError('대기열 프로젝트 드라이브 연결을 확인하세요')
                if q.get('failure'):
                    raise ValueError('실패한 실행을 재시도하거나 건너뛰세요')
                q['paused'] = False
                q.pop('service_error', None)
            elif action in ('retry', 'continue_case'):
                c = q['cases'].get(case_id)
                if not c or c['status'] not in ('failed', 'stopped'):
                    raise ValueError('실패하거나 중단된 Case만 복구할 수 있습니다')
                recovery = self.detail(case_id)['recovery']
                if not recovery.get('resume' if action == 'continue_case' else 'retry'):
                    raise ValueError(recovery.get('resume_reason') or recovery['reason'])
                c['queued_from_status'] = c['status']
                c['next_mode'] = 'resume' if action == 'continue_case' else 'fresh'
                c['status'] = 'queued'
                q['order'].insert(0, case_id)
                if q.get('failure') == case_id:
                    q['failure'] = None
                q['paused'] = True
            elif action == 'skip':
                if not q.get('failure') or q['failure'] != case_id:
                    raise ValueError('대기열을 중단시킨 실행을 선택하세요')
                q['failure'] = None
                q['paused'] = True
            elif action == 'stop':
                if q['active'] != case_id:
                    raise ValueError('선택한 실행이 현재 계산 중이 아닙니다')
                c = q['cases'][case_id]
                if c['kind'] == 'warehouse':
                    write(Path(c['attempts'][-1]['job_path']).with_name('stop.json'), {'requested': time.time()})
                elif getattr(self, 'legacy_stop', None):
                    self.legacy_stop(c)
                else:
                    raise ValueError('이 실행기의 중단 연결이 없습니다')
                c['stop_requested'] = True
                q['paused'] = True
            else:
                raise ValueError('지원하지 않는 대기열 작업입니다')
            self.save_queue(q)
            return self.queue_summary(q)

    def queue_summary(self, q=None):
        q = q or self.queue_data()
        return {k: q.get(k) for k in ('paused', 'active', 'order', 'failure', 'service_error')}

    def start_queue_service(self):
        if getattr(self, '_queue_thread', None):
            return
        self._queue_shutdown = threading.Event()
        self._async_launch = True
        with self.lock:
            self._catalog(self.discover())
            q = self.queue_data()
            # Restore the order, but never silently launch new work after a restart.
            q['paused'] = True
            self.save_queue(q)
        def loop():
            while not self._queue_shutdown.wait(1):
                try:
                    self.queue_tick()
                except Exception as error:
                    with self.lock:
                        q = self.queue_data();q['paused'] = True;q['service_error'] = str(error);self.save_queue(q)
        self._queue_thread = threading.Thread(target=loop, name='studio-queue', daemon=True)
        self._queue_thread.start()

    def queue_tick(self):
        with self.lock:
            q = self.queue_data()
            if q['active']:
                c = q['cases'][q['active']]
                a = c['attempts'][-1]
                if a['id'] in getattr(self, '_launching', set()):
                    return
                if c['kind'] == 'warehouse':
                    job = read(a['job_path'], {})
                    process = self.processes.get(a['id'])
                    if job.get('status') in ('queued', 'running') and process is not None and process.poll() is not None:
                        job.update(status='failed', error='실행기가 완료 기록 없이 종료되었습니다')
                        write(a['job_path'], job)
                    if job.get('status') in ('queued', 'running') and process is None and time.time()-read(Path(a['job_path']).with_name('heartbeat.json'), {}).get('time', a['started']) > 120:
                        job.update(status='failed', error='실행기 응답이 없습니다. 원본과 로그를 확인한 후 재시도하세요.')
                        write(a['job_path'], job)
                elif getattr(self, 'legacy_poll', None):
                    job = self.legacy_poll(c)
                else:
                    job = {'status': 'failed', 'error': '실행기 연결이 없습니다'}
                if job.get('status') in ('complete', 'failed', 'stopped'):
                    state = 'stopped' if c.get('stop_requested') else job['status']
                    c.update(status=state, error=job.get('error', ''), completion_reason=job.get('completion_reason', 'time'))
                    a.update(status=state, finished=time.time())
                    q['active'] = None
                    self.processes.pop(a['id'], None)
                    if state in ('failed', 'stopped'):
                        q['paused'] = True;q['failure'] = c['id']
                    self.save_queue(q)
                return
            if q['paused'] or q.get('failure') or not q['order'] or self.busy():
                return
            key = q['order'].pop(0);c = q['cases'][key]
            if c['status'] != 'queued':
                raise ValueError('대기열 상태 불일치')
            attempt = uuid.uuid4().hex
            folder = self.attempt_folder(c['project_id'], key, attempt)
            folder.mkdir(parents=True, exist_ok=False)
            write(folder/'input.json', c['config'])
            digest = hashlib.sha256((folder/'input.json').read_bytes()).hexdigest()
            output = folder/'Raw'/('warehouse_transport_ui_'+attempt)
            job = {'id': attempt, 'case_id': key, 'project_id': c['project_id'], 'name': c['name'],
                   'status': 'queued', 'created': time.time(), 'output': str(output.resolve()),
                   'end_s': c['end_s'], 'run_key': 'warehouse:'+output.name, 'input_sha256': digest,
                   'termination': c['config']['_studio']['termination']}
            write(folder/'job.json', job)
            c.pop('queued_from_status', None)
            c.update(status='running', error='', stop_requested=False)
            c['attempts'].append({'id': attempt, 'job_path': str((folder/'job.json').resolve()), 'started': time.time(), 'input_sha256': digest,
                                  'mode': c.pop('next_mode', 'fresh'), 'source_result_key': c.get('result_key')})
            q['active'] = key
            self.save_queue(q)  # Reserve before launching; never replay this attempt on restart.
            if c['kind'] == 'warehouse':
                c['result_key'] = job['run_key'];c['output'] = job['output'];self.save_queue(q)
            if not hasattr(self, '_launching'):
                self._launching = set()
            self._launching.add(attempt)
            if getattr(self, '_async_launch', False):
                threading.Thread(target=self.launch_case, args=(key, attempt), name='case-launch', daemon=True).start()
            else:
                self.launch_case(key, attempt)

    def launch_case(self, key, attempt):
        with self.lock:
            q = self.queue_data();c = copy.deepcopy(q['cases'][key])
            a = c['attempts'][-1]
            if a['id'] != attempt or q['active'] != key:
                return
            folder = Path(a['job_path']).parent
        try:
            if c['kind'] == 'warehouse':
                with (folder/'execution.log').open('x', encoding='utf-8') as log:
                    process = subprocess.Popen(self._command(folder/'job.json'), stdout=log, stderr=subprocess.STDOUT,
                        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000) if os.name == 'nt' else 0,
                        start_new_session=os.name != 'nt')
                with self.lock:
                    self.processes[attempt] = process
            elif getattr(self, 'legacy_start', None):
                result = self.legacy_start(c)
                with self.lock:
                    q = self.queue_data();q['cases'][key]['result_key'] = 'legacy:'+str(result['rid']);self.save_queue(q)
            else:
                raise ValueError('이 모델의 실행기 연결이 없습니다')
        except Exception as error:
            with self.lock:
                q = self.queue_data();c = q['cases'][key]
                state = 'stopped' if c.get('stop_requested') else 'failed'
                c.update(status=state, error=str(error));q.update(active=None, paused=True, failure=key)
                c['attempts'][-1].update(status=state, finished=time.time())
                job = read(folder/'job.json');job.update(status=state, error=str(error));write(folder/'job.json', job)
                self.save_queue(q)
        finally:
            with self.lock:
                getattr(self, '_launching', set()).discard(attempt)

    def edit_project(self, key, name, description, default_preset, storage_path=None, form_id=None):
        from cfd_studio.execution_workspace import label
        from cfd_studio.project_storage import project_path
        name = label(name)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('프로젝트 설명은 4,000자 이내로 입력하세요')
        if default_preset:
            self.template(default_preset)
        with self.lock:
            data = self._catalog(self.discover())
            p = next((p for p in data['projects'] if p['id'] == key), None)
            if not p:
                raise ValueError('프로젝트를 찾을 수 없습니다')
            selected_form = form_id or p.get('form_id')
            if selected_form:
                if selected_form != self.project_form(p, self.discover()):
                    raise ValueError('프로젝트의 CFD Template은 고정됩니다. 새 프로젝트를 만드세요.')
                self.check_form_preset(selected_form, default_preset)
            if storage_path and project_path(storage_path) != project_path(p['storage_path']):
                self.relocate_project(key, storage_path)
                data = self._catalog(self.discover())
                p = next(p for p in data['projects'] if p['id'] == key)
            if default_preset!=p.get('default_preset'):p.pop('initial_config',None)
            p.update(name=name, description=description, default_preset=default_preset, form_id=selected_form)
            self.persist_catalog(data)
            return p

    def rename_preset(self, key, name):
        from cfd_studio.execution_workspace import label
        name = label(name)
        if not isinstance(key, str) or not key.startswith('preset:'):
            raise ValueError('기본 제공 프리셋은 복제한 뒤 이름을 변경하세요')
        with self.lock:
            paths = self.preset_paths()
            if key not in paths:
                raise ValueError('프리셋을 찾을 수 없습니다')
            saved = self.save_preset(name, self.template(key))
            try:
                data = self._catalog(self.discover())
                for p in data['projects']:
                    if p.get('default_preset') == key:
                        p['default_preset'] = saved['id']
                self.persist_catalog(data)
            except Exception:
                self.preset_paths()[saved['id']].unlink(missing_ok=True)
                raise
            paths[key].unlink()  # Only the selected managed preset; run snapshots stay untouched.
            return saved

    def open_result_folder(self, key):
        record = self.detail(key)
        path = Path(record.get('path') or '')
        if not record.get('path') or not path.is_dir():
            raise ValueError('아직 생성된 결과 폴더가 없습니다')
        if os.name == 'nt':
            os.startfile(str(path.resolve()))
        else:
            subprocess.Popen(['xdg-open', str(path.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {'path': str(path.resolve())}
