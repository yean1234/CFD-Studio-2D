import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock
from cfd_studio.agent_diagnostics import diagnose


class AgentDiagnosticsTests(unittest.TestCase):
    def test_host_uri_failure_and_http_failure_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            result = diagnose(directory, 'sandboxCwd is not a local file URI', Mock(side_effect=ConnectionRefusedError('offline')))
        self.assertEqual([c['code'] for c in result['checks']], ['APP-A001', 'APP-N001'])
        self.assertEqual(result['tab_connected'], 'not_checked')

    def test_successful_http_is_not_a_tab_attachment(self):
        fetch = Mock(side_effect=[io.BytesIO(b"const VERSION='1.3';root.CFDAgent={};"),
                                 io.BytesIO(b'root.CFDAgentCollaboration={};')])
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'studio_config.json').write_text(json.dumps({'port': 8899}))
            result = diagnose(directory, opener=fetch)
        self.assertEqual(result['checks'][0]['code'], 'OK')
        self.assertEqual(result['tab_connected'], 'not_checked')
        self.assertEqual(fetch.call_args_list[0].args[0], 'http://127.0.0.1:8899/agent_controls.js')

    def test_wrong_service_is_not_reported_as_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = diagnose(directory, opener=Mock(return_value=io.BytesIO(b'<html>other server</html>')))
        self.assertEqual(result['checks'][0]['code'], 'APP-A002')

    def test_invalid_port_does_not_probe_network(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'studio_config.json').write_text('{"port":true}')
            fetch = Mock(); result = diagnose(directory, opener=fetch)
        self.assertEqual(result['checks'][0]['code'], 'APP-A002'); fetch.assert_not_called()

    def test_healthy_server_does_not_hide_automation_host_failure(self):
        fetch = Mock(side_effect=[io.BytesIO(b"const VERSION='1.3';root.CFDAgent={};"),
                                 io.BytesIO(b'root.CFDAgentCollaboration={};')])
        with tempfile.TemporaryDirectory() as directory:
            result = diagnose(directory, 'sandboxCwd is not a local file URI', fetch)
        self.assertEqual(result['stages'], {'automation_host': 'failed', 'studio_http': 'responded',
                                          'agent_scripts': 'ready', 'current_tab': 'not_checked'})
        self.assertEqual([row['code'] for row in result['checks']], ['APP-A001', 'OK'])

    def test_launcher_port_override_is_used_without_changing_config(self):
        fetch = Mock(side_effect=ConnectionRefusedError('offline'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'studio_config.json')
            path.write_text('{"port":8712}')
            result = diagnose(directory, opener=fetch, environ={'CFD_STUDIO_PORT':'8921'})
            self.assertEqual(path.read_text(), '{"port":8712}')
        self.assertEqual(result['url'], 'http://127.0.0.1:8921')
        self.assertEqual(result['stages']['studio_http'], 'failed')

    def test_malformed_config_is_reported_without_network_request(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'studio_config.json').write_text('[]')
            fetch = Mock()
            result = diagnose(directory, opener=fetch)
        fetch.assert_not_called()
        self.assertEqual(result['checks'][0]['code'], 'APP-A002')
        self.assertEqual(result['stages']['current_tab'], 'not_checked')

    def test_documented_cli_starts_under_isolated_python(self):
        script = Path(__file__).resolve().parents[1]/'cfd_studio/internal/agent_diagnostics.py'
        result = subprocess.run([sys.executable, '-I', str(script), '--help'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--client-error', result.stdout)
