"""Verify duplicate and blocked startup without touching user processes or data."""
import ast
import io
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cfd_studio.studio_launcher import configured_port, existing_studio, launch, startup_action

ROOT = Path(__file__).resolve().parents[1]


class StudioLauncherTests(unittest.TestCase):
    def test_port_validation_and_environment_override(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder, 'studio_config.json')
            config.write_text('{"port": 8899}')
            self.assertEqual(configured_port(folder, {}), 8899)
            self.assertEqual(configured_port(folder, {'CFD_STUDIO_PORT': '8900'}), 8900)
            for bad in (True, 0, 65536, 8712.5, '8712.5', []):
                config.write_text(json.dumps({'port': bad}))
                with self.subTest(port=bad), self.assertRaises(ValueError):
                    configured_port(folder, {})

    def test_busy_and_unavailable_ports_never_start(self):
        factory = Mock(side_effect=OSError('unavailable'))
        self.assertEqual(startup_action(8712, factory, lambda _: True), 'reuse')
        self.assertEqual(startup_action(8712, factory, lambda _: False), 'blocked')

    def test_real_free_and_busy_ports_without_connection_timeout(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            self.assertEqual(startup_action(port, probe=lambda _: False), 'blocked')
        probe = Mock(side_effect=AssertionError('Free ports need no HTTP request'))
        self.assertEqual(startup_action(port, probe=probe), 'start')
        probe.assert_not_called()

    def test_reuse_opens_existing_server_without_spawning(self):
        with tempfile.TemporaryDirectory() as folder:
            runner, browser = Mock(), Mock()
            self.assertEqual(launch(folder, action=lambda _: 'reuse', browser=browser, runner=runner), 0)
            browser.assert_called_once()
            runner.assert_not_called()

    def test_conflict_preserves_port_and_does_not_open_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder, 'studio_config.json')
            config.write_text('{"port": 8899}')
            runner, browser = Mock(), Mock()
            self.assertEqual(launch(folder, action=lambda _: 'blocked', browser=browser, runner=runner), 2)
            self.assertEqual(config.read_text(), '{"port": 8899}')
            browser.assert_not_called()
            runner.assert_not_called()

    def test_free_port_passes_exact_port_and_preserves_exit_status(self):
        with tempfile.TemporaryDirectory(prefix='cfd space ') as folder:
            runner = Mock(return_value=7)
            with patch.dict(os.environ, {'CFD_STUDIO_PORT': '8921'}):
                self.assertEqual(launch(folder, action=lambda _: 'start', runner=runner), 7)
            self.assertEqual(runner.call_args.kwargs['env']['CFD_STUDIO_PORT'], '8921')
            self.assertEqual(runner.call_args.args[0][1], str(Path(folder).resolve() / 'app.py'))

    def test_identity_uses_read_only_static_script(self):
        fetch = Mock(return_value=io.BytesIO(b"const VERSION='1.3';root.CFDAgent={};"))
        self.assertTrue(existing_studio(8899, fetch))
        self.assertEqual(fetch.call_args.args[0], 'http://127.0.0.1:8899/agent_controls.js')
        self.assertFalse(existing_studio(8899, Mock(return_value=io.BytesIO(b'<html>other</html>'))))

    def test_direct_app_conflict_does_not_run_migrations_or_claim_pid(self):
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        probe = Mock(return_value=True)
        browser = Mock()
        # Missing migration and PID globals deliberately fail if reached
        env = {'sys': Mock(), 'StudioHTTPServer': Mock(side_effect=OSError('occupied')),
               'PORT': 8712, 'H': object(), 'webbrowser': browser}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<startup>', 'exec'), env)
        with patch.dict('sys.modules', {'studio_launcher': Mock(existing_studio=probe)}):
            env['main']()
        browser.open.assert_called_once_with('http://127.0.0.1:8712')

    def test_pid_record_does_not_terminate_previous_pid(self):
        tree = ast.parse((ROOT/'cfd_studio/app.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_claim_studio_pid')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'studio.pid')
            path.write_text('{"pid": 99999, "started": 1}')
            env = {'os': os, 'json': json, 'PROCESS_STARTED': 2, 'STUDIO_PIDF': str(path)}
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<pid>', 'exec'), env)
            env['_claim_studio_pid']()
            self.assertEqual(json.loads(path.read_text())['pid'], os.getpid())


if __name__ == '__main__':
    unittest.main()
