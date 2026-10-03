"""Read-only agent connection checks; never launch, stop or attach to a browser."""
import argparse
import json
from pathlib import Path
import re
import urllib.error
import urllib.request


def diagnose(studio, client_error='', opener=urllib.request.urlopen):
    studio = Path(studio)
    checks = []
    if 'sandboxCwd is not a local file URI' in client_error:
        checks.append({'code': 'APP-A001', 'scope': 'external_client',
                       'detail': 'The automation host rejected its workspace URI before connecting to Studio',
                       'action': 'Use the Windows local CFD-Studio workspace and reconnect the existing tab; do not restart a solver'})
    try:
        config_path = studio/'studio_config.json'
        config = json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
        port = config.get('port', 8712)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError('port must be an integer in 1..65535')
    except (OSError, ValueError) as exc:
        checks.append({'code': 'APP-A002', 'scope': 'studio_config', 'detail': str(exc)})
        return {'checks': checks, 'tab_connected': 'not_checked'}
    url = f'http://127.0.0.1:{port}'
    try:
        with opener(url+'/agent_controls.js', timeout=3) as response:
            script = response.read(1024 * 1024).decode('utf-8')
        match = re.search(r"const VERSION=['\"]([0-9.]+)['\"]", script)
        if not match or 'root.CFDAgent=' not in script:
            checks.append({'code': 'APP-A002', 'scope': 'studio_interface', 'detail': 'The endpoint did not serve a recognizable CFDAgent interface'})
        else:
            with opener(url+'/agent_collaboration.js', timeout=3) as response:
                dependency = response.read(1024 * 1024).decode('utf-8')
            if 'CFDAgentCollaboration' not in dependency:
                checks.append({'code': 'APP-A002', 'scope': 'studio_interface', 'detail': 'Agent collaboration dependency is missing'})
            else:
                checks.append({'code': 'OK', 'scope': 'studio_interface', 'version': match.group(1)})
    except (OSError, UnicodeError) as exc:
        checks.append({'code': 'APP-N001', 'scope': 'studio_http', 'detail': str(exc),
                       'action': 'Check the configured port and whether Studio is running; do not terminate the browser or solver'})
    return {'url': url, 'checks': checks, 'tab_connected': 'not_checked',
            'note': 'HTTP availability does not prove attachment to the user tab or permission to calculate'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studio', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--client-error', default='')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = diagnose(args.studio, args.client_error)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        # Preserve prior diagnostic records rather than silently overwrite them
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(payload+'\n')
    print(payload)
    return int(any(row['code'] != 'OK' for row in result['checks']))


if __name__ == '__main__':
    raise SystemExit(main())
