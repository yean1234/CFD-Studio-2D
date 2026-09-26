"""트랜잭션 기반 실험 이력과 단일 소유자 순차 실행 대기열."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid

from .contracts import ROOT, CAPABILITIES, canonical, candidates, digest


class Conflict(ValueError):
    pass


def uid():
    return uuid.uuid4().hex


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def snapshot(destination):
    destination.mkdir(parents=True)
    files = []
    for package in ('study_platform', 'tracer_transport'):
        for path in (ROOT/package).rglob('*'):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and (
                    path.suffix in ('.py', '.C', '.json') or path.name in ('files', 'options', 'requirements.txt', 'COPYING')):
                # 컴파일 산출물·사용자 입력·Raw는 소스 스냅샷에 포함하지 않는다.
                if any(part.startswith('linux') for part in path.parts):
                    continue
                files.append(path)
    for name in ('LICENSE', 'README.md'):
        if (ROOT/name).is_file():
            files.append(ROOT/name)
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    # Git 커밋만으로 미커밋 변경을 재현할 수 없으므로 실제 파일 해시가 최종 기준이다.
    provenance = destination/'git_provenance.json'
    provenance.write_text(canonical({'head': commit, 'authority': 'source_manifest.json'}), encoding='utf-8')
    hashes = {}
    hashes['git_provenance.json'] = file_hash(provenance)
    for path in files:
        rel = path.relative_to(ROOT)
        target = destination/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[rel.as_posix()] = file_hash(target)
    (destination/'source_manifest.json').write_text(canonical(hashes), encoding='utf-8')
    return digest(hashes)


def verify_snapshot(folder, expected):
    manifest = json.loads((folder/'source_manifest.json').read_text(encoding='utf-8'))
    if digest(manifest) != expected:
        raise ValueError('코드 스냅샷 목록이 변경되었습니다')
    for name, expected_hash in manifest.items():
        path = (folder/name).resolve()
        if folder.resolve() not in path.parents or path.is_symlink() or file_hash(path) != expected_hash:
            raise ValueError('코드 스냅샷이 변경되었습니다: '+name)


@contextlib.contextmanager
def owner_lock(path):
    stream = open(path, 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        yield False
        return
    try:
        yield True
    finally:
        stream.close()


class Service:
    def __init__(self, root, settings=None, project_root=None, adapter=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root/'studies.sqlite'
        self.settings = settings or {}
        self.project_root = Path(project_root) if project_root else None
        self.adapter = adapter or self._real_adapter
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS studies(id TEXT PRIMARY KEY, name TEXT NOT NULL, current_revision TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, study_id TEXT, parent TEXT, data TEXT, code_hash TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, revision_id TEXT, input TEXT, input_hash TEXT, baseline INTEGER);
                CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, case_id TEXT, state TEXT, quality TEXT, owner TEXT, created REAL, result TEXT, resume_from TEXT);
                CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY, payload_hash TEXT, response TEXT);
                CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER);
                INSERT OR IGNORE INTO control VALUES(1,0);
                CREATE TRIGGER IF NOT EXISTS frozen_case BEFORE UPDATE ON cases BEGIN SELECT RAISE(ABORT,'immutable Case'); END;
                CREATE TRIGGER IF NOT EXISTS frozen_revision BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT,'immutable Revision'); END;
            ''')

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    def create(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError('실험 이름은 1~80자로 입력해 주세요')
        key = uid()
        with self.db() as db:
            db.execute('INSERT INTO studies VALUES(?,?,NULL,?)', (key, name.strip(), time.time()))
        return key

    def list(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM studies ORDER BY created DESC')]

    def detail(self, study):
        with self.db() as db:
            row = db.execute('SELECT * FROM studies WHERE id=?', (study,)).fetchone()
            if row is None:
                raise ValueError('실험을 찾을 수 없습니다')
            result = dict(row)
            result['revisions'] = [dict(r) for r in db.execute('SELECT * FROM revisions WHERE study_id=? ORDER BY created', (study,))]
            for rev in result['revisions']:
                rev['data'] = json.loads(rev['data'])
            result['cases'] = [dict(r) for r in db.execute('SELECT c.* FROM cases c JOIN revisions r ON c.revision_id=r.id WHERE r.study_id=?', (study,))]
            for case in result['cases']:
                case['input'] = json.loads(case['input'])
            result['attempts'] = [dict(r) for r in db.execute('SELECT a.* FROM attempts a JOIN cases c ON a.case_id=c.id JOIN revisions r ON c.revision_id=r.id WHERE r.study_id=? ORDER BY a.created', (study,))]
            for attempt in result['attempts']:
                attempt['result'] = json.loads(attempt['result']) if attempt['result'] else None
            result['paused'] = bool(db.execute('SELECT paused FROM control WHERE id=1').fetchone()[0])
        return result

    def commit(self, study, design, preview_hash, expected_revision):
        preview = candidates(design)
        if preview['preview_hash'] != preview_hash:
            raise Conflict('후보가 변경되었습니다. 미리보기를 다시 확인해 주세요')
        revision = uid()
        code_hash = snapshot(self.root/'revisions'/revision/'code')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT current_revision FROM studies WHERE id=?', (study,)).fetchone()
            if row is None or row[0] != expected_revision:
                raise Conflict('실험 버전이 변경되었습니다. 다시 불러와 주세요')
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)', (revision, study, expected_revision, canonical(preview), code_hash, time.time()))
            keys = []
            for candidate in preview['candidates']:
                if candidate['valid']:
                    key = uid(); keys.append(key)
                    resolved = {**candidate['input'], 'code_hash': code_hash}
                    db.execute('INSERT INTO cases VALUES(?,?,?,?,?)', (key, revision, canonical(resolved), digest(resolved), candidate['baseline']))
            db.execute('UPDATE studies SET current_revision=? WHERE id=?', (revision, study))
        return {'revision': revision, 'cases': keys}

    def enqueue(self, case_ids, request_key, resume_from=None):
        if (not isinstance(case_ids, list) or not 1 <= len(case_ids) <= 33 or len(set(case_ids)) != len(case_ids)
                or not all(isinstance(k, str) for k in case_ids) or not isinstance(request_key, str) or not 1 <= len(request_key) <= 128):
            raise ValueError('예약할 후보와 요청 ID를 확인해 주세요')
        payload = digest({'cases': case_ids, 'resume_from': resume_from})
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM requests WHERE key=?', (request_key,)).fetchone()
            if old:
                if old['payload_hash'] != payload:
                    raise Conflict('요청 ID가 다른 예약에 사용됐습니다')
                return json.loads(old['response'])
            ids = []
            for key in case_ids:
                case = db.execute('SELECT input FROM cases WHERE id=?', (key,)).fetchone()
                if not case:
                    raise ValueError('확정된 후보를 찾을 수 없습니다')
                if json.loads(case['input']).get('profile') != CAPABILITIES['profile']:
                    raise ValueError('저장고 후보는 형상 검토·저장 단계입니다. 실제 저장고 수송 어댑터 연결 전에는 실행할 수 없습니다')
                if db.execute("SELECT 1 FROM attempts WHERE case_id=? AND state IN ('queued','running','recovery_required')", (key,)).fetchone():
                    raise Conflict('이미 예약·실행 중이거나 복구 확인이 필요한 후보입니다')
                if resume_from:
                    old_attempt = db.execute('SELECT * FROM attempts WHERE id=? AND case_id=?', (resume_from, key)).fetchone()
                    if not old_attempt or old_attempt['state'] not in ('failed', 'finished') or len(case_ids) != 1:
                        raise ValueError('종료된 동일 후보의 체크포인트만 재개할 수 있습니다')
                attempt = uid(); ids.append(attempt)
                db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?)', (attempt, key, 'queued', 'unchecked', None, time.time(), None, resume_from))
            response = {'attempts': ids}
            db.execute('INSERT INTO requests VALUES(?,?,?)', (request_key, payload, canonical(response)))
        return response

    def pause(self, paused):
        if not isinstance(paused, bool):
            raise ValueError('paused는 참/거짓이어야 합니다')
        with self.db() as db:
            db.execute('UPDATE control SET paused=? WHERE id=1', (int(paused),))

    def cancel_queued(self, attempt):
        with self.db() as db:
            if db.execute("UPDATE attempts SET state='cancelled' WHERE id=? AND state='queued'", (attempt,)).rowcount != 1:
                raise Conflict('대기 중인 작업만 취소할 수 있습니다')

    def wake(self):
        def requested_run():
            # 예약과 작업자 종료가 겹쳐도 단일 소유자 잠금 아래 대기열을 재확인한다.
            for _ in range(3):
                self.drain()
                time.sleep(.1)
        threading.Thread(target=requested_run, daemon=True).start()

    def drain(self):
        with owner_lock(self.root/'worker.lock') as locked:
            if not locked:
                return
            owner = f'{os.getpid()}:{uid()}'
            with self.db() as db:
                # 앱 연결 상실은 솔버 종료의 증거가 아니므로 자동 재실행하지 않는다.
                db.execute("UPDATE attempts SET state='recovery_required' WHERE state='running'")
            while True:
                with self.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if db.execute('SELECT paused FROM control').fetchone()[0] or db.execute("SELECT 1 FROM attempts WHERE state='recovery_required'").fetchone():
                        return
                    row = db.execute("SELECT a.*,c.input,c.input_hash,c.revision_id FROM attempts a JOIN cases c ON a.case_id=c.id WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
                    if not row:
                        return
                    row = dict(row)
                    db.execute("UPDATE attempts SET state='running',owner=? WHERE id=? AND state='queued'", (owner, row['id']))
                folder = self.root/'attempts'/row['id']
                try:
                    spec = json.loads(row['input'])
                    if digest(spec) != row['input_hash']:
                        raise ValueError('불변 입력의 해시가 일치하지 않습니다')
                    code = self.root/'revisions'/row['revision_id']/'code'
                    verify_snapshot(code, spec['code_hash'])
                    if shutil.disk_usage(self.root).free < 256*1024**2:
                        raise OSError('검증 예제 실행용 디스크 여유가 부족합니다 (최소 256 MiB)')
                    folder.mkdir(parents=True, exist_ok=False)
                    (folder/'input.json').write_text(canonical(spec), encoding='utf-8')
                    checks = self.adapter(folder, spec, code, row['resume_from'])
                    quality = 'pass' if checks.get('pass') is True else 'fail'
                    result = {'checks': checks}
                    if (folder/'metrics.json').exists():
                        result['metrics'] = json.loads((folder/'metrics.json').read_text(encoding='utf-8'))
                    if quality == 'pass' and self.project_root and (folder/'viewer').exists():
                        project = self.project_root/('Study_'+row['id'])
                        shutil.copytree(folder/'viewer', project)
                        meta = json.loads((project/'meta.json').read_text(encoding='utf-8'))
                        meta['name'] = 'Study '+row['case_id'][:8]+' / '+row['id'][:6]
                        meta['study_case_id'] = row['case_id']
                        meta['study_attempt_id'] = row['id']
                        (project/'meta.json').write_text(canonical(meta), encoding='utf-8')
                        result['project_id'] = meta['run_id']
                        result['project_folder'] = project.name
                    with self.db() as db:
                        db.execute("UPDATE attempts SET state='finished',quality=?,result=? WHERE id=? AND owner=?", (quality, canonical(result), row['id'], owner))
                except Exception as exc:
                    with self.db() as db:
                        db.execute("UPDATE attempts SET state='failed',quality='unchecked',result=? WHERE id=? AND owner=?", (canonical({'error': str(exc)}), row['id'], owner))
                        if isinstance(exc, OSError):
                            db.execute('UPDATE control SET paused=1')

    def _real_adapter(self, folder, spec, code, resume_from):
        prefix = []
        paths = [str(code), str(folder)]
        if resume_from:
            paths.append(str(self.root/'attempts'/resume_from/'raw'))
        if os.name == 'nt':
            prefix = ['wsl.exe']
            if self.settings.get('wsl_distro'):
                prefix += ['-d', self.settings['wsl_distro']]
            paths = [subprocess.check_output(prefix+['--', 'wslpath', '-u', p], text=True, timeout=15).strip() for p in paths]
            prefix += ['--']
        bashrc = self.settings.get('openfoam_bashrc', 'auto')
        load = ('rcs=(/usr/lib/openfoam/openfoam*/etc/bashrc); test -f "${rcs[-1]}" && source "${rcs[-1]}"'
                if bashrc == 'auto' else 'source '+shlex.quote(bashrc))
        command = load+' && cd '+shlex.quote(paths[0])+' && python3 -m study_platform.runner '+shlex.quote(paths[1])
        if resume_from:
            command += ' --resume '+shlex.quote(paths[2])
        with (folder/'execution.log').open('w') as log:
            result = subprocess.run(prefix+['bash', '-c', command], stdout=log, stderr=subprocess.STDOUT)
        checks = folder/'raw/checks.json'
        if not checks.exists():
            raise OSError(f'계산 환경 또는 실행 오류 ({result.returncode}). execution.log를 확인해 주세요')
        verdict = json.loads(checks.read_text(encoding='utf-8'))
        if result.returncode != 0 and verdict.get('pass'):
            raise RuntimeError(f'수치 검사 후 처리 오류 ({result.returncode}). execution.log를 확인해 주세요')
        return verdict

    def comparison(self, study):
        detail = self.detail(study)
        rows, excluded = [], []
        cases_by_id = {c['id']: c for c in detail['cases']}
        for attempt in detail['attempts']:
            case = cases_by_id[attempt['case_id']]
            if case['revision_id'] != detail['current_revision']:
                continue
            if attempt['state'] != 'finished' or attempt['quality'] != 'pass' or not (attempt['result'] or {}).get('metrics'):
                excluded.append({'attempt': attempt['id'], 'reason': f"{attempt['state']} / {attempt['quality']}"})
                continue
            revision = next(r for r in detail['revisions'] if r['id'] == case['revision_id'])
            variable = revision['data']['variable_definition']
            rows.append({'attempt': attempt['id'], 'case': case['id'], 'baseline': case['baseline'],
                         'input_hash': case['input_hash'], 'changed_variable': variable,
                         'value': case['input']['parameters'][variable['key']], **attempt['result']})
        windows = {canonical(r['metrics']['evaluation_window_s']) for r in rows}
        if len(windows) > 1:
            raise Conflict('물리시간 구간이 달라 직접 비교할 수 없습니다')
        return {'definition': 'equal_cell_volume_mean_v1', 'unit': 'C/C_ref', 'time_unit': 's',
                'rows': rows, 'excluded': excluded, 'ranking': None, 'experimental_validation': False}
