"""Read-only local server for warehouse-result screen review; no solver routes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
from zipfile import BadZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cfd_studio.warehouse_results import WarehouseResults


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, content, kind):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        url = urlparse(self.path)
        files = {'/warehouse/results': ROOT/'cfd_studio/warehouse_results.html',
                 '/warehouse/results.js': ROOT/'cfd_studio/warehouse_results.js',
                 '/studies/three.module.js': ROOT/'study_platform/vendor/three.module.js'}
        if url.path in files:
            kind = 'text/html' if url.path.endswith('results') else 'text/javascript'
            self._send(200, files[url.path].read_bytes(), kind)
            return
        q = parse_qs(url.query)
        r = WarehouseResults(ROOT/'output')
        try:
            if url.path == '/api/warehouse/results':
                result = {'results': r.list()}
            elif url.path == '/api/warehouse/results/meta':
                result = r.metadata(q.get('id', [''])[0])
            elif url.path == '/api/warehouse/results/frame':
                result = r.frame(q.get('id', [''])[0], int(q.get('index', [''])[0]))
            elif url.path == '/api/warehouse/results/sample':
                result = r.sample(q.get('id', [''])[0],
                                  [float(q.get(k, [''])[0]) for k in ('x', 'y', 'z')],
                                  float(q.get('time', [''])[0]), float(q.get('max_distance', [''])[0]))
            else:
                self._json({'error': 'Not found'}, 404)
                return
            self._json(result)
        except (ValueError, KeyError, OSError, BadZipFile, EOFError) as error:
            self._json({'error': str(error)}, 400)


if __name__ == '__main__':
    print('read-only warehouse review on localhost:18745', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 18745), Handler).serve_forever()
