import copy
import json
from pathlib import Path
import tempfile
import unittest

from tracer_transport.warehouse_geometry import build, checked_mesh_quality, mesh_dictionary, validate


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

    def test_checked_mesh_report_requires_matching_topology_and_volume(self):
        log = '''Mesh stats
    cells:            22308
    Number of regions: 1 (OK).
    floor               2028     2133     ok
    roof                2028     2133     ok
    sideWalls           1716     1896     ok
    endWall             286      324      ok
    annexInterface      286      324      ok
    Total volume = 17452.5.  Cell volumes OK.
    Mesh non-orthogonality Max: 14.9638 average: 7.21419
    Max skewness = 0.39503 OK.
Mesh OK.
'''
        quality = checked_mesh_quality(log, 22308, 17452.5)
        self.assertEqual(quality['checked_cells'], 22308)
        self.assertEqual(quality['boundary_faces']['annexInterface'], 286)
        self.assertAlmostEqual(quality['max_skewness'], .39503)
        for changed in (log.replace('22308', '22307'), log.replace('17452.5', '17000'),
                        log.replace('Mesh OK.', 'Mesh failed.')):
            with self.subTest(changed=changed[-20:]), self.assertRaises(RuntimeError):
                checked_mesh_quality(changed, 22308, 17452.5)


if __name__ == '__main__':
    unittest.main()
