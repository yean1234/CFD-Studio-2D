"""치수·공급량은 코드 검사용 가정이며 실제 저장고 운전 조건이 아니다."""
import copy
import tempfile
import unittest

from study_platform.contracts import candidates
from study_platform.research_design import variable_schema
from study_platform.service import Service


def design_fixture():
    variables = variable_schema()['variables']
    layout = {'spacing_axis': 0, 'blocks': [
        {'id': 'a', 'min': [1, 1, 0], 'max': [3, 3, 2], 'mass_kg': 10},
        {'id': 'b', 'min': [4, 1, 0], 'max': [6, 3, 2], 'mass_kg': 10}]}
    values = {'layout': layout, 'spacing_m': 1, 'supply_positions': [[8, 2, 1]],
              'total_supply': {'value': 1, 'unit': 'normalized_test_unit', 'evidence': 'unit_test_only'}}
    for key, value in values.items():
        variables[key]['value'] = value
    baseline = {key: copy.deepcopy(v['value']) for key, v in variables.items()}
    return {'profile': 'warehouse_joint_v1', 'variables': variables, 'baseline': baseline,
            'sampling': {'method': 'cartesian_choices', 'seed': 42},
            'common': {'geometry': {'length_m': 10, 'width_m': 8, 'eaves_m': 4},
                       'stored_mass_kg': 20, 'mass_tolerance_kg': 0, 'source_count': 1,
                       'supply_duration_s': 10, 'wall_clearance_m': 1, 'maximum_stack_height_m': 3,
                       'aisles': [{'min': [0, 4, 0], 'max': [10, 6, 4], 'width_axis': 1, 'minimum_width_m': 2}],
                       'allowed_source_regions': [{'min': [7, 1, 0], 'max': [9, 3, 3]}]}}


class ResearchDesignTests(unittest.TestCase):
    def test_joint_candidates_and_supply_identity(self):
        d = design_fixture()
        d['variables']['supply_positions'] = {'mode': 'search', 'choices': [[[8, 2, 1]], [[8, 2.5, 1]]]}
        p = candidates(d)
        self.assertEqual(sum(r['valid'] for r in p['candidates']), 2)
        self.assertEqual(p, candidates(d))
        self.assertEqual(p['candidates'][0]['input']['supply']['mean_rate'], .1)
        self.assertFalse(p['solver_ready'])
        self.assertFalse('parameters' in p['candidates'][0]['input'])

    def test_constraints_do_not_silently_fix_geometry(self):
        for mutation, reason in [
            (lambda d: d['common'].update(stored_mass_kg=21), 'STORAGE_MASS'),
            (lambda d: d['common'].update(wall_clearance_m=2), 'BLOCK_OUTSIDE'),
            (lambda d: d['common']['aisles'][0].update(min=[0, 2, 0]), 'AISLE_BLOCKED'),
            (lambda d: d['baseline'].update(supply_positions=[[2, 2, 1]]), 'SOURCE_IN_BLOCK'),
            (lambda d: d['baseline'].update(supply_positions=None), 'SOURCE_COUNT'),
        ]:
            d = design_fixture(); mutation(d); original = copy.deepcopy(d)
            p = candidates(d)
            self.assertIn(reason, [v['code'] for v in p['candidates'][0]['violations']])
            self.assertEqual(original, d)

    def test_spacing_search_moves_blocks_without_changing_mass(self):
        d = design_fixture()
        d['variables']['spacing_m'] = {'mode': 'search', 'bounds': [1, 2], 'count': 2}
        p = candidates(d)
        row = p['candidates'][-1]
        self.assertEqual(row['input']['variables']['layout']['blocks'][1]['min'][0], 5)
        self.assertEqual(d['baseline']['layout']['blocks'][1]['min'][0], 4)
        self.assertTrue(row['valid'])
        d['variables']['spacing_m'] = {'mode': 'derived', 'rule': 'minimum_horizontal_clearance'}
        self.assertEqual(candidates(d)['candidates'][0]['input']['variables']['spacing_m'], 1)

    def test_fixed_quantities_and_missing_evidence(self):
        d = design_fixture(); d['variables']['total_supply']['mode'] = 'search'
        with self.assertRaises(ValueError): candidates(d)
        d = design_fixture(); d['variables']['total_supply']['value']['evidence'] = ''
        with self.assertRaises(ValueError): candidates(d)
        d = design_fixture(); d['baseline']['temperature_K'] = 300
        with self.assertRaises(ValueError): candidates(d)

    def test_persist_but_never_execute_warehouse_as_tracer(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Service(tmp, adapter=lambda *args: self.fail('must not run'))
            study = store.create('geometry only'); d = design_fixture()
            rev = store.commit(study, d, candidates(d)['preview_hash'], None)
            self.assertTrue(rev['cases'])
            with self.assertRaisesRegex(ValueError, '어댑터'):
                store.enqueue(rev['cases'], 'request')
            self.assertEqual(store.detail(study)['attempts'], [])


if __name__ == '__main__':
    unittest.main()
