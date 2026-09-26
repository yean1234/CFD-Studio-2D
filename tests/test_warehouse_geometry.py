import copy
import json
from pathlib import Path
import tempfile
import unittest

from tracer_transport.warehouse_geometry import build, mesh_dictionary, validate


class WarehouseGeometryTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((Path(__file__).resolve().parents[1]/'tracer_transport/warehouse_geometry_20260925.json').read_text())

    def test_gabled_volume_and_scope(self):
        report = validate(self.spec)
        self.assertAlmostEqual(report['volume_m3'], 17452.5)
        self.assertEqual(report['cells'], 22308)
        self.assertFalse(report['transport_ready'])
        self.assertIn('annexInterface', mesh_dictionary(self.spec))

    def test_bad_dimensions_and_budget(self):
        for value in (0, -1, True, float('nan'), float('inf')):
            spec = copy.deepcopy(self.spec)
            spec['geometry']['length_m'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(spec)
        self.spec['mesh']['maximum_cells'] = 10
        with self.assertRaises(ValueError):
            validate(self.spec)

    def test_generic_dimensions(self):
        self.spec['geometry'].update(length_m=12, width_m=8, eaves_m=4, roof_rise_m=2)
        self.assertEqual(validate(self.spec)['volume_m3'], 480)
        self.spec['geometry']['typo'] = 1
        with self.assertRaises(ValueError):
            validate(self.spec)

    def test_preserve_existing_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)/'new'
            self.assertEqual(build(self.spec, destination)['status'], 'generated_not_checked')
            before = (destination/'geometry.json').read_bytes()
            with self.assertRaises(FileExistsError):
                build(self.spec, destination)
            self.assertEqual(before, (destination/'geometry.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
