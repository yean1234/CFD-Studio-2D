"""운영 Study와 분리한 HTTP 복구 UI 시험 서버. 실제 CFD 프로세스를 만들지 않는다."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'cfd_studio'))
from study_platform import http
from study_platform.contracts import candidates
from study_platform.service import Service


def serve(folder, port):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    # 복구 UX만 시험하는 가짜 어댑터. 실제 수치 검증 보고에 이 결과를 포함하지 않는다.
    store = Service(folder, adapter=lambda *args: {'pass': True, 'scope': 'ui_fixture_only'})
    design = {'variable': 'porosity', 'method': 'manual', 'values': [.4], 'seed': 1}
    keys = []
    for name in ('UX 복구 확인', 'UX 예약 취소'):
        study = store.create(name)
        rev = store.commit(study, design, candidates(design)['preview_hash'], None)
        attempt = store.enqueue([rev['cases'][0]], name)['attempts'][0]
        keys.append({'study': study, 'attempt': attempt})
    with store.db() as db:
        db.execute("UPDATE attempts SET state='running',owner='fixture:disconnected' WHERE id=?", (keys[0]['attempt'],))
    (folder/'fixture.json').write_text(json.dumps(keys), encoding='utf-8')
    http._service = store
    import app
    print(json.dumps({'port': port, 'fixtures': keys}), flush=True)
    app.StudioHTTPServer(('127.0.0.1', port), app.H).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('new_folder', type=Path)
    parser.add_argument('--port', type=int, default=8740)
    args = parser.parse_args()
    serve(args.new_folder, args.port)
