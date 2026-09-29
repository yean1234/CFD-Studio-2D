"""Studio geometry editor and isolated mesh jobs; never launches a gas solver."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from zipfile import BadZipFile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tracer_transport.warehouse_geometry import validate
from cfd_studio.warehouse_results import WarehouseResults


class Workspace:
    def __init__(self, folder, settings):
        self.folder = Path(folder)
        self.settings = settings
        self.lock = threading.Lock()
        self.jobs = {}
        for path in (self.folder/'checks').glob('*/job.json'):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job['status'] in ('queued', 'running'):
                    job.update(status='failed', error='이전 실행이 중단되었습니다. 새 검사를 실행해 주세요.')
                self.jobs[job['id']] = job
            except (OSError, ValueError, KeyError):
                continue

    def read(self):
        template = json.loads((ROOT/'tracer_transport/warehouse_geometry_20260925.json').read_text(encoding='utf-8'))
        presets = []
        for path in sorted((self.folder/'settings').glob('*.json')):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                presets.append({'id': path.stem, **item})
            except (OSError, ValueError):
                continue
        with self.lock:
            jobs = copy.deepcopy(list(self.jobs.values()))
        return {'template': template, 'settings': presets, 'jobs': jobs, 'transport_ready': False}

    def save(self, body):
        name = body.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError('설정 이름은 1~80자로 입력해 주세요')
        spec = body.get('geometry_spec')
        validate(spec)
        record = {'name': name.strip(), 'geometry_spec': spec, 'created': time.time(),
                  'stage': 'geometry_only', 'target_species': 'ClO2', 'transport_ready': False}
        key = uuid.uuid4().hex
        folder = self.folder/'settings'
        folder.mkdir(parents=True, exist_ok=True)
        with (folder/(key+'.json')).open('x', encoding='utf-8') as out:
            json.dump(record, out, ensure_ascii=False, indent=2, allow_nan=False)
        return {'id': key, **record}

    def start(self, key):
        if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{32}', key):
            raise ValueError('저장된 설정을 선택해 주세요')
        record = json.loads((self.folder/'settings'/(key+'.json')).read_text(encoding='utf-8'))
        validate(record['geometry_spec'])
        with self.lock:
            if any(j['status'] in ('queued', 'running') for j in self.jobs.values()):
                raise ValueError('격자 검사가 진행 중입니다')
            job_id = uuid.uuid4().hex
            job = {'id': job_id, 'setting_id': key, 'name': record['name'], 'status': 'queued', 'created': time.time()}
            self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id, record), daemon=True).start()
        return copy.deepcopy(job)

    def _run(self, key, record):
        folder = self.folder/'checks'/key
        try:
            folder.mkdir(parents=True, exist_ok=False)
            config = folder/'input.json'
            config.write_text(json.dumps(record['geometry_spec'], ensure_ascii=False), encoding='utf-8')
            with self.lock:
                self.jobs[key]['status'] = 'running'
                (folder/'job.json').write_text(json.dumps(self.jobs[key], ensure_ascii=False), encoding='utf-8')
            root, cfg, out = str(ROOT), str(config.resolve()), str((folder/'mesh').resolve())
            prefix = []
            if os.name == 'nt':
                prefix = ['wsl.exe']
                distro = self.settings.get('wsl_distro')
                if distro:
                    prefix += ['-d', distro]
                paths = []
                for path in (root, cfg, out):
                    paths.append(subprocess.check_output(prefix+['--', 'wslpath', '-u', path], text=True, timeout=15, creationflags=0x08000000 if os.name == 'nt' else 0).strip())
                root, cfg, out = paths
                prefix += ['--']
            bashrc = self.settings.get('openfoam_bashrc', 'auto')
            if bashrc == 'auto':
                load = ('shopt -s nullglob; rcs=(/usr/lib/openfoam/openfoam*/etc/bashrc /opt/openfoam*/etc/bashrc); '
                        'if ((${#rcs[@]})); then source "${rcs[-1]}"; '
                        'else echo "OpenFOAM environment not found" >&2; exit 1; fi')
            else:
                load = 'source '+shlex.quote(bashrc)
            command = (load+' && cd '+shlex.quote(root)+' && python3 -m tracer_transport.warehouse_geometry'
                       +' --config '+shlex.quote(cfg)+' --output '+shlex.quote(out)+' --check-mesh')
            with (folder/'execution.log').open('w', encoding='utf-8') as log:
                subprocess.run(prefix+['bash', '-c', command], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=660, creationflags=0x08000000 if os.name == 'nt' else 0)
            report = json.loads((folder/'mesh/geometry_report.json').read_text(encoding='utf-8'))
            with self.lock:
                self.jobs[key].update(status='complete', report=report, folder=str(folder))
        except Exception as exc:
            with self.lock:
                self.jobs[key].update(status='failed', error=str(exc), folder=str(folder))
        finally:
            with self.lock:
                result = copy.deepcopy(self.jobs[key])
            if folder.exists():
                (folder/'job.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def get_route(handler, path, workspace):
    if path == '/warehouse':
        handler._send(200, (Path(__file__).with_name('warehouse_workspace.html')).read_bytes(), 'text/html; charset=utf-8')
    elif path == '/api/warehouse':
        handler._json(workspace.read())
    elif path == '/warehouse/results':
        handler._send(200, (Path(__file__).with_name('warehouse_results.html')).read_bytes(), 'text/html; charset=utf-8')
    elif path == '/warehouse/results.js':
        handler._send(200, (Path(__file__).with_name('warehouse_results.js')).read_bytes(), 'text/javascript; charset=utf-8')
    elif path.startswith('/api/warehouse/results'):
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(handler.path).query)
        results = WarehouseResults(ROOT/'output', getattr(workspace, 'resolve_result', None), getattr(workspace, 'result_paths', None))
        try:
            if path == '/api/warehouse/results':
                payload = {'results': results.list()}
            elif path == '/api/warehouse/results/meta':
                payload = results.metadata(query.get('id', [''])[0])
            elif path == '/api/warehouse/results/frame':
                maximum = int(query.get('maximum_points', ['25000'])[0])
                if not 1 <= maximum <= 125000:
                    raise ValueError('표시 셀 수는 1~125000 범위여야 합니다')
                payload = results.frame(query.get('id', [''])[0], int(query.get('index', [''])[0]), maximum_points=maximum)
            elif path == '/api/warehouse/results/sample':
                payload = results.sample(query.get('id', [''])[0],
                                         [float(query.get(k, [''])[0]) for k in ('x', 'y', 'z')],
                                         float(query.get('time', [''])[0]),
                                         float(query.get('max_distance', [''])[0]))
            else:
                return False
            handler._json(payload)
        except (ValueError, KeyError, TypeError, OSError, BadZipFile, EOFError) as exc:
            handler._json({'error': str(exc)}, 400)
    else:
        return False
    return True


def post_route(handler, path, body, workspace):
    if path not in ('/api/warehouse/save', '/api/warehouse/check'):
        return False
    try:
        if not isinstance(body, dict):
            raise ValueError('JSON 객체가 필요합니다')
        result = workspace.save(body) if path.endswith('/save') else workspace.start(body.get('id'))
        handler._json({'ok': True, 'result': result})
    except (ValueError, TypeError, KeyError, OSError) as exc:
        handler._json({'ok': False, 'msg': str(exc)}, 400)
    return True
