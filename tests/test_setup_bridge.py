"""Preserve installer paths and terminal input across the Windows/WSL boundary."""
import base64
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('setup_bridge', Path(__file__).resolve().parents[1]/'cfd_studio/internal/setup_bridge.py')
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class SetupBridgeTests(unittest.TestCase):
    def test_script_quotes_unicode_paths_and_rejects_root_targets(self):
        script = bridge.setup_script(Path('C:/Test Folder/한글'), '~/test case')
        self.assertIn("wslpath -u 'C:/Test Folder/한글'", script.replace('\\', '/'))
        self.assertIn("'~/test case'", script)
        for path in ('/', '~/', 'relative', '/tmp/a\nb'):
            with self.assertRaises(ValueError):
                bridge.setup_script(Path('C:/Test'), path)

    def test_script_is_staged_via_stdin_and_execution_keeps_terminal(self):
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder)/'한글 폴더'/'cfd_studio'
            here.mkdir(parents=True)
            (here/'studio_config.json').write_text('{"wsl_case":"~/test case"}')
            calls = []

            def run(argv, **kwargs):
                calls.append((argv, kwargs))
                if argv[-1] == '-s':
                    return subprocess.CompletedProcess(argv, 0, b'/tmp/cfd-studio-setup.ABC123\n')
                return subprocess.CompletedProcess(argv, 0)

            with patch.object(bridge, 'HERE', here), patch.object(bridge.subprocess, 'run', side_effect=run):
                self.assertEqual(bridge.main(), 0)
            stage = calls[1][1]['input'].decode('ascii')
            encoded = stage.split('printf %s ', 1)[1].split(' | base64', 1)[0]
            self.assertIn('한글 폴더', base64.b64decode(encoded).decode('utf-8'))
            self.assertNotIn('input', calls[2][1])
            self.assertEqual(calls[2][0][-3:], ['--exec', 'bash', '/tmp/cfd-studio-setup.ABC123'])
            self.assertEqual(calls[3][0][-4:], ['rm', '-f', '--', '/tmp/cfd-studio-setup.ABC123'])
