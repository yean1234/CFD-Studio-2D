"""Read-only agent connection checks; never launch, stop or attach to a browser."""
import argparse
import json
from pathlib import Path
import re
import sys
import urllib.request

if __package__:
    from .studio_launcher import configured_port
else:
    # The bundled isolated Python omits the script directory from sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from studio_launcher import configured_port


def diagnostic_result(checks, url=None):
    """Keep server reachability distinct from attachment to the user's tab."""
    scopes = {row['scope']: row['code'] for row in checks}
    stages = {
        'automation_host': 'failed' if 'external_client' in scopes else 'not_checked',
        'studio_http': 'failed' if 'studio_http' in scopes else 'responded' if 'studio_interface' in scopes else 'not_checked',
        'agent_scripts': 'ready' if scopes.get('studio_interface') == 'OK' else 'failed' if 'studio_interface' in scopes else 'not_checked',
        'current_tab': 'not_checked',
    }
    return {'url': url, 'checks': checks, 'stages': stages, 'tab_connected': 'not_checked',
            'note': 'HTTP availability does not prove attachment to the user tab or permission to calculate'}


def diagnose(studio, client_error='', opener=urllib.request.urlopen, *, environ=None):
    studio = Path(studio)
    checks = []
    if 'sandboxCwd is not a local file URI' in client_error:
        checks.append({'code': 'APP-A001', 'scope': 'external_client',
                       'detail': 'The automation host rejected its workspace URI before connecting to Studio',
                       'action': 'Check the automation host workspace mapping; a Windows local workspace is an unverified recovery option, not a guaranteed fix; preserve Studio and solvers'})
    try:
        port = configured_port(studio, environ)
    except (OSError, ValueError) as exc:
        checks.append({'code': 'APP-A002', 'scope': 'studio_config', 'detail': str(exc)})
        return diagnostic_result(checks)
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
    return diagnostic_result(checks, url)


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
