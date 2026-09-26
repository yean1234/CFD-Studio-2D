import json
from pathlib import Path
import tempfile
import unittest
from cfd_studio.warehouse_workspace import Workspace, ROOT


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT/'tracer_transport/warehouse_geometry_20260925.json').read_text())

    def test_saved_settings_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, {})
            first = workspace.save({'name': 'same', 'geometry_spec': self.spec})
            self.spec['geometry']['length_m'] = 90
            second = workspace.save({'name': 'same', 'geometry_spec': self.spec})
            self.assertNotEqual(first['id'], second['id'])
            items = workspace.read()['settings']
            self.assertEqual(sorted(x['geometry_spec']['geometry']['length_m'] for x in items), [78, 90])
            self.assertFalse(workspace.read()['transport_ready'])

    def test_invalid_settings_and_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, {})
            for key in ('../case', '', None, 'a'*33):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    workspace.start(key)
            self.spec['mesh']['nx'] = -1
            with self.assertRaises(ValueError):
                workspace.save({'name': 'invalid', 'geometry_spec': self.spec})
            self.assertEqual(workspace.read()['settings'], [])

    def test_interrupted_job_not_reported_as_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'checks'/'a'
            folder.mkdir(parents=True)
            (folder/'job.json').write_text(json.dumps({'id': 'a', 'status': 'running'}))
            self.assertEqual(Workspace(tmp, {}).read()['jobs'][0]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
