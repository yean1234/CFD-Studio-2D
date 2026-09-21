"""Offline checks; never invoke WSL installation or start a solver."""
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('setup_bridge', ROOT/'cfd_studio/setup_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class DistributionTests(unittest.TestCase):
    def test_runtime_and_launcher_dependencies(self):
        for name in ['python.exe', 'python312.dll', 'python312.zip', '_socket.pyd', '_ssl.pyd', '_ctypes.pyd', 'LICENSE.txt']:
            self.assertTrue((ROOT/'cfd_studio/Setup/Python312'/name).is_file())
        launcher = (ROOT/'cfd_studio/설치.bat').read_text()
        self.assertIn('%~dp0setup_bridge.py', launcher)
        self.assertNotIn('_runtime\\setup_bridge.py', launcher)

    def test_python_syntax(self):
        for base in ['cfd_studio','tmc49_full_tank','silo_reproduction']:
            for p in (ROOT/base).rglob('*.py'):
                ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))

    def test_no_personal_state(self):
        for name in ['studio_config.json','Project','Trash','_runtime','frames']:
            self.assertFalse((ROOT/'cfd_studio'/name).exists(), name)

    def test_case_validation(self):
        for cfg in ['immersion','grain_silo']:
            with self.subTest(cfg=cfg), tempfile.TemporaryDirectory() as tmp:
                dst=Path(tmp)/'case'
                shutil.copytree(ROOT/'tmc49_full_tank',dst)
                shutil.copy2(ROOT/f'cfd_studio/configs/{cfg}.json',dst/'config.json')
                r=subprocess.run([sys.executable,str(dst/'tools/build_case.py'),'--check'],
                                 capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_path_validation(self):
        for case in ['/', '~/', 'relative', '~/bad\npath']:
            with self.assertRaises(ValueError):
                bridge.setup_script('C:\\CFD Studio',case)
        script=bridge.setup_script("C:\\Users\\한글\\Studio's folder", '~/new_case')
        self.assertIn('wslpath -u',script)
        self.assertIn('"$PARENT/cfd_studio/setup.sh"',script)
        if shutil.which('bash'):
            subprocess.run(['bash','-n'],input=script,text=True,check=True)

    @unittest.skipUnless(sys.platform != 'win32' and shutil.which('bash'), 'Linux bash required')
    def test_existing_case_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel=Path(tmp)/'config.json'
            sentinel.write_text('{"preserve":true}')
            r=subprocess.run(['bash',str(ROOT/'cfd_studio/setup.sh'),str(ROOT),tmp],capture_output=True)
            self.assertNotEqual(r.returncode,0)
            self.assertEqual(sentinel.read_text(),'{"preserve":true}')

if __name__ == '__main__':
    unittest.main()
