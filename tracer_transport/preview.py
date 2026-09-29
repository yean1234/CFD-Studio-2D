"""Read-only QA host for the exact Studio UI; no solver control or WSL calls."""
import argparse
import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse, unquote


def studio_html():
    root = Path(__file__).resolve().parents[1]/'cfd_studio'
    tree = ast.parse((root/'app.py').read_text(encoding='utf-8'))
    html = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id=='INDEX_HTML' for t in n.targets)
                and isinstance(n.value,ast.Constant))
    return html.replace('__APP_VER__','QA read-only').replace('__TRACER_VIEWER__',(root/'internal/tracer_viewer.js').read_text())


def serve(project, port):
    project = Path(project).resolve()
    cfg=json.loads((project/'case_config.json').read_text())
    meta=json.loads((project/'meta.json').read_text())
    frames=json.loads((project/'tracer_frames.json').read_text())['frames']
    inv={'config':True,'config_name':'case_config.json','C':False,'bubble':0,'flow':0,'therm':0,'phase':0,
         'pressure':0,'turbulence':0,'concentration':len(frames),'sorbed':len(frames),'tmax':frames[-1]['t']}
    p={**meta,'rid':meta['run_id'],'data':inv,'mtime':project.stat().st_mtime,'analysis':'gas_transport',
       'config_available':True,'preset_available':True,'solver':'porousTracerFoam','extract':{},'n':0}
    info={'rid':p['rid'],'cur':'','projects':[p],'config':cfg,'config_source':'project','data':inv,
          'project_config_available':True,'project_config_name':'case_config.json','conditions':[],
          'tracer_frames':frames,'extract':{},'saved_configs':[]}
    allowed={'case_config.json','meta.json'}|{r[k] for r in frames for k in ['concentration','sorbed']}
    class Handler(BaseHTTPRequestHandler):
        def send(self, content, mime='application/json', code=200):
            self.send_response(code);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/':return self.send(studio_html().encode(),'text/html; charset=utf-8')
            if path in ['/qa/immersion','/qa/grain_silo']:
                fixture=Path(__file__).resolve().parents[1]/'cfd_studio/configs'/(path.split('/')[-1]+'.json')
                return self.send(fixture.read_bytes())
            if path.startswith('/files/'):
                name=unquote(path.split('/')[-1])
                if name in allowed:return self.send((project/name).read_bytes(),'application/octet-stream')
                return self.send(b'{}',code=404)
            routes={'/api/info':info,'/api/projects':{'cur':'','projects':[p]},
                    '/api/config':{'ok':True,'config':cfg,'conditions':[],'name':'case_config.json'},
                    '/api/history':{'probes':[],'vapor':[],'coil':[]},
                    '/api/uistate':{'mode':'viz','proj':p['rid'],'vproj':p['rid'],'speed':'1'},
                    '/api/status':{'running':False,'snap_times':[],'extract':{},'sys':{}},
                    '/api/extract-state':{},'/api/sys':{},'/api/settings':{'ok':True,'settings':{}}}
            self.send(json.dumps(routes.get(path,{})).encode())
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length','0')))
            if self.path=='/api/uistate':return self.send(b'{"ok":true}')
            self.send(json.dumps({'ok':False,'msg':'읽기 전용 시각화 검증 서버입니다.'}).encode(),code=403)
        def log_message(self,*args):pass
    print(f'Read-only Studio preview: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('project',type=Path)
    parser.add_argument('--port',type=int,default=8728)
    args=parser.parse_args();serve(args.project,args.port)
