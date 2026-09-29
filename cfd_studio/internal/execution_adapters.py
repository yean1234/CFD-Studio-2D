"""Connect the shared queue to existing Studio execution and conversion services."""
import copy
import json
import math
import os
from pathlib import Path
import re
import threading
import time


def install(workspace, g):
    class Reply:
        def _json(self, value, code=200):
            self.value, self.code = value, code

    def recovery(case):
        rid = str(case.get('result_key', '')).removeprefix('legacy:')
        if not re.fullmatch(r'[0-9]+', rid):
            return {'resume': False, 'resume_reason': '재시작 원본의 실행 ID가 없습니다.'}
        mode_error = g['_resume_mode_error'](rid)
        if mode_error:
            return {'resume': False, 'resume_reason': mode_error}
        source = g['WSL_CASE'] if rid == str(g['_active_rid']()) else g['WSL_CASE'].rstrip('/')+'/ProjectRuns/'+rid
        quoted = g['_shq'](source)
        command = (f'cd {quoted} || exit 1; '
                   f'test "$(cat .cfd_studio_runid 2>/dev/null)" = {g["_shq"](rid)} || exit 2; '
                   + g['_resume_anchor_shell']('ANCHOR', '.') + 'printf "STUDIO_ANCHOR=%s\\n" "$ANCHOR"')
        ok, output = g['wsl'](command, timeout=20)
        match = re.search(r'STUDIO_ANCHOR=([0-9]+(?:[.][0-9]+)?)', output)
        anchor = float(match[1]) if ok and match else None
        if anchor is None or anchor <= 0 or anchor >= case['end_s']:
            return {'resume': False, 'resume_reason': '목표 시점 이전의 완전한 재시작 저장 지점이 없습니다. 다시하기로 처음부터 계산할 수 있습니다.'}
        return {'resume': True, 'anchor': anchor, 'resume_source': source,
                'resume_reason': f'저장 지점 {anchor:g}부터 재개합니다. 이후의 불완전 저장 구간은 다시 계산합니다.'}

    def start(case):
        reply = Reply()
        attempt = case['attempts'][-1]
        mode = attempt.get('mode', 'fresh')
        rid = str(attempt.get('source_result_key') or '').removeprefix('legacy:')
        if mode == 'resume':
            recovered = recovery(case)
            if not recovered.get('resume'):
                raise ValueError(recovered['resume_reason'])
            # Preserve the original checkpoint and logs before the native resume path
            # prunes incomplete writes or replaces log.restart.
            destination = g['win2wsl'](str(Path(attempt['job_path']).parent/'Recovery_Source'))
            source = recovered['resume_source']
            command = (f'set -e; S={g["_shq"](source)}; D={g["_shq"](destination)}; test ! -e "$D"; mkdir "$D"; '
                       'for P in "$S"/system "$S"/constant "$S"/config.json "$S"/.cfd_studio_runid "$S"/processor[0-9]* "$S"/[0-9]* "$S"/log.* "$S"/postProcessing; do '
                       '[ ! -e "$P" ] || cp -a --reflink=auto "$P" "$D/"; done')
            ok, output = g['wsl'](command, timeout=3600)
            if not ok:
                raise ValueError('재시작 원본 보존 실패: '+output[-1000:])
        if workspace.queue_data()['cases'][case['id']].get('stop_requested'):
            raise ValueError('실행 준비 중 사용자가 계산을 중단했습니다.')
        g['H']._run_legacy(reply, {'mode': 'resume_archived' if mode == 'resume' else 'fresh', 'selected_rid': rid, 'end': case['end_s'], 'config_ref': 'inline',
            'config': copy.deepcopy(case['config']), 'output_fields': case['config']['run'].get('output_fields'),
            'execution_project_id': case['project_id'], 'execution_name': case['name'],
            'execution_attempt_path': str(Path(case['attempts'][-1]['job_path']).parent),
            '_queue_authorized': workspace})
        if not reply.value.get('ok'):
            raise ValueError(reply.value.get('msg', '실행 시작 실패'))
        rid = reply.value['rid']
        from cfd_studio.execution_workspace import atomic_json
        atomic_json(Path(case['attempts'][-1]['job_path']).with_name('applied_input.json'), g['project_config'](rid))
        return reply.value

    def prepare(record):
        rid = record['rid']
        if record['kind'] == 'warehouse':
            raise ValueError('저장고 결과는 계산 완료 시 원본 검사 후 생성됩니다. 실행 로그를 확인하세요.')
        state = g['_extract_state'](rid)
        with g['EXTRACT_REGISTRY_LK']:
            if state.get('busy') or g['_extract_lock'](rid).locked():
                return {'started': False}
            fields = g['project_config'](rid).get('run', {}).get('output_fields') or ['bubble', 'flow', 'therm', 'phase']
            state.update(busy=True, done=0, processed=0, total=0, remaining=0, failed=0, last_error='', msg='누락 구간 확인 중', rid=rid,
                         sel={key: name in fields for name, key in [('bubble','alpha'),('flow','flow'),('therm','therm'),('phase','phase'),('pressure','pressure'),('turbulence','turbulence')]})
        threading.Thread(target=g['extract_worker'], args=(rid,), daemon=True).start()
        return {'started': True}

    def info(record):
        if record['kind'] == 'warehouse':
            return {}
        rid = record['rid'];pd = record['path'];inv = g['project_inventory'](pd)
        config = g['project_config'](rid) or {}
        if config.get('_해석유형') == 'gas_transport':
            return {'result_status': 'ready' if inv.get('concentration') else 'none', 'can_generate': False}
        meta = g['_read_json_file'](os.path.join(pd, 'meta.json')) or {}
        latest = max(float(meta.get('last_time') or 0), float(meta.get('tmax') or 0))
        ready = any(inv.get(k) for k in ('bubble','phase','flow','therm','pressure','turbulence'))
        fields = config.get('run', {}).get('output_fields') or ['bubble','flow','therm','phase']
        run = config.get('run', {})
        steady = config.get('openfoam_mapping', {}).get('solver') == 'simpleFoam'
        interval = (run.get('write_interval_iterations') if steady else run.get('viz_interval_s') or run.get('write_interval_s')) or 1
        policy = config.get('_studio', {}).get('termination', {})
        include_initial = policy.get('include_initial', False)
        expected_last = math.floor((latest+1e-7)/interval)
        prefixes = {'bubble':'bub','flow':'flow','therm':'therm','phase':'phase','pressure':'pressure','turbulence':'turbulence'}
        times_by_field = []
        # Directory entries expose size without opening every historical frame.
        # Full header validation remains in the completion gate and converter.
        with os.scandir(pd) as entries:
            files = [(entry.name, entry.stat().st_size) for entry in entries if entry.is_file()]
        for field in fields:
            indices = set();prefix = prefixes.get(field, field)+'_'
            for filename, size in files:
                if not filename.startswith(prefix) or not filename.endswith('.bin'):
                    continue
                try:
                    value = float(filename[len(prefix):-4]);index = round(value/interval)
                    if abs(value-index*interval)<1e-6 and size >= (12 if field == 'bubble' else 40):
                        indices.add(index)
                except ValueError:
                    pass
            times_by_field.append(indices)
        complete_indices = set.intersection(*times_by_field) if times_by_field else set()
        first_index = 0 if include_initial else 1
        incomplete = sum(first_index<=i<=expected_last for i in complete_indices) < max(0, expected_last-first_index+1)
        state = g['_extract_state'](rid)
        return {'last_saved': inv.get('tmax'), 'result_status': 'preparing' if state.get('busy') else 'update' if ready and (expected_last*interval>inv['tmax']+1e-6 or incomplete) else 'ready' if ready else 'none',
                'has_results': ready, 'can_generate': not state.get('busy') and latest > 0,
                'frame_counts': {k: inv.get(k, 0) for k in fields}, 'extract': g['_extract_public'](rid)}

    def poll(case):
        rid = case.get('result_key', '').removeprefix('legacy:')
        if not rid:
            return {'status': 'running'} if time.time()-case['attempts'][-1]['started'] < 240 else {'status': 'failed', 'error': '시작 결과 연결을 확인하지 못했습니다. 실행 중인 솔버와 원본을 확인하세요.'}
        if g['_active_rid']() != rid:
            return {'status': 'failed', 'error': '활성 실행이 변경되었습니다. 이전 결과는 보존됩니다.'}
        state = g['get_status']()
        if state.get('running'):
            return {'status': 'running'}
        if case.get('stop_requested'):
            return {'status': 'stopped', 'completion_reason': 'stopped'}
        if not state.get('completed'):
            if time.time()-case['attempts'][-1]['started'] < 240:
                return {'status': 'running'}
            return {'status': 'failed', 'error': '솔버 완료 기록이 없습니다. 실행 로그를 확인하세요.'}
        # The next case must not replace the live case while result conversion is using it.
        record = {'rid': rid, 'kind': 'legacy', 'path': g['proj_dir'](rid)}
        result = info(record)
        if result['result_status'] in ('none','update'):
            if g['_extract_state'](rid).get('failed') or g['_extract_state'](rid).get('last_error'):
                return {'status': 'failed', 'error': '결과 저장 실패: '+str(g['_extract_state'](rid).get('last_error', '변환 로그 확인'))}
            prepare(record)
            return {'status': 'running'}
        if result['result_status'] == 'preparing':
            return {'status': 'running'}
        policy = case['config']['_studio']['termination']
        if policy['mode'] == 'frames':
            prefixes = {'bubble':'bub', 'flow':'flow','therm':'therm','phase':'phase','pressure':'pressure','turbulence':'turbulence'}
            fields = case['config']['run'].get('output_fields') or ['flow']
            sets = []
            names = os.listdir(record['path'])
            for field in fields:
                times = {float(m.group(1)) for name in names if (m:=re.fullmatch(re.escape(prefixes[field])+r'_([0-9.eE+-]+)\.bin', name)) and g['_valid_viz_output'](os.path.join(record['path'], name), field)}
                if not policy['include_initial']:
                    times.discard(0.0)
                sets.append(times)
            count = len(set.intersection(*sets)) if sets else 0
            if count != policy['frames']:
                return {'status': 'failed', 'error': f'완전 저장 프레임 수 불일치: {count}/{policy["frames"]}'}
        from cfd_studio.execution_workspace import atomic_json
        marker = Path(case['attempts'][-1]['job_path']).with_name('storage_complete.json')
        if not marker.is_file():
            destination = g['win2wsl'](str(Path(record['path'])/'Raw_Data'/'Case_State'))
            token = g['_wsl_case_token']()
            target = g['_shq'](destination)
            script = f'''set -eu
cd {token}
mkdir -p {target}
for item in system constant 0 0.orig config.json run_overrides.json postProcessing processor[0-9]* log.* [0-9]*; do
    [ -e "$item" ] || continue
    rsync -rLt -- "$item" {target}/
done
# A second checksum pass verifies the destination without deleting original data.
for item in system constant 0 0.orig config.json run_overrides.json postProcessing processor[0-9]* log.* [0-9]*; do
    [ -e "$item" ] || continue
    test -z "$(rsync -rLtcni -- "$item" {target}/)"
done
echo PROJECT_SAVED'''
            ok, out = g['wsl'](script, timeout=86400)
            if not ok or 'PROJECT_SAVED' not in out:
                return {'status': 'failed', 'error': '프로젝트 원본 저장 실패: '+str(out)[-240:]}
            atomic_json(marker, {'path': str(Path(record['path'])/'Raw_Data'/'Case_State'), 'verified': True})
        return {'status': 'complete', 'completion_reason': policy['mode']}

    def stop(case):
        rid = case.get('result_key', '').removeprefix('legacy:')
        if not rid or g['_active_rid']() != rid:
            raise ValueError('현재 실행과 선택 실행이 다릅니다. 중단하지 않았습니다.')
        before = g['get_status']()
        g['_persist_project_progress'](rid, before.get('time'))
        ok, message = g['wsl'](f"cd {g['WSL_CASE']} || exit 1; touch .cfd_studio_user_stopped; " + g['_case_kill_script']('icoReactingMultiphaseInterFoam|simpleFoam|pimpleFoam|Allrun|cfd_studio_solver_supervisor'))
        if not ok:
            raise ValueError('중단 요청 실패: '+message)
        g['STATE']['user_stopped'] = True;g['STATE']['stop_t'] = time.time()

    polling, polled = set(), {}
    poll_lock = threading.Lock()
    def nonblocking_poll(case):
        key = case['attempts'][-1]['id']
        with poll_lock:
            result = polled.get(key, {'status': 'running'})
            if result.get('status') in ('complete', 'failed', 'stopped'):
                return copy.deepcopy(result)
            if key not in polling:
                polling.add(key)
                snapshot = copy.deepcopy(case)
                def collect():
                    try:
                        value = poll(snapshot)
                    except Exception as error:
                        value = {'status': 'failed', 'error': str(error)}
                    with poll_lock:
                        polled[key] = value
                        polling.discard(key)
                threading.Thread(target=collect, name='case-result-check', daemon=True).start()
            return copy.deepcopy(result)

    workspace.legacy_recovery = recovery
    workspace.legacy_start = start
    workspace.legacy_poll = nonblocking_poll
    workspace.legacy_stop = stop
    workspace.result_info = info
    workspace.result_prepare = prepare
