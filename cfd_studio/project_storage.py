"""Portable project folders. The Studio registry stores locations, never solver inputs."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


def read(path, default=None):
    from cfd_studio.execution_workspace import read_json
    return read_json(path, default)


def write(path, value):
    from cfd_studio.execution_workspace import atomic_json
    atomic_json(path, value)


def project_path(value):
    """Keep the exact chosen folder, including non-C Windows drives."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('프로젝트 저장 폴더를 지정하세요')
    raw = value.strip().strip('"')
    if '\x00' in raw:
        raise ValueError('올바른 저장 경로를 입력하세요')
    if os.name != 'nt' and re.match(r'^[A-Za-z]:[\\/]', raw):
        raw = '/mnt/'+raw[0].lower()+'/'+raw[3:].replace('\\', '/')
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError('드라이브를 포함한 전체 경로를 입력하세요')
    path = path.resolve()
    if path == Path(path.anchor) or re.fullmatch(r'/mnt/[a-z]', str(path)):
        raise ValueError('드라이브 안의 프로젝트 폴더를 지정하세요')
    return path


def writable(path):
    if not path.is_dir():
        raise ValueError('프로젝트 드라이브 또는 폴더가 연결되어 있지 않습니다: '+str(path))
    probe = path/('.studio-write-'+uuid.uuid4().hex)
    try:
        with probe.open('xb') as stream:
            stream.write(b'project storage check')
    finally:
        probe.unlink(missing_ok=True)


def remap(value, mappings):
    if isinstance(value, dict):
        return {k: (v if k in ('config', 'baseline') else remap(v, mappings)) for k, v in value.items()}
    if isinstance(value, list):
        return [remap(v, mappings) for v in value]
    if isinstance(value, str):
        canonical = value.replace('\\', '/')
        for old, new in mappings:
            old = str(old).replace('\\', '/').rstrip('/')
            if canonical.casefold() == old.casefold() or canonical.casefold().startswith(old.casefold()+'/'):
                return str(new)+canonical[len(old):].replace('/', os.sep)
    return value


def copy_verified(source, target):
    """Copy to a new destination; retain the original even after verification."""
    source, target = Path(source), Path(target)
    target.mkdir(parents=True, exist_ok=False)
    marker = target/'.copy-incomplete'
    marker.touch()
    shutil.copytree(source, target, symlinks=False, dirs_exist_ok=True)
    for base, _, files in os.walk(source, followlinks=True):
        for name in files:
            old = Path(base)/name
            new = target/old.relative_to(source)
            def digest(path):
                with path.open('rb') as stream:
                    return hashlib.file_digest(stream, 'sha256').digest()
            if old.stat().st_size != new.stat().st_size or digest(old) != digest(new):
                raise ValueError('복사 검증 실패: '+str(old))
    marker.unlink()



