"""Run Allrun against fake mesh commands; no CFD executable is called."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'Shell control-flow test uses POSIX sh')
class MeshGateTests(unittest.TestCase):
    def fixture(self, failed, mesh_ok=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'tools').mkdir(); (root/'0.orig').mkdir()
            (root/'system').mkdir()
            (root/'system/createPatchDict').write_text('test fixture')
            (root/'tools/build_case.py').write_text('')
            (root/'config.json').write_text('{"_해석유형":"grain_silo"}')
            (root/'Allrun').write_bytes((ROOT/'tmc49_full_tank/Allrun').read_bytes())
            (root/'foam/bin/tools').mkdir(parents=True)
            (root/'bin').mkdir()
            command = root/'bin/foamDictionary'; command.write_text('#!/bin/sh\nexit 0\n'); command.chmod(0o755)
            (root/'foam/bin/tools/RunFunctions').write_text('''runApplication() {
 [ "$1" != -overwrite ] || shift
 echo "$1" >> "$TEST_TRACE"
 if [ "$1" = checkMesh ]; then
   if [ "$TEST_MESH_OK" = yes ]; then echo 'Mesh OK.' > log.checkMesh; else echo 'Failed 1 mesh checks' > log.checkMesh; fi
 fi
 [ "$1" != "$TEST_FAILED" ]
}
getApplication() { echo simpleFoam; }
runParallel() { echo SOLVER >> "$TEST_TRACE"; }
''')
            env = {**os.environ, 'WM_PROJECT_DIR': str(root/'foam'), 'PATH': str(root/'bin')+':'+os.environ['PATH'],
                   'NP': '1', 'TEST_TRACE': str(root/'trace'), 'TEST_FAILED': failed,
                   'TEST_MESH_OK': 'yes' if mesh_ok else 'no', 'CFD_STUDIO_COMPUTE_MODE': 'gpu_only'}
            result = subprocess.run(['sh', './Allrun'], cwd=root, env=env, capture_output=True, text=True)
            return result, (root/'trace').read_text().splitlines()

    def test_failed_mesh_commands_never_reach_solver(self):
        for command in ['blockMesh', 'topoSet', 'createPatch', 'checkMesh', 'decomposePar']:
            with self.subTest(command=command):
                result, trace = self.fixture(command, mesh_ok=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('SOLVER', trace)

    def test_zero_exit_without_mesh_ok_still_blocks_solver(self):
        result, trace = self.fixture('none')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CFG-G006', result.stdout)
        self.assertNotIn('SOLVER', trace)

    def test_successful_mesh_checks_reach_solver_dispatch(self):
        result, trace = self.fixture('none', mesh_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SOLVER', trace)
