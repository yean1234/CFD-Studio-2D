"""Offline result-integrity checks; no CFD solver or operating project is touched."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tracer_transport.export_studio import export_case
from tracer_transport.run import generate


ROOT = Path(__file__).resolve().parents[1]


class ResultIntegrityTests(unittest.TestCase):
    def audit(self, root):
        return subprocess.run([sys.executable, str(ROOT/'tests/audit_saved_results.py'), str(root)],
                              capture_output=True, text=True, check=False)

    def test_export_hashes_detect_finite_frame_change_and_keep_legacy_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case, project = root/'case', root/'projects'/'example'
            parameters = json.loads((ROOT/'tracer_transport/supply_test.json').read_text())
            cfg, _, initial = generate(case, 20, .05, 'porous', parameters)
            values = np.stack([initial, initial + 1])
            np.savez(case/'concentration.npz', times=[0, 1], concentration=values,
                     sorbed_bulk=values / 10, shape_xyz=cfg['shape_xyz'], lengths_m=cfg['lengths_m'])
            (case/'checks.json').write_text(json.dumps({'pass': True}))
            export_case(case, project)

            manifest_path = project/'tracer_frames.json'
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest['integrity_schema'], 1)
            self.assertEqual(set(manifest['frames'][0]['frame_sha256']), {'concentration', 'sorbed'})
            clean = self.audit(root/'projects')
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertEqual(json.loads(clean.stdout)['hash_verified_files'], 4)

            frame = project/'concentration_1.bin'
            original = frame.read_bytes()
            changed = bytearray(original)
            changed[-1] ^= 1  # still a finite float32; structural checks alone would pass
            frame.write_bytes(changed)
            corrupt = self.audit(root/'projects')
            self.assertNotEqual(corrupt.returncode, 0)
            self.assertIn('frame hash mismatch', corrupt.stdout)
            frame.write_bytes(original)

            del manifest['integrity_schema']
            for row in manifest['frames']:
                del row['frame_sha256']
            manifest_path.write_text(json.dumps(manifest))
            legacy = self.audit(root/'projects')
            self.assertEqual(legacy.returncode, 0, legacy.stdout + legacy.stderr)
            self.assertEqual(json.loads(legacy.stdout)['hash_verified_files'], 0)

    def test_existing_result_timeline_cannot_be_shortened(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case, project = root/'case', root/'projects'/'example'
            parameters = json.loads((ROOT/'tracer_transport/supply_test.json').read_text())
            cfg, _, initial = generate(case, 20, .05, 'porous', parameters)
            values = np.stack([initial, initial + 1, initial + 2])
            np.savez(case/'concentration.npz', times=[0, .5, 1], concentration=values,
                     sorbed_bulk=values / 10, shape_xyz=cfg['shape_xyz'], lengths_m=cfg['lengths_m'])
            (case/'checks.json').write_text(json.dumps({'pass': True}))
            export_case(case, project)
            original_manifest = (project/'tracer_frames.json').read_bytes()
            original_last = (project/'concentration_1.bin').read_bytes()

            np.savez(case/'concentration.npz', times=[0, .5], concentration=values[:2],
                     sorbed_bulk=values[:2] / 10, shape_xyz=cfg['shape_xyz'], lengths_m=cfg['lengths_m'])
            with self.assertRaisesRegex(ValueError, 'truncated'):
                export_case(case, project)
            self.assertEqual((project/'tracer_frames.json').read_bytes(), original_manifest)
            self.assertEqual((project/'concentration_1.bin').read_bytes(), original_last)


if __name__ == '__main__':
    unittest.main()