class ProjectStorage:
    def project_defaults(self):
        standard = self.root/'cfd_studio/_runtime/executions'
        base = self.root/'cfd_studio/Projects' if self.folder == standard else self.folder.parent/'Projects'
        return {'base_path': str(base.resolve())}

    def prepare_project_folder(self, project, location=None):
        if not location:
            safe = re.sub(r'[\\/:*?"<>|]', '_', project['name']).strip('. ')
            location = str(Path(self.project_defaults()['base_path'])/(safe+'_'+project['id'][:8]))
        path = project_path(location)
        for existing in self.stored_projects():
            if existing.get('storage_path') and existing['id'] != project['id']:
                other = project_path(existing['storage_path'])
                if path == other or path in other.parents or other in path.parents:
                    raise ValueError('다른 프로젝트와 겹치지 않는 폴더를 지정하세요')
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError('비어 있는 프로젝트 폴더를 지정하세요. 기존 프로젝트는 열기로 연결하세요.')
        # Do not create a fake mount point when a Windows drive is disconnected.
        if re.match(r'^/mnt/[a-z]/', str(path)) and not Path(*path.parts[:3]).is_mount():
            if not Path(*path.parts[:3]).exists():
                raise ValueError('선택한 드라이브가 연결되어 있지 않습니다')
        path.mkdir(parents=True, exist_ok=True)
        writable(path)
        for name in ('ProjectSettings', 'Cases', 'Results', 'Cache'):
            (path/name).mkdir(exist_ok=True)
        project['storage_path'] = str(path)
        project.setdefault('linked_results', [])
        write(path/'project.cfdproj', {**project, 'schema': 1})
        return path

    def persist_catalog(self, data):
        """Write manifests before publishing registry changes; restore on write failure."""
        backups = []
        try:
            for project in data['projects']:
                if not project.get('storage_path'):
                    self.prepare_project_folder(project)
                root = project_path(project['storage_path'])
                manifest = root/'project.cfdproj'
                if not root.is_dir():
                    continue  # Offline projects remain listed, with an explicit availability state.
                value = {**project, 'schema': 1}
                if read(manifest) != value:
                    backups.append((manifest, read(manifest)))
                    write(manifest, value)
            write(self.folder/'projects.json', data)
        except Exception:
            for path, value in reversed(backups):
                if value is not None:
                    write(path, value)
            raise

    def stored_projects(self):
        return read(self.folder/'projects.json', {'projects': []})['projects']

    def project_folder(self, project_id):
        project = next((p for p in self.stored_projects() if p['id'] == project_id), None)
        if not project or not project.get('storage_path'):
            raise ValueError('프로젝트 저장 위치를 지정하세요')
        path = project_path(project['storage_path'])
        writable(path)
        manifest = read(path/'project.cfdproj', {})
        if manifest.get('id') != project_id:
            raise ValueError('프로젝트 파일을 찾을 수 없습니다. 드라이브 연결과 저장 경로를 확인하세요.')
        return path

    def managed_result_entries(self):
        entries = []
        for p in self.stored_projects():
            if not p.get('storage_path'):
                continue
            root = project_path(p['storage_path'])
            for item in p.get('linked_results', []):
                path = project_path(item['path']) if item.get('external') else root/item['path']
                entries.append({**item, 'path': str(path), 'project_id': p['id']})
            for path in [*root.glob('Results/*'), *root.glob('Cases/*/Attempts/*/Results/*')]:
                if (path/'meta.json').is_file():
                    entries.append({'path': str(path), 'kind': 'legacy', 'project_id': p['id']})
            for path in root.glob('Cases/*/Attempts/*/Raw/warehouse_transport_*'):
                entries.append({'path': str(path), 'kind': 'warehouse', 'project_id': p['id']})
        return entries

    def result_path(self, rid, kind):
        for item in self.managed_result_entries():
            path = Path(item['path'])
            if item['kind'] != kind:
                continue
            if kind == 'warehouse' and path.name == rid:
                return path
            if kind == 'legacy':
                meta = read(path/'meta.json', {})
                if str(meta.get('run_id') or meta.get('project_id')) == str(rid):
                    return path
        return None

    def attempt_folder(self, project_id, case_id, attempt):
        return self.project_folder(project_id)/'Cases'/case_id.removeprefix('case:')/'Attempts'/attempt

    def read_project_queue(self):
        q = read(self.folder/'queue.json', {'schema': 1, 'paused': True, 'active': None, 'order': [], 'cases': {}, 'failure': None})
        if q.get('schema') == 1:
            return q
        q['cases'] = {}
        for project in self.stored_projects():
            root = project_path(project['storage_path'])
            file = root/'ProjectSettings/executions.json'
            if not (root/'project.cfdproj').is_file():
                if any(key in q.get('order', []) or key == q.get('active') for key in project.get('runs', [])):
                    q['paused'] = True
                    q['service_error'] = '대기열 프로젝트 드라이브 연결을 확인하세요: '+project['name']
                continue
            local = read(file, {'cases': {}})
            q['cases'].update(local['cases'])
        return q

    def write_project_queue(self, q):
        backups = []
        try:
            for project in self.stored_projects():
                subset = {k: c for k, c in q['cases'].items() if c['project_id'] == project['id']}
                path = project_path(project['storage_path'])/'ProjectSettings/executions.json'
                local = {'schema': 1, 'cases': subset, 'order': [k for k in q['order'] if k in subset],
                         'active': q['active'] if q['active'] in subset else None,
                         'failure': q['failure'] if q['failure'] in subset else None, 'paused': q['paused']}
                if not path.parent.is_dir() and not subset:
                    continue
                if read(path) == local:
                    continue
                self.project_folder(project['id'])
                backups.append((path, read(path)))
                write(path, local)
            write(self.folder/'queue.json', {**{k: v for k, v in q.items() if k != 'cases'}, 'schema': 2})
        except Exception:
            for path, old in reversed(backups):
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    write(path, old)
            raise

    def relocate_project(self, key, location):
        """Copy into the selected folder, verify, then switch. No source deletion."""
        with self.lock:
            if self.busy() or getattr(self, 'storage_busy', lambda: False)() or self.queue_data().get('active'):
                raise ValueError('계산·결과 저장이 끝난 뒤 프로젝트 위치를 변경하세요')
            records = self.discover()
            data = self._catalog(records)
            p = next((p for p in data['projects'] if p['id'] == key), None)
            if not p:
                raise ValueError('프로젝트를 찾을 수 없습니다')
            source, target = self.project_folder(key), project_path(location)
            if target == source:
                return p
            for existing in data['projects']:
                other = project_path(existing['storage_path'])
                if target == other or target in other.parents or other in target.parents:
                    raise ValueError('기존 프로젝트와 겹치지 않는 폴더를 지정하세요')
            if target.exists():
                if not target.is_dir() or any(target.iterdir()):
                    raise ValueError('비어 있는 새 프로젝트 폴더를 지정하세요')
                target.rmdir()
            q = self.queue_data()
            self.save_queue(q)
            copy_verified(source, target)
            incomplete = target/'.storage-incomplete'
            incomplete.touch()
            mappings = [(source, target)]
            linked = []
            try:
                for rid in p['runs']:
                    record = records.get(rid)
                    if not record or not record.get('path'):
                        continue
                    old = project_path(record['path'])
                    if old.is_relative_to(source) or (not old.exists() and not record.get('has_results')):
                        continue
                    dest = target/'Results'/old.name
                    if dest.exists():
                        raise ValueError('결과 폴더 이름 충돌: '+old.name)
                    copy_verified(old, dest)
                    mappings.insert(0, (old, dest))
                    # Legacy Raw can live outside the Viewer folder. Preserve it as well.
                    meta = read(dest/'meta.json', {})
                    raw = meta.get('raw_archive_run')
                    if raw and project_path(raw).is_dir() and not project_path(raw).is_relative_to(old):
                        raw_target = dest/'Raw_Data'
                        copy_verified(project_path(raw), raw_target)
                        mappings.insert(0, (project_path(raw), raw_target))
                    linked.append({'path': str(dest.relative_to(target)), 'kind': record['kind']})
                for file in target.rglob('*.json'):
                    if file.name not in ('executions.json', 'job.json', 'meta.json', 'storage_complete.json'):
                        continue
                    original = read(file)
                    updated = remap(original, mappings)
                    if updated != original:
                        write(file, updated)
                for meta_file in target.rglob('meta.json'):
                    if not (meta_file.parent/'case_config.json').is_file():
                        continue
                    meta = read(meta_file, {})
                    if meta.get('run_id') or meta.get('project_id'):
                        meta.update(execution_project_id=key, raw_archive_root=str(meta_file.parent),
                                    raw_archive_run=str(meta_file.parent/'Raw_Data'))
                        write(meta_file, meta)
                p['storage_path'] = str(target)
                p['linked_results'] = [i for i in p.get('linked_results', []) if not i.get('external')]+linked
                # Cases and attempts use new paths; committed after all files verify.
                q = remap(q, mappings)
                local = {'schema': 1, 'cases': {k:c for k,c in q['cases'].items() if c['project_id'] == key},
                         'order': [k for k in q['order'] if q['cases'][k]['project_id'] == key], 'paused': True, 'active': None, 'failure': None}
                write(target/'ProjectSettings/executions.json', local)
                incomplete.unlink()
                self.persist_catalog(data)
                return p
            except Exception:
                # Leave the verified/partial copy for inspection; registry stays on old storage.
                raise

    def open_project(self, location):
        with self.lock:
            root = project_path(location)
            writable(root)
            if any((root/name).exists() for name in ('.copy-incomplete', '.storage-incomplete')):
                raise ValueError('복사가 완료되지 않은 프로젝트입니다. 원본 프로젝트를 여세요.')
            p = read(root/'project.cfdproj', {})
            if p.get('schema') != 1 or not re.fullmatch(r'[a-f0-9]{32}', p.get('id', '')) or not isinstance(p.get('runs'), list):
                raise ValueError('CFD Studio 프로젝트 폴더가 아닙니다')
            existing = next((v for v in self.stored_projects() if v['id'] == p['id']), None)
            if existing:
                if project_path(existing['storage_path']) == root:
                    return existing
                if (project_path(existing['storage_path'])/'project.cfdproj').is_file():
                    raise ValueError('같은 프로젝트가 다른 경로에 연결되어 있습니다. 프로젝트 설정에서 위치를 변경하세요.')
            for other in self.stored_projects():
                if other['id'] == p['id']:
                    continue
                other_root = project_path(other['storage_path'])
                if root == other_root or root in other_root.parents or other_root in root.parents:
                    raise ValueError('다른 프로젝트와 겹치지 않는 폴더를 지정하세요')
            local = read(root/'ProjectSettings/executions.json', {'cases': {}, 'order': []})
            if not isinstance(local.get('cases'), dict) or not isinstance(local.get('order', []), list):
                raise ValueError('프로젝트 실행 목록 형식을 확인하세요')
            for key, case in local['cases'].items():
                if not isinstance(case, dict) or case.get('project_id') != p['id'] or case.get('id') != key:
                    raise ValueError('다른 프로젝트의 실행 설정이 포함되어 있습니다')
                if case.get('status') == 'running':
                    raise ValueError('실행 중인 프로젝트는 원래 Studio에서 완료 후 여세요')
            order = local.get('order', [])
            if any(key not in local['cases'] for key in order) or len(order) != len(set(order)):
                raise ValueError('프로젝트 대기열 형식을 확인하세요')
            data = self._catalog(self.discover())
            q = self.queue_data()
            if any(key in q['cases'] and q['cases'][key]['project_id'] != p['id'] for key in local['cases']):
                raise ValueError('다른 프로젝트와 실행 ID가 겹칩니다')
            old = p.get('storage_path', str(root))
            files = [*root.glob('ProjectSettings/*.json'), *root.glob('Cases/*/Attempts/*/job.json'),
                     *root.glob('Results/*/meta.json'), *root.glob('Cases/*/Attempts/*/Results/*/meta.json')]
            # Preserve exact bytes before publishing any imported paths or queue entries.
            protected = set(files) | {root/'project.cfdproj', root/'ProjectSettings/executions.json',
                                      self.folder/'projects.json', self.folder/'queue.json'}
            for item in data['projects']:
                base = project_path(item['storage_path'])
                protected.update((base/'project.cfdproj', base/'ProjectSettings/executions.json'))
            backups = {file: file.read_bytes() if file.is_file() else None for file in protected}
            try:
                for file in files:
                    value = read(file)
                    updated = remap(value, [(old, root)])
                    if updated != value:
                        write(file, updated)
                p['storage_path'] = str(root)
                data['projects'] = [p if item['id'] == p['id'] else item for item in data['projects']] if existing else data['projects']+[p]
                self.persist_catalog(data)
                q['cases'].update(remap(local['cases'], [(old, root)]))
                q['order'] += [k for k in order if k not in q['order']]
                q['paused'] = True
                q.pop('service_error', None)
                self.save_queue(q)
            except Exception:
                for file, raw in backups.items():
                    if raw is None:
                        file.unlink(missing_ok=True)
                    elif not file.is_file() or file.read_bytes() != raw:
                        temp = file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp')
                        try:
                            temp.write_bytes(raw)
                            os.replace(temp, file)
                        finally:
                            temp.unlink(missing_ok=True)
                raise
            return p

    def pick_project_folder(self, start=''):
        if os.name != 'nt':
            raise ValueError('프로젝트 경로를 직접 입력하세요')
        env = os.environ.copy()
        env['CFD_PROJECT_PICK_START'] = str(start)
        command = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new();Add-Type -AssemblyName System.Windows.Forms;"
                   "$d=New-Object System.Windows.Forms.FolderBrowserDialog;$d.Description='프로젝트 폴더 선택';"
                   "$d.ShowNewFolderButton=$true;if(Test-Path -LiteralPath $env:CFD_PROJECT_PICK_START){$d.SelectedPath=$env:CFD_PROJECT_PICK_START};"
                   "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){[Console]::Write($d.SelectedPath)}")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-STA', '-Command', command], capture_output=True,
                                env=env, timeout=600, creationflags=0x08000000)
        if result.returncode:
            raise ValueError('폴더 선택 창을 열지 못했습니다. 경로를 직접 입력하세요.')
        path = result.stdout.decode('utf-8').strip()
        return {'path': path, 'cancelled': not bool(path)}
