"""Serve the real project UI without starting or stopping an existing Studio."""
import argparse
import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlparse,parse_qs

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cfd_studio.execution_workspace import ExecutionWorkspace,get_route,post_route
from cfd_studio.warehouse_results import WarehouseResults


def serve(folder,output,port,allow_run,allow_write=False):
    workspace=ExecutionWorkspace(ROOT,[ROOT/'cfd_studio/Project'],folder=folder,output=output)
    if allow_run:
        workspace.start_queue_service()
    tree=ast.parse((ROOT/'cfd_studio/app.py').read_text())
    html=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='INDEX_HTML' for t in n.targets))
    html=html.replace('__APP_VER__','대기열 검토').replace('__TRACER_VIEWER__',(ROOT/'cfd_studio/internal/tracer_viewer.js').read_text())
    config=json.loads((ROOT/'cfd_studio/configs/immersion.json').read_text())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def _send(self,code,data,kind):
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def _json(self,data,code=200):self._send(code,json.dumps(data,ensure_ascii=False).encode(),'application/json; charset=utf-8')
        def do_GET(self):
            if get_route(self,workspace):return
            u=urlparse(self.path);q=parse_qs(u.query)
            files={'/warehouse/results':'cfd_studio/internal/warehouse_results.html','/warehouse/results.js':'cfd_studio/internal/warehouse_results.js','/studies/three.module.js':'study_platform/vendor/three.module.js'}
            if u.path=='/':self._send(200,html.encode(),'text/html; charset=utf-8')
            elif u.path in files:self._send(200,(ROOT/files[u.path]).read_bytes(),'text/javascript' if u.path.endswith('.js') else 'text/html; charset=utf-8')
            elif u.path.startswith('/api/warehouse/results'):
                r=WarehouseResults(output, lambda rid:workspace.result_path(rid, 'warehouse'))
                try:
                    if u.path.endswith('/meta'):data=r.metadata(q['id'][0])
                    elif u.path.endswith('/frame'):data=r.frame(q['id'][0],int(q['index'][0]))
                    elif u.path.endswith('/sample'):data=r.sample(q['id'][0],[float(q[k][0]) for k in ('x','y','z')],float(q['time'][0]),float(q['max_distance'][0]))
                    else:data={'results':r.list()}
                    self._json(data)
                except Exception as e:self._json({'error':str(e)},400)
            elif u.path=='/api/info':self._json({'config':config,'conditions':[],'projects':[],'rid':'','cur':'','saved_configs':[],'data':{},'frames':[],'bubs':[],'flows':[],'therms':[],'phases':[],'pressures':[],'turbulences':[]})
            elif u.path=='/api/status':self._json({'running':False,'wsl':True,'case':False,'snap_times':[],'log':'','extract':{'busy':False}})
            elif u.path=='/api/projects':self._json({'projects':[],'cur':''})
            else:self._json({})
        def do_POST(self):
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n>65536:raise ValueError('Request too large')
                body=json.loads(self.rfile.read(n) or b'{}')
                if not (allow_run or allow_write) and self.path.startswith('/api/executions'):
                    self._json({'ok':False,'msg':'읽기 전용 검토 서버'},409);return
                if self.path == '/api/uistate':
                    self._json({'ok':True});return
                if post_route(self,workspace,body):return
                self._json({'ok':False,'msg':'검토 서버에서 미지원'},409)
            except Exception as e:self._json({'ok':False,'msg':str(e)},400)
    print(f'http://127.0.0.1:{port}, CFD launch enabled: {allow_run}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=18747);p.add_argument('--allow-run',action='store_true');p.add_argument('--allow-write',action='store_true');a=p.parse_args()
    serve(a.folder,a.output,a.port,a.allow_run,a.allow_write)
