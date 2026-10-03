"""Send progress only; this client cannot edit Config, save Cases or run CFD."""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

if __package__:
    from .studio_launcher import configured_port
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from studio_launcher import configured_port


def request(port, body=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body else None
    req = Request(f'http://127.0.0.1:{port}/api/agent/activity', data=data,
                  headers={'Content-Type': 'application/json', 'X-CFD-Activity': '1'})
    try:
        with urlopen(req, timeout=4) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            result = json.load(exc)
            if isinstance(result, dict) and isinstance(result.get('error'), str):
                return result
        except ValueError:
            pass
        return {'error': 'ACTIVITY_UNAVAILABLE', 'http_status': exc.code}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'update', 'status', 'finish'))
    parser.add_argument('--studio', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--session-file', type=Path)
    parser.add_argument('--name', default='AI agent')
    parser.add_argument('--mode', choices=('development', 'operation'), default='development')
    parser.add_argument('--stage')
    parser.add_argument('--detail')
    parser.add_argument('--wait-visible', action='store_true')
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args(argv)
    if args.action != 'status' and not args.session_file:
        parser.error('--session-file is required; use a new file in an ignored output folder')
    if args.action != 'status' and (not args.stage or not args.detail):
        parser.error('--stage and --detail are required')
    created = False
    try:
        port = configured_port(args.studio)
        body = None
        if args.action != 'status':
            body = {'action': args.action, 'stage': args.stage, 'detail': args.detail}
            if args.action == 'start':
                # Reserve before claiming; never overwrite another controller's token
                with args.session_file.open('x', encoding='utf-8'):
                    pass
                created = True
                body.update(name=args.name, mode=args.mode)
            else:
                session = json.loads(args.session_file.read_text(encoding='utf-8'))
                if session['port'] != port:
                    raise ValueError('Session port changed; reconnect explicitly')
                body['token'] = session['token']
        result = request(port, body)
        if args.action == 'start' and 'token' in result:
            token = result.pop('token')
            args.session_file.write_text(json.dumps({'port': port, 'token': token}), encoding='utf-8')
            created = False
        if args.wait_visible and 'error' not in result:
            revision = result['revision']
            server = result['server']
            task_id = (result.get('task') or {}).get('id')
            deadline = time.monotonic() + 5
            while not result.get('displayed') and time.monotonic() < deadline and not result.get('paused'):
                time.sleep(.25)
                result = request(port)
                if 'error' in result:
                    break
                if result['server'] != server or result['revision'] != revision or (result.get('task') or {}).get('id') != task_id:
                    if not result.get('paused'):
                        result['error'] = 'ACTIVITY_STALE'
                    break
        if not args.history:
            result.pop('history', None)
            if isinstance(result.get('state'), dict):
                result['state'].pop('history', None)
        print(json.dumps(result, ensure_ascii=False))
        if result.get('paused') or result.get('error') == 'PAUSED':
            return 3
        if 'error' in result:
            return 2
        if args.wait_visible and not result.get('displayed'):
            return 4
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': 'ACTIVITY_UNAVAILABLE', 'detail': str(exc)}, ensure_ascii=False))
        return 2
    finally:
        if created:
            args.session_file.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
