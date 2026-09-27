import copy
import json
from pathlib import Path
import unittest
from tracer_transport.warehouse_scenario import validate

ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT/'tracer_transport/warehouse_plan_scenario.json').read_text())

    def test_plan_constraints_and_time_domain(self):
        self.assertEqual(validate(self.spec)['cells'], 85800)
        for edit in ('temperature', 'clearance', 'overlap'):
            value = copy.deepcopy(self.spec)
            if edit == 'temperature': value['temperature']['values_C'][0] = 50
            elif edit == 'clearance': value['loading']['blocks'][0]['min_m'][0] = .5
            else: value['loading']['blocks'].append(value['loading']['blocks'][0])
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                validate(value)

    def test_missing_assumption_provenance_rejected(self):
        self.spec['initial']['basis'] = ''
        with self.assertRaises(ValueError): validate(self.spec)
