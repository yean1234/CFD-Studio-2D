"""Isolated browser fixture; no app import, project access, or CFD execution."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cfd_studio.agent_activity import route

HTML = '''<!doctype html><html><head><meta charset="utf-8"><title>Agent progress test</title>
<style>body{background:#111;color:#eee;font:14px system-ui;padding:120px 40px}button{padding:10px;background:#333;color:white;border:1px solid #666;border-radius:8px}dialog{background:#222;color:white;padding:80px}</style></head><body>
<h1>Agent progress test</h1><p>Isolated interface fixture · No project data</p>
<button id="mCFD" onclick="this.textContent='Clicked'">CFD</button>
<button onclick="document.querySelector('dialog').showModal()">Open modal</button>
<dialog><h2>Draft preview</h2><button onclick="this.closest('dialog').close()">Close modal</button></dialog>
<div id="languageOptions"><button data-language="ko">한국어</button><button data-language="en">English</button><button data-language="ja">日本語</button></div>
<script src="/i18n.js"></script><script src="/agent_collaboration.js"></script>
<script src="/agent_activity.js"></script><script src="/agent_controls.js"></script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, body, code=200):
        self._send(code, json.dumps(body).encode(), 'application/json')

    def do_GET(self):
        if route(self):
            return
        if self.path == '/':
            self._send(200, HTML.encode(), 'text/html; charset=utf-8')
        elif self.path in ('/i18n.js', '/agent_collaboration.js', '/agent_activity.js', '/agent_controls.js'):
            self._send(200, (ROOT/'cfd_studio/internal'/self.path[1:]).read_bytes(), 'text/javascript; charset=utf-8')
        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        if not route(self, post=True):
            self._json({'error': 'not found'}, 404)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'http://127.0.0.1:{server.server_port}', flush=True)
    server.serve_forever()
