"""공통 설정 UI 전용 서버. 운영 앱을 import하거나 CFD를 실행하지 않는다."""
import argparse
import ast
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_config_presets import TREE, app_functions, preset


def serve(folder, port):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    namespace = app_functions(folder/'configs')
    namespace['saved_config_types'] = lambda: {
        p.stem: json.loads(p.read_text(encoding='utf-8')).get('_해석유형', 'immersion')
        for p in (folder/'configs').glob('*.json')}
    html = next(ast.literal_eval(n.value) for n in TREE.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INDEX_HTML' for t in n.targets))
    html = html.replace('__APP_VER__', '설정 검토용 · 실행 없음').replace(
        '__TRACER_VIEWER__', (ROOT/'cfd_studio/tracer_viewer.js').read_text(encoding='utf-8'))
    silo = preset('grain_silo')

    class Handler(namespace['H']):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == '/':
                self._send(200, html.encode(), 'text/html; charset=utf-8')
            elif url.path == '/api/info':
                self._json({'config': preset(), 'conditions': [], 'projects': [], 'rid': '',
                            'saved_configs': namespace['saved_configs'](), 'config_source': 'case',
                            'data': {}, 'frames': [], 'bubs': [], 'flows': [], 'therms': [],
                            'phases': [], 'pressures': [], 'turbulences': []})
            elif url.path == '/api/config':
                name = (parse_qs(url.query).get('saved') or [''])[0]
                path = folder/'configs'/(namespace['cfg_safe'](name)+'.json')
                self._json({'ok': True, 'config': json.loads(path.read_text(encoding='utf-8')) if name and path.is_file() else preset()})
            elif url.path == '/api/silo/info':
                self._json({'ok': True, 'config': silo})
            elif url.path == '/api/status':
                self._json({'running': False, 'wsl': False, 'case': False, 'snap_times': [], 'log': '',
                            'extract': {'busy': False, 'done': 0, 'total': 0, 'msg': ''}})
            elif url.path == '/api/projects':
                self._json({'cur': '', 'projects': []})
            else:
                self._json({})

        def do_POST(self):
            if urlparse(self.path).path == '/api/config-save':
                super().do_POST()
            elif urlparse(self.path).path == '/api/uistate':
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self._json({'ok': True})
            else:
                self._json({'ok': False, 'msg': '설정 검토 서버에서는 실행할 수 없습니다'}, 409)

    print(json.dumps({'port': port, 'output': str(folder), 'solver_enabled': False}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('new_folder', type=Path)
    parser.add_argument('--port', type=int, default=8751)
    args = parser.parse_args()
    serve(args.new_folder, args.port)
