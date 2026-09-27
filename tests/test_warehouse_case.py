import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tracer_transport.compare_measurements import compare
from tracer_transport.warehouse_case import AIR_DIFFUSIVITY_M2_S, generate, validate


ROOT = Path(__file__).resolve().parents[1]


class WarehouseCaseTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'tracer_transport/warehouse_gable_verification.json').read_text())
        self.config['geometry_spec']['mesh'] = {'nx': 4, 'ny_per_half': 1, 'nz': 1, 'maximum_cells': 100}

    def physical(self):
        self.config['transport'] = {
            'kind': 'clo2_gas_in_air', 'temperature_C': 23, 'initial_mg_m3': 1,
            'initial_evidence': 'synthetic interface test',
            'reaction': {'value_s_inv': 0.1, 'basis': 'scenario_assumption', 'source': 'synthetic'},
            'exchange': {'value_s_inv': 0.05, 'basis': 'scenario_assumption', 'source': 'synthetic'}}

    def test_air_diffusivity_is_cited_and_converted_to_si(self):
        self.physical()
        model = validate(self.config)
        self.assertEqual(model['diffusivity_m2_s'], AIR_DIFFUSIVITY_M2_S[23])
        self.assertEqual(model['initial_kg_m3'], 1e-6)
        self.assertIn('2014.07.008', model['diffusivity_source'])
        self.assertEqual(model['model_validation'], 'unvalidated_for_rice_warehouse')

    def test_no_temperature_extrapolation_or_unattributed_rates(self):
        self.physical()
        self.config['transport']['temperature_C'] = 25
        with self.assertRaises(ValueError):
            validate(self.config)
        self.config['transport']['temperature_C'] = 23
        self.config['transport']['reaction']['source'] = ''
        with self.assertRaises(ValueError):
            validate(self.config)

    def test_unsupported_physical_fields_do_not_disappear(self):
        self.physical()
        self.config['transport']['supply'] = {'rate': 1}
        with self.assertRaises(ValueError):
            validate(self.config)

    def test_generated_case_has_gable_patches_and_separate_sinks(self):
        self.physical()
        with tempfile.TemporaryDirectory() as folder:
            case = Path(folder)/'case'
            generate(self.config, case)
            self.assertIn('annexInterface', (case/'0/C').read_text())
            self.assertIn('0.1', (case/'0/decayRate').read_text())
            self.assertIn('0.05', (case/'0/exchangeRate').read_text())
            self.assertIn('1 -3 0 0 0 0 0', (case/'0/C').read_text())
            self.assertTrue((case/'input_hashes.json').exists())
            with self.assertRaises(FileExistsError):
                generate(self.config, case)

    def test_comparison_rejects_normalized_and_out_of_range(self):
        with tempfile.TemporaryDirectory() as folder:
            case = Path(folder)/'case'
            generate(self.config, case)
            with self.assertRaises(ValueError):
                compare(case, Path(folder)/'missing.csv', Path(folder)/'comparison', 'synthetic', 1)

    def test_comparison_metrics_preserve_validation_split(self):
        self.physical()
        with tempfile.TemporaryDirectory() as folder:
            case = Path(folder)/'case'
            generate(self.config, case)
            centres = np.array([[1., 1., 1.]])
            np.savez_compressed(case/'concentration.npz', times_s=[0., 1.],
                                concentration=np.array([[1e-6], [0.5e-6]]),
                                concentration_unit='kg/m3', cell_centres_m=centres)
            observations = Path(folder)/'observations.csv'
            with observations.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['sensor_id', 'x_m', 'y_m', 'z_m', 'time_s',
                                 'concentration_mg_m3', 'uncertainty_mg_m3', 'split'])
                writer.writerow(['S1', 1, 1, 1, 0.5, 0.7, 0.1, 'validation'])
            result = compare(case, observations, Path(folder)/'comparison', 'synthetic observation', 0.1)
            self.assertAlmostEqual(result['metrics']['validation']['mae_mg_m3'], 0.05)
            self.assertEqual(result['comparison_status'], 'computed_not_certified')
            with self.assertRaises(FileExistsError):
                compare(case, observations, Path(folder)/'comparison', 'synthetic observation', 0.1)


if __name__ == '__main__':
    unittest.main()
