"""Result screen must reject tampering and keep query units/domain explicit."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from cfd_studio.warehouse_results import WarehouseResults


class WarehouseResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = self.root/'warehouse_transport_fixture'
        self.case.mkdir()
        (self.case/'state.json').write_text('{"status":"complete"}')
        (self.case/'model_contract.json').write_text(json.dumps({
            'kind': 'normalized_gable_verification', 'model_validation': 'numerical_only',
            'initial_unit': 'C/C_ref', 'geometry': {'cells': 2}}))
        (self.case/'checks.json').write_text(json.dumps({
            'numerical_pass': True, 'cells': 2, 'frames': 2,
            'geometry_basis': 'nominal_drawing_envelope', 'relative_balance_error': 0}))
        (self.case/'transport_input.json').write_text(json.dumps({'geometry_spec': {'geometry': {
            'length_m': 2, 'width_m': 2, 'eaves_m': 2, 'roof_rise_m': 1}}}))
        np.savez_compressed(self.case/'concentration.npz', times_s=[0., 1.],
                            concentration=[[1., 2.], [2., 3.]],
                            cell_centres_m=[[0.5, 0.5, 0.5], [1.5, 1.5, 0.5]],
                            concentration_unit='C/C_ref')
        for time, values in [('0', '1\n2'), ('1', '2\n3')]:
            (self.case/time).mkdir()
            (self.case/time/'C').write_text('internalField nonuniform List<scalar> 2 ('+values+') ;\nboundaryField {}')
        self.reader = WarehouseResults(self.root)

    def test_query_matches_saved_raw_and_keeps_normalized_units(self):
        self.assertEqual(len(self.reader.list()), 1)
        self.assertEqual(self.reader.frame(self.case.name, 0)['concentration'], [1., 2.])
        value = self.reader.sample(self.case.name, [0.5, 0.5, 0.5], .5, .1)
        self.assertEqual(value['concentration'], 1.5)
        self.assertEqual(value['concentration_unit'], 'C/C_ref')
        self.assertIsNone(value['temperature'])
        self.assertEqual(len(value['source_files']), 2)
        self.assertEqual(len(self.reader.sample(self.case.name, [0.5, .5, .5], 0, .1)['source_files']), 1)

    def test_rejects_outside_domain_path_and_tampered_raw(self):
        for name in ('../warehouse_transport_fixture', 'warehouse_transport_fixture/0', 'other'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.reader.metadata(name)
        with self.assertRaisesRegex(ValueError, '영역 밖'):
            self.reader.sample(self.case.name, [3, 0, 0], 0, 1)
        with self.assertRaisesRegex(ValueError, '프레임 범위'):
            self.reader.sample(self.case.name, [.5, .5, .5], 2, 1)
        with self.assertRaisesRegex(ValueError, '허용 거리'):
            self.reader.sample(self.case.name, [1, 1, .5], 0, .1)
        (self.case/'1/C').write_text('internalField uniform 99; boundaryField {}')
        with self.assertRaisesRegex(ValueError, '일치하지'):
            self.reader.frame(self.case.name, 1)

    def test_corrupt_archive_is_not_offered_as_completed_result(self):
        (self.case/'concentration.npz').write_bytes(b'not-an-array')
        self.assertEqual(self.reader.list(), [])


if __name__ == '__main__':
    unittest.main()
