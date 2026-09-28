import tempfile
import unittest
from pathlib import Path
from cfd_studio.storage_layout import compatibility_folder


class StorageLayoutTests(unittest.TestCase):
    def test_clean_install_keeps_compatibility_directories_in_runtime(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertEqual(Path(compatibility_folder(base, 'Project', 'legacy_results')),
                             Path(base)/'_runtime/legacy_results')
            self.assertFalse((Path(base)/'Project').exists())

    def test_existing_results_are_not_hidden_or_moved(self):
        with tempfile.TemporaryDirectory() as base:
            old = Path(base)/'Project'
            old.mkdir()
            (old/'result.bin').write_bytes(b'original')
            self.assertEqual(Path(compatibility_folder(base, 'Project', 'legacy_results')), old)
            self.assertEqual((old/'result.bin').read_bytes(), b'original')

    def test_empty_legacy_directory_does_not_reappear_as_active_storage(self):
        with tempfile.TemporaryDirectory() as base:
            (Path(base)/'frames').mkdir()
            self.assertEqual(Path(compatibility_folder(base, 'frames', 'frames')),
                             Path(base)/'_runtime/frames')
