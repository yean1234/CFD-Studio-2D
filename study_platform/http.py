"""기존 Studio HTTP 서버에 연결되는 실험 관리 경로."""
import base64
import json
from pathlib import Path
import re
import threading
import zipfile
from urllib.parse import urlparse
from .contracts import CAPABILITIES, VARIABLES, candidates
from .service import Service, Conflict, uid
from . import packages

_service = None
_lock = threading.Lock()


def service(here, settings, projects):
    global _service
    with _lock:
        if _service is None:
            _service = Service(Path(here)/'Studies', settings, projects)
    return _service


def get(handler, store):
    path = urlparse(handler.path).path
    try:
        if path == '/studies':
            handler._send(200, Path(__file__).with_name('ui.html').read_bytes(), 'text/html; charset=utf-8')
        elif path == '/studies/design':
            handler._send(200, Path(__file__).with_name('design.html').read_bytes(), 'text/html; charset=utf-8')
        elif path in ('/studies/three.module.js', '/studies/design.js'):
            file = Path(__file__).parent/('vendor/three.module.js' if path.endswith('three.module.js') else 'design.js')
            handler._send(200, file.read_bytes(), 'text/javascript; charset=utf-8')
        elif path == '/api/studies/schema':
            from .research_design import variable_schema
            handler._json(variable_schema())
        elif path == '/api/capabilities':
            handler._json({'capabilities': CAPABILITIES, 'variables': VARIABLES})
        elif path == '/api/studies':
            handler._json({'studies': store.list()})
        elif match := re.fullmatch(r'/api/studies/([a-f0-9]{32})(/comparison)?', path):
            handler._json(store.comparison(match[1]) if match[2] else store.detail(match[1]))
        elif match := re.fullmatch(r'/api/study-packages/([a-f0-9]{32})\.zip', path):
            handler._send_file(str(store.root/'packages'/(match[1]+'.zip')))
        elif match := re.fullmatch(r'/api/attempts/([a-f0-9]{32})/log', path):
            file = store.root/'attempts'/match[1]/'execution.log'
            handler._json({'log': file.read_text(encoding='utf-8', errors='replace')[-16000:] if file.exists() else '로그 준비 중'})
        else:
            return False
    except (ValueError, OSError) as exc:
        handler._json({'ok': False, 'code': 'NOT_AVAILABLE', 'msg': str(exc)}, 400)
    return True


def post(handler, store, body):
    path = urlparse(handler.path).path
    if not (path.startswith('/api/studies') or path.startswith('/api/study-queue') or path.startswith('/api/study-packages')):
        return False
    try:
        if not isinstance(body, dict):
            raise ValueError('JSON 객체를 입력해 주세요')
        if path == '/api/studies':
            result = {'id': store.create(body.get('name'))}
        elif path == '/api/study-queue':
            store.pause(body.get('paused'))
            if body.get('paused') is False:
                store.wake()
            result = {'paused': body['paused']}
        elif path == '/api/study-packages/import':
            data = base64.b64decode(body.get('base64', ''), validate=True)
            if not 0 < len(data) <= 20*1024*1024:
                raise ValueError('패키지는 20 MiB 이하여야 합니다')
            folder = store.root/'imports'
            folder.mkdir(exist_ok=True)
            key = uid(); archive = folder/(key+'.zip')
            archive.write_bytes(data)
            manifest = packages.import_package(archive, folder/key)
            result = {'id': key, 'level': manifest['level'], 'code_executed': False, 'files': len(manifest['files'])}
        elif match := re.fullmatch(r'/api/studies/([a-f0-9]{32})/(preview|commit|enqueue|export)', path):
            study, action = match[1], match[2]
            detail = store.detail(study)
            if action == 'preview':
                result = candidates(body.get('design'))
            elif action == 'commit':
                result = store.commit(study, body.get('design'), body.get('preview_hash'), body.get('expected_revision'))
            elif action == 'enqueue':
                case_ids = body.get('cases', [])
                if not set(case_ids) <= {c['id'] for c in detail['cases']}:
                    raise ValueError('다른 실험의 후보가 포함되어 있습니다')
                result = store.enqueue(case_ids, body.get('request_id'))
                store.wake()
            else:
                result = packages.export(store, study)
        else:
            raise ValueError('지원하지 않는 실험 작업입니다')
        handler._json({'ok': True, 'result': result})
    except Conflict as exc:
        handler._json({'ok': False, 'code': 'CONFLICT', 'msg': str(exc)}, 409)
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        handler._json({'ok': False, 'code': 'INVALID_INPUT', 'msg': str(exc)}, 400)
    return True
