"""Launch WSL setup with base64-encoded UTF-8 for reliable Windows paths."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]

def setup_script(parent, case):
    if not (case.startswith('~/') or case.startswith('/')) or case in ('/', '~/'):
        raise ValueError('wsl_case must be a dedicated absolute Linux path or ~/subdirectory')
    if any(c in case for c in '\n\r\x00'):
        raise ValueError('Invalid case path')
    return ('set -e\n'
            'PARENT=$(wslpath -u ' + shlex.quote(str(parent)) + ')\n'
            'bash "$PARENT/cfd_studio/internal/setup.sh" "$PARENT" ' + shlex.quote(case) + '\n')

def main():
    cfg_path = HERE / 'studio_config.json'
    if not cfg_path.exists():
        example = json.loads((HERE / 'studio_config.example.json').read_text(encoding='utf-8'))
        cfg_path.write_text(json.dumps(example, indent=2), encoding='utf-8')
    cfg = json.loads(cfg_path.read_text(encoding='utf-8-sig'))
    wsl = os.environ.get('CFD_STUDIO_WSL_EXE') or 'wsl.exe'
    prefix = [wsl]
    if cfg.get('wsl_distro'):
        prefix += ['-d', str(cfg['wsl_distro'])]
    probe = subprocess.run(prefix + ['--', 'true'], check=False)
    if probe.returncode:
        raise RuntimeError('Install and initialize WSL2 Ubuntu first: wsl --install -d Ubuntu')
    script = setup_script(HERE.parent, str(cfg.get('wsl_case', '~/cfd_studio_case')))
    # Stage through stdin; command-line quoting differs between WSL releases.
    import base64
    encoded = base64.b64encode(script.encode('utf-8')).decode('ascii')
    stage = ('umask 077\nTASK_SCRIPT=$(mktemp /tmp/cfd-studio-setup.XXXXXX) || exit 1\n'
             + 'printf %s ' + shlex.quote(encoded) + ' | base64 -d > "$TASK_SCRIPT" || exit 1\n'
             + 'printf "%s\\n" "$TASK_SCRIPT"\n')
    result = subprocess.run(prefix + ['--exec', 'bash', '-s'], input=stage.encode('ascii'),
                            capture_output=True, check=True)
    target = result.stdout.decode('utf-8').strip()
    if not target.startswith('/tmp/cfd-studio-setup.') or any(c.isspace() for c in target):
        raise RuntimeError('Invalid installer staging path')
    try:
        # Inherit terminal input so sudo can still prompt when packages are absent.
        return subprocess.run(prefix + ['--exec', 'bash', target], check=False).returncode
    finally:
        subprocess.run(prefix + ['--exec', 'rm', '-f', '--', target], check=False)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('[setup] ' + str(exc), file=sys.stderr)
        sys.exit(1)
