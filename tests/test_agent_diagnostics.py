import io
import json
from pathlib import Path
import tempfile
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
