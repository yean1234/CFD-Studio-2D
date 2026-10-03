"""Launch or reuse Studio without terminating another application or solver."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
import webbrowser


def configured_port(studio, environ=None):
    environ = os.environ if environ is None else environ
    path = Path(studio) / 'studio_config.json'
    config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError('studio_config.json must contain an object')
    port = environ.get('CFD_STUDIO_PORT') or config.get('port', 8712)
    if isinstance(port, str) and port.isascii() and port.isdecimal():
        port = int(port)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('port must be an integer in 1..65535')
    return port


def existing_studio(port, opener=urllib.request.urlopen):
    # Static script inspection avoids API endpoints that migrate legacy results
    try:
        with opener(f'http://127.0.0.1:{port}/agent_controls.js', timeout=2) as response:
            script = response.read(1024 * 1024).decode('utf-8')
        return 'root.CFDAgent=' in script and 'const VERSION=' in script
    except (OSError, UnicodeError):
        return False


def startup_action(port, connector=socket.create_connection, probe=existing_studio):
    try:
        with connector(('127.0.0.1', port), timeout=1):
            pass
    except ConnectionRefusedError:
        return 'start'
    except OSError:
        return 'blocked'
    return 'reuse' if probe(port) else 'blocked'


def launch(studio, *, action=startup_action, browser=webbrowser.open, runner=subprocess.call):
    studio = Path(studio).resolve()
    try:
        port = configured_port(studio)
    except (OSError, ValueError) as exc:
        print(f'[APP-A002] {exc}')
        return 2
    state = action(port)
    if state == 'reuse':
        print(f'[CFD Studio] Existing server preserved: http://127.0.0.1:{port}')
        browser(f'http://127.0.0.1:{port}')
        return 0
    if state != 'start':
        print(f'[APP-A002] Port {port} is occupied or unavailable; no process was stopped')
        return 2
    return runner([sys.executable, str(studio / 'app.py')], cwd=str(studio),
                  env={**os.environ, 'CFD_STUDIO_PORT': str(port)})


if __name__ == '__main__':
    raise SystemExit(launch(Path(__file__).resolve().parents[1]))
