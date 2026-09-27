"""실행 없이 연구 대상과 실제 계산 모델의 표시 계약을 검사한다."""
import copy
import unittest

from study_platform.contracts import CAPABILITIES, base_input
from tracer_transport.protocol import contract


class ModelScopeTests(unittest.TestCase):
    def test_research_target_does_not_imply_simulated_chemistry(self):
        spec = base_input()
        self.assertEqual(spec['research_target'], 'ClO2')
        self.assertEqual(spec['represented_model'], 'normalized_inert_tracer')
        self.assertFalse(CAPABILITIES['physical_ClO2'])
        self.assertFalse(CAPABILITIES['experimental_validation'])

    def test_legacy_target_remains_metadata_not_physical_units(self):
        spec = base_input()
        conditions = contract(spec['parameters'], spec['kind'], spec['dt'])
        self.assertEqual(conditions['target_species'], 'PH3')
        self.assertEqual(conditions['represented_species'], spec['represented_model'])
        self.assertEqual(conditions['concentration'], 'pore C/C_ref')
        self.assertEqual(CAPABILITIES['units'], conditions['concentration'])
        self.assertFalse(conditions['experimental_reproduction'])

    def test_unavailable_fields_are_explicit(self):
        for name in ('temperature', 'leakage', 'bag_resistance', 'insects', 'mpi', 'gpu'):
            with self.subTest(name=name):
                self.assertIs(CAPABILITIES[name], False)
        self.assertEqual(CAPABILITIES['flow'], 'U=0')
        self.assertEqual(CAPABILITIES['geometry'], 'orthogonal_benchmark_only')

    def test_actual_species_cannot_be_silently_accepted(self):
        spec = base_input()
        for model in ('ClO2', 'PH3'):
            parameters = copy.deepcopy(spec['parameters'])
            parameters['model_kind'] = model
            with self.subTest(model=model), self.assertRaises(ValueError):
                contract(parameters, spec['kind'], spec['dt'])

    def test_reading_contract_does_not_modify_source(self):
        spec = base_input()
        before = copy.deepcopy(spec)
        contract(spec['parameters'], spec['kind'], spec['dt'])
        self.assertEqual(spec, before)
        spec['parameters']['evidence'] = 'temporary test metadata'
        self.assertEqual(base_input(), before)


if __name__ == '__main__':
    unittest.main()
